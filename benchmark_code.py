"""E2: preregistered 30-run optional-code ablation, three isolated workers.

No candidate laws, simulator truth, or model messages are read by this driver.
Each scheduled attempt runs once. Failed attempts are retained, never replaced.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
from datetime import datetime, timezone
import getpass
import hashlib
import json
import math
import os
from pathlib import Path
import random
import signal
import statistics
import subprocess
import sys
import time

from shore_agent.web_jobs import _read, _write, accepted_submission

PROJECT = Path(__file__).resolve().parent
ARMS = ('baseline', 'code')
WORLDS = ('world_3', 'world_4', 'world_5')
THREAD_VARS = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
               'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS', 'BLIS_NUM_THREADS')
CONCURRENCY = 3
SCHEDULE_SEED = 2026110402


def now():
    return datetime.now(timezone.utc).isoformat()


def schedule(seed=SCHEDULE_SEED):
    rng = random.Random(seed)
    jobs = []
    for repeat in range(1, 6):
        block = [{'world_id': world, 'arm': arm, 'repeat': repeat}
                 for world in WORLDS for arm in ARMS]
        rng.shuffle(block)
        jobs.extend(block)
    for index, job in enumerate(jobs, 1):
        job.update(order=index, run_id=f'E2-{job["arm"]}-w{job["world_id"][-1]}-r{job["repeat"]}')
    return jobs


def configuration(base, job):
    config = copy.deepcopy(base)
    # No browser/session setting can alter the registered experiment.
    config['environment'].update(world_id=job['world_id'], physics_version='v4',
                                 seed=42, noise=False, wall_seconds=3600)
    config['model'].update(model='deepseek-flash', base_url='https://api.deepseek.com',
        deployment='cloud', reasoning_protocol='deepseek', thinking=True,
        api_key_env='DEEPSEEK_API_KEY', api_key_required=True,
        reasoning_effort='high', max_calls=None, main_max_calls=None,
        max_total_tokens=5000000, max_tokens_per_call=393216, timeout_seconds=1800,
        max_retries=1)
    config['model'].pop('main_timeout_seconds', None)
    config.setdefault('agent', {}).pop('max_turns', None)
    config['agent'].pop('max_rounds', None)
    config.setdefault('code_execution', {}).update(enabled=job['arm'] == 'code', timeout_seconds=90, memory_mb=1024)
    return config


def source_hashes(project=PROJECT):
    paths = [project / name for name in ('evaluate.py', 'shore_worlds.py', 'shore_scoring.py',
             'benchmark_code.py', 'config.example.json', 'code_sandbox/runner.py', 'code_sandbox/Dockerfile')]
    for folder in ('shore_agent', 'shore_sim'):
        paths.extend(p for p in (project / folder).rglob('*') if p.suffix in ('.py', '.txt'))
    return {str(p.relative_to(project)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths) if p.is_file()}


def jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def collect(directory, job, elapsed, returncode):
    """Whitelist public results and request metadata, excluding private thoughts."""
    result = _read(directory / 'result.json', directory, {})
    evaluation = _read(directory / 'evaluation.json', directory, {})
    metadata = _read(directory / 'web.json', directory, {})
    usage = result.get('model_usage') or {}
    requests = [e for e in jsonl(directory / 'model_events.jsonl') if e.get('event') == 'request']
    tools = jsonl(directory / 'tools.jsonl')
    executions = [_read(p, directory, {}) for p in sorted((directory / 'records' / 'code_execution').glob('*.json'))]
    code_time = sum(e.get('elapsed_seconds', 0) for e in executions)
    tool_time = sum(e.get('elapsed_seconds', 0) for e in tools)
    submitted = bool(accepted_submission(directory))
    evaluated = bool(submitted and evaluation.get('complete') and evaluation.get('overall')
                     and evaluation.get('seed') == 1871 and evaluation.get('n_trajectories') == 20
                     and evaluation.get('n_successful') == 20
                     and evaluation.get('world_id') == job['world_id']
                     and evaluation.get('physics_version') == 'v4')
    rmse = evaluation.get('overall', {}).get('position_rmse') if evaluated else None
    if rmse is not None and (not isinstance(rmse, (int, float)) or not math.isfinite(rmse)):
        raise ValueError('invalid_evaluation_metric')
    law_id = (result.get('submission') or {}).get('law_id') if submitted else None
    law = _read(directory / 'records' / 'law' / (law_id + '.json'), directory, {}) if law_id else {}
    # Persist no raw provider body, conversation text or research reasoning.
    request_fields = ('call_number', 'http_status', 'error', 'finish_reason', 'usage',
                      'elapsed_seconds', 'response_model', 'system_fingerprint', 'max_tokens',
                      'reasoning_protocol', 'requested_reasoning_effort')
    return {**job, 'status': result.get('status', 'error'),
        'reason': result.get('reason', 'worker_exited_without_result'), 'returncode': returncode,
        'accepted_submission': submitted, 'independent_evaluation_complete': evaluated,
        'position_rmse': rmse, 'velocity_rmse': (evaluation.get('overall') or {}).get('velocity_rmse') if evaluated else None,
        'high_precision': bool(evaluated and rmse < 1e-6),
        'score': evaluation.get('score') if submitted else None,
        'evaluation_status': metadata.get('evaluation_status', 'unavailable'),
        'evaluation_error': ('evaluation_missing_or_invalid' if submitted and not evaluation else
                             'independent_trajectory_failures' if evaluation.get('failures') else
                             'evaluation_protocol_mismatch' if submitted and not evaluated else None),
        'evaluation_failures': evaluation.get('failures', []),
        'calls': usage.get('calls', len(requests)), 'tokens': usage.get('total_tokens', 0),
        'completion_tokens': usage.get('completion_tokens', 0),
        'final_budget': result.get('budget'), 'elapsed_seconds': elapsed,
        'law': {k: law.get(k) for k in ('law_id', 'law_spec', 'fitted_parameters')} if law else None,
        'law_count': len(list((directory / 'records' / 'law').glob('*.json'))),
        'api_requests': [{k: e[k] for k in request_fields if k in e} for e in requests],
        'tool_counts': dict(Counter(e['tool'] for e in tools)),
        'code_execution_count': len(executions),
        'code_success_count': sum(e.get('status') == 'success' for e in executions),
        'code_status_counts': dict(Counter(e.get('status') for e in executions)),
        'code_elapsed_seconds': code_time,
        'code_cpu_seconds_reported': sum(e.get('cpu_seconds_reported', 0) for e in executions),
        'tool_elapsed_seconds': tool_time,
        'api_elapsed_seconds': sum(e.get('elapsed_seconds', 0) for e in requests),
        'code_execution_ids': [e['execution_id'] for e in executions],
        'tool_error_counts': dict(Counter((e.get('result', {}).get('error') or {}).get('code', 'unknown')
                                         for e in tools if not e.get('result', {}).get('ok')))}


def aggregate(rows):
    groups = []
    for world in (*WORLDS, 'all'):
        for arm in ARMS:
            cell = [r for r in rows if r['arm'] == arm and (world == 'all' or r['world_id'] == world)]
            completed = [r for r in cell if 'returncode' in r]
            errors = [r['position_rmse'] for r in completed if r.get('independent_evaluation_complete')]
            scores = [(r.get('score') or {}).get('total') for r in completed]
            scores = [s for s in scores if isinstance(s, (int, float)) and math.isfinite(s)]
            groups.append({'world_id': world, 'arm': arm, 'scheduled': len(cell), 'finished': len(completed),
                'submitted': sum(bool(r.get('accepted_submission')) for r in completed),
                'evaluated': len(errors), 'high_precision': sum(bool(r.get('high_precision')) for r in completed),
                'position_rmse_values': errors,
                'median_rmse_evaluated_only': statistics.median(errors) if errors else None,
                'score_n': len(scores), 'mean_score_scored_only': statistics.mean(scores) if scores else None,
                'median_score_scored_only': statistics.median(scores) if scores else None,
                'tokens': sum(r.get('tokens', 0) for r in completed),
                'median_seconds': statistics.median(r['elapsed_seconds'] for r in completed) if completed else None,
                'runs_using_code': sum(r.get('code_execution_count', 0) > 0 for r in completed),
                'code_calls': sum(r.get('code_execution_count', 0) for r in completed),
                'code_successes': sum(r.get('code_success_count', 0) for r in completed),
                'code_seconds': sum(r.get('code_elapsed_seconds', 0) for r in completed),
                'median_tool_seconds': statistics.median(r.get('tool_elapsed_seconds', 0) for r in completed) if completed else None,
                'termination_reasons': dict(Counter(r.get('reason') for r in completed))})
    return groups


def markdown(summary):
    lines = ['# E2：代码执行工具消融实验', '',
        '世界3/4/5 × baseline/code × 每组5次。固定3并发；5M总预算、393216单次输出、1800秒请求超时、3600秒会话。'
        '固定环境种子42、无噪声；提交后独立评测20条轨迹，种子1871。推理强度固定high；控制组保持原7工具和提示词，实验组增加可选run_code及接口说明。', '',
        '高精度次数指完整独立评测位置RMSE < 1e-6，仅为实验分析标签，不改变题目公式评分。'
        '所有失败均保留；均分只对有分数的会话计算，必须同时看提交/评测率，缺失分数不当作0分。', '',
        '| 世界 | 工具组 | 完成尝试 | 提交 | 完整评测 | 高精度 | 已评分均分（样本数） | 已评测RMSE中位数 |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for group in summary['groups']:
        n = group['scheduled']
        score = group['mean_score_scored_only']
        error = group['median_rmse_evaluated_only']
        lines.append(f'| {group["world_id"]} | {group["arm"]} | {group["finished"]}/{n} | '
            f'{group["submitted"]}/{n} | {group["evaluated"]}/{n} | {group["high_precision"]}/{n} | '
            + (f'{score:.3f} ({group["score_n"]})' if score is not None else '—') + ' | '
            + (f'{error:.4e}' if error is not None else '—') + ' |')
    lines += ['', '每格只有5次，接近的结果不足以证明稳定优胜。Token和耗时用于解释，不以省Token选择档位。', '',
              '逐次结果、模型返回版本与请求元数据见 summary.json；预注册顺序、配置、代码和提示词哈希见 manifest.json。'
              '原始记录仅保留在本机 runs/，不上传私有推理内容或凭证。', '']
    return '\n'.join(lines)


def run(output, key, *, project=PROJECT, poll_seconds=2):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('output_must_be_new_or_empty')
    jobs = schedule()
    runs = project / 'runs'
    staging = runs / '.E2-active'
    if staging.exists() or any((runs / j['run_id']).exists() for j in jobs):
        raise ValueError('E2_already_exists_no_automatic_resume_or_replacement')
    base = json.loads((project / 'config.example.json').read_text())
    from shore_agent.code_execution import sandbox_info
    sandbox = sandbox_info(base.get('code_execution'))
    if not sandbox['available']:
        raise ValueError('code_sandbox_unavailable')
    hashes = source_hashes(project)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=project, text=True).strip()
    # Reject credentials in any nonstandard config before persisting it.
    config_text = json.dumps(base)
    if any(marker in config_text for marker in ('sk-', 'Bearer ', 'api_key"')):
        raise ValueError('base_config_must_not_contain_credentials')
    output.mkdir(parents=True, exist_ok=True)
    staging.mkdir(parents=True, mode=0o700)
    manifest = {'experiment_id': 'E2', 'started_at': now(), 'status': 'running',
        'git_commit': commit, 'sandbox': sandbox, 'reasoning_effort': 'high', 'source_sha256': hashes, 'schedule_seed': SCHEDULE_SEED,
        'concurrency': CONCURRENCY, 'numerical_threads': 1, 'automatic_reruns': False,
        'evaluation': {'n_probes': 20, 'seed': 1871},
        'primary_diagnostic': 'Complete independent position RMSE < 1e-6, denominator all scheduled attempts',
        'model_version_note': 'Provider-managed deepseek-flash alias; returned model metadata recorded per request; weights not pinned.',
        'rows': [{**j, 'configuration': configuration(base, j), 'state': 'pending'} for j in jobs]}
    summary = {'experiment_id': 'E2', 'started_at': manifest['started_at'], 'status': 'running',
               'rows': [{**j, 'status': 'pending'} for j in jobs]}
    active = {}
    index = 0

    def checkpoint():
        summary['groups'] = aggregate(summary['rows'])
        _write(output / 'manifest.json', manifest)
        _write(output / 'summary.json', summary)
        (output / 'comparison.md').write_text(markdown(summary), encoding='utf-8')

    checkpoint()
    try:
        while index < len(jobs) or active:
            while index < len(jobs) and len(active) < CONCURRENCY:
                if source_hashes(project) != hashes or sandbox_info(base.get('code_execution')) != sandbox:
                    raise ValueError('frozen_source_changed')
                job = jobs[index]
                directory = staging / job['run_id']
                directory.mkdir(mode=0o700)
                entry = manifest['rows'][index]
                _write(directory / 'config.json', entry['configuration'])
                _write(directory / 'web.json', {'id': job['run_id'], 'created_at': now(), 'status': 'running',
                    'world_id': job['world_id'], 'mode': 'autonomous_discovery', 'experiment_id': 'E2',
                    'reasoning_effort': 'high', 'arm': job['arm'], 'repeat': job['repeat']})
                env = dict(os.environ)
                env.pop('DEEPSEEK_API_KEY', None)
                env.update({name: '1' for name in THREAD_VARS})
                env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(project))
                process = subprocess.Popen([sys.executable, '-u', '-m', 'shore_agent.web_worker',
                    '--run-dir', str(directory)], cwd=project, env=env,
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    text=True, start_new_session=True)
                active[index] = (process, time.monotonic(), directory)
                process.stdin.write(json.dumps({'api_key': key}) + '\n')
                process.stdin.close()
                entry.update(state='running', started_at=now(), worker_pid=process.pid)
                summary['rows'][index]['status'] = 'running'
                print(f'E2 {index+1}/30 START {job["run_id"]}', flush=True)
                index += 1
                checkpoint()
            for slot, (process, start, directory) in list(active.items()):
                code = process.poll()
                if code is None:
                    continue
                job = jobs[slot]
                row = collect(directory, job, time.monotonic() - start, code)
                # Only closed/evaluated sessions enter the ordinary workbench history.
                directory.rename(runs / job['run_id'])
                summary['rows'][slot] = row
                manifest['rows'][slot].update(state='finished', finished_at=now(), returncode=code)
                del active[slot]
                checkpoint()
                print(f'E2 DONE {job["run_id"]} status={row["status"]} rmse={row["position_rmse"]} '
                      f'tokens={row["tokens"]} reason={row["reason"]}', flush=True)
            if active:
                time.sleep(poll_seconds)
        manifest['status'] = summary['status'] = 'completed_all_attempts'
        manifest['source_unchanged'] = source_hashes(project) == hashes
        staging.rmdir()
    except BaseException:
        manifest['status'] = summary['status'] = 'interrupted_no_replacement'
        # Stop only children of this driver; their incomplete raw records remain.
        for process, _, _ in active.values():
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        raise
    finally:
        manifest['finished_at'] = summary['finished_at'] = now()
        checkpoint()
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', default=str(PROJECT / 'experiments' / 'E2'))
    parser.add_argument('--ask-key', action='store_true')
    args = parser.parse_args()
    key = getpass.getpass('API key (hidden; memory only): ') if args.ask_key else os.environ.get('DEEPSEEK_API_KEY')
    if not key:
        parser.error('API key missing')
    try:
        run(args.output_dir, key)
    except (ValueError, OSError):
        # Credentials never appear in exception or traceback output.
        parser.exit(2, 'E2 controller stopped; inspect its manifest. No automatic retry.\n')
    finally:
        key = None


if __name__ == '__main__':
    main()
