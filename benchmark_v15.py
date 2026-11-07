"""One genuine autonomous baseline attempt in each of the six v15 worlds.

Run from physics_discovery, for example:
    .venv/bin/python benchmark_v15.py --output experiments/v15-baseline-20261107

Credentials come from the configured environment variable or a hidden prompt,
then reach each web_worker over stdin only. This driver never imports physical
truth, supplies candidate answers, retries a session, or expands its budget.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

from shore_agent.model import model_auth_config
from shore_agent.web_jobs import RunManager, _write, accepted_submission
from shore_worlds import V15_PHYSICS_VERSION, V15_WORLD_IDS, world_name
from shore_rules import apply_rules, rules_for

PROJECT = Path(__file__).resolve().parent


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (FileNotFoundError, OSError, ValueError):
        return default


def configuration(project=PROJECT, model='qwen3.8-27b', config_path=None, *, thinking=True, ruleset=None):
    """Copy the current example + trusted local web configuration, without keys."""
    if type(thinking) is not bool:
        raise ValueError('thinking_must_be_boolean')
    project = Path(project)
    config_path = Path(config_path) if config_path else project / 'config.local.web.json'
    config = read_json(project / 'config.example.json')
    override = read_json(config_path)
    if not isinstance(config, dict) or not isinstance(override, dict):
        raise ValueError('baseline_configuration_missing_or_invalid')
    config = copy.deepcopy(config)
    for section, value in override.items():
        if isinstance(value, dict) and isinstance(config.get(section), dict):
            config[section].update(value)
        else:
            config[section] = value
    config['environment'].update(world_set='v15', physics_version=V15_PHYSICS_VERSION, seed=42)
    if ruleset not in (None, 'e4', 'e5'):
        raise ValueError('unknown_baseline_ruleset')
    if ruleset is None:
        config['environment'].update(noise=False, wall_seconds=3600)
        config['environment'].pop('ruleset', None)
        config['environment'].pop('energy_budget', None)
    else:
        config['environment']['ruleset'] = ruleset
    for name in ('reference_length', 'position_limit', 'velocity_limit', 'time_max'):
        config['environment'].pop(name, None)
    config['model'].update(model=model, thinking=thinking, max_calls=None, main_max_calls=None)
    if ruleset is None:
        config['model'].pop('ruleset', None)
    config = apply_rules(config)
    for name in ('max_turns', 'max_rounds'):
        config.get('agent', {}).pop(name, None)
    model_auth_config(config['model'])  # Also rejects credential-bearing URLs.

    def check_keys(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key.lower() in {'api_key', 'authorization', 'password', 'secret', 'access_token'}:
                    raise ValueError('credentials_must_not_be_in_configuration')
                check_keys(item)
        elif isinstance(value, list):
            for item in value:
                check_keys(item)

    check_keys(config)
    json.dumps(config, allow_nan=False)
    return config


def _hashes(project):
    paths = ['shore_agent/agent.py', 'shore_agent/prompts/main.txt', 'shore_agent/prompts/e5.txt', 'shore_agent/prompts/e5_concise.txt', 'shore_agent/schemas.py',
             'shore_agent/runtime.py', 'shore_agent/numerics.py', 'shore_agent/expressions.py',
             'shore_agent/model.py', 'shore_agent/web_worker.py', 'shore_agent/store.py', 'shore_agent/workspace.py',
             'shore_agent/submission.py', 'shore_rules.py', 'shore_v15/simulator.py',
             'shore_v15/evaluation.py', 'benchmark_v15.py', 'shore_v15/vendor/SOURCE.json']
    return {path: hashlib.sha256((project / path).read_bytes()).hexdigest()
            for path in paths if (project / path).is_file()}


def _endpoints(config, model_endpoints):
    if model_endpoints is None:
        return [config['model']['base_url'].rstrip('/')] if config['environment'].get('ruleset') in ('e4', 'e5') else []
    endpoints = [item.strip().rstrip('/') for item in model_endpoints]
    if not endpoints or any(not item for item in endpoints) or len(set(endpoints)) != len(endpoints):
        raise ValueError('model_endpoints_must_be_distinct_nonempty_urls')
    for endpoint in endpoints:
        candidate = dict(config['model'], base_url=endpoint)
        model_auth_config(candidate)
    return endpoints


def prepare(output, config, workers=3, project=PROJECT, model_endpoints=None):
    """Reserve all six fresh run directories; no existing directory is reused."""
    output, project = Path(output).resolve(), Path(project).resolve()
    slug = re.sub(r'[^A-Za-z0-9_-]+', '-', output.name).strip('-_')
    if not slug or len(slug) > 80:
        raise ValueError('experiment_name_must_make_a_run_prefix_of_1_to_80_characters')
    if type(workers) is not int or not 1 <= workers <= 6:
        raise ValueError('workers_must_be_between_1_and_6')
    endpoints = _endpoints(config, model_endpoints)
    if endpoints:
        workers = min(workers, len(endpoints))
    profile = rules_for(config['environment'])
    ruleset = profile['ruleset']
    group = ruleset.upper()
    energy_budget = profile['energy_budget']
    wall_seconds = config['environment'].get('wall_seconds', profile['wall_seconds'])
    runs = {world: project / 'runs' / f'{slug}-{world}' for world in V15_WORLD_IDS}
    if output.exists() or any(path.exists() for path in runs.values()):
        raise ValueError('experiment_or_run_directory_already_exists_no_overwrite')
    output.mkdir(parents=True, exist_ok=False)
    created = now()
    for world, directory in runs.items():
        directory.mkdir(parents=True, exist_ok=False, mode=0o700)
        effective = copy.deepcopy(config)
        effective['environment']['world_id'] = world
        _write(directory / 'config.json', effective)
        _write(directory / 'web.json', {
            'id': directory.name, 'status': 'queued', 'mode': 'autonomous_discovery',
            'experiment_kind': 'v15_baseline', 'autonomous_discovery': True,
            'runner_owned': True, 'worker_pid': None, 'benchmark_id': output.name,
            'experiment_id': output.name, 'experiment_group': group, 'ruleset': ruleset,
            'arm': ruleset + '_local_rules_baseline' if ruleset in ('e4', 'e5') else 'unchanged_agent_v15_baseline',
            'created_at': created, 'model': effective['model']['model'],
            'world_set': 'v15', 'world_set_name': '新版 · v15',
            'world_id': world, 'world_name': world_name(world, 'v15'),
        })
    manifest = {'experiment_id': output.name, 'created_at': created, 'status': 'running',
                'kind': 'real_autonomous_v15_baseline', 'workers': workers,
                'experiment_group': group, 'ruleset': ruleset, 'model_endpoints': endpoints,
                'configuration': config, 'source_sha256': _hashes(project),
                'runs': {world: path.name for world, path in runs.items()},
                'protocol': {'attempts_per_world': 1, 'automatic_session_retries': False,
                             'resume_sessions': False, 'candidate_answers_supplied': False,
                             'energy_budget': energy_budget, 'wall_seconds_per_world': wall_seconds,
                             'single_active_world_per_endpoint': bool(endpoints),
                             'queue_time_excluded_from_mission_budget': True,
                             'evaluation': 'all_fixed_v15_cases_after_accepted_submission',
                             'official_score': False, 'official_sdk_compatible': False}}
    _write(output / 'manifest.json', manifest)
    return manifest, runs


def launch(directory, api_key, project=PROJECT, *, popen=subprocess.Popen):
    """Start one worker; credentials are excluded from argv, files and child env."""
    directory, project = Path(directory).resolve(), Path(project).resolve()
    config = read_json(directory / 'config.json')
    key_env, _required = model_auth_config(config['model'])
    env = dict(os.environ)
    for name in (key_env, 'DASHSCOPE_API_KEY', 'DEEPSEEK_API_KEY', 'OPENAI_API_KEY'):
        env.pop(name, None)
    env['PYTHONPATH'] = str(project)
    process = popen([sys.executable, '-u', '-m', 'shore_agent.web_worker', '--run-dir', str(directory)],
                    cwd=project, env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, text=True, encoding='utf-8', start_new_session=True)
    try:
        metadata = read_json(directory / 'web.json', {})
        metadata.update(status='running', worker_pid=process.pid, worker_started_at=now())
        _write(directory / 'web.json', metadata)
        process.stdin.write(json.dumps({'api_key': api_key}, ensure_ascii=False) + '\n')
        process.stdin.flush()
        process.stdin.close()
    except BaseException:
        terminate(process)
        raise
    return process


def terminate(process):
    """Only stop a child process group owned by this particular driver."""
    for sig, timeout in ((signal.SIGTERM, 2), (signal.SIGKILL, 3)):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            pass


def finished(directory, returncode, elapsed_seconds, *, reason=None):
    metadata = read_json(directory / 'web.json', {})
    result = read_json(directory / 'result.json', {})
    submission = accepted_submission(directory)
    fallback = 'stopped' if reason and reason != 'worker_start_failed' else 'error'
    status = 'submitted' if submission else result.get('status', fallback)
    if not result:
        result = {'status': status, 'reason': reason or 'worker_exited_without_result',
                  'submission': submission}
        _write(directory / 'result.json', result)
    metadata.update(status=status, worker_pid=None, worker_returncode=returncode,
                    finished_at=now(), wall_seconds_including_evaluation=elapsed_seconds)
    if reason:
        metadata['runner_end_reason'] = reason
    _write(directory / 'web.json', metadata)


def watchdog_expired(metadata, current=None):
    """Hard fallback for a stuck timed worker, excluding post-submission evaluation."""
    if (metadata.get('ruleset') not in ('e4', 'e5') or metadata.get('exploration_finished_at')
            or metadata.get('status') not in ('starting', 'running')):
        return False
    try:
        deadline = datetime.fromisoformat(metadata['exploration_deadline_at'])
        if deadline.tzinfo is None:
            return False
        return ((current or datetime.now(timezone.utc)) - deadline).total_seconds() > 10
    except (KeyError, ValueError, TypeError):
        return False


def summarize(snapshot, directory):
    """Project only observed results; failed or incomplete attempts remain rows."""
    metadata = read_json(directory / 'web.json', {})
    config = read_json(directory / 'config.json', {})
    environment = config.get('environment', {})
    profile = rules_for(environment)
    ruleset = profile['ruleset']
    energy_budget = profile['energy_budget']
    wall_limit = environment.get('wall_seconds', profile['wall_seconds'])
    result = snapshot.get('result') or {}
    usage, budget = snapshot.get('model_usage') or {}, snapshot.get('budget') or {}
    records = snapshot.get('records') or {}
    accepted = [s for s in records.get('submissions', [])
                if s.get('status') == 'accepted' and s.get('session_ended') is True]
    submission = accepted[0] if len(accepted) == 1 else None
    law = next((item for item in records.get('laws', [])
                if submission and item.get('law_id') == submission.get('law_id')), None)
    evaluation = snapshot.get('evaluation') or {}
    valid_evaluation = bool(submission and evaluation.get('world_set') == 'v15'
                            and evaluation.get('world_id') == snapshot.get('world_id')
                            and evaluation.get('physics_version') == V15_PHYSICS_VERSION
                            and evaluation.get('submission_id') == submission.get('submission_id')
                            and evaluation.get('law_id') == submission.get('law_id'))
    remaining = budget.get('energy_remaining')
    wall_remaining = budget.get('wall_seconds_remaining')
    terminal = snapshot.get('status') not in ('queued', 'starting', 'running', 'evaluating')
    requests = []
    try:
        for line in (directory / 'model_events.jsonl').read_text().splitlines():
            try:
                event = json.loads(line)
                if event.get('event') == 'request':
                    requests.append(event)
            except ValueError:
                continue  # A live writer may not have finished its last line yet.
    except OSError:
        pass
    reported = [event for event in requests if type(event.get('usage', {}).get('completion_tokens')) is int]
    output_values = [event['usage']['completion_tokens'] for event in reported]
    output_limit = config.get('model', {}).get('max_tokens_per_call', profile['max_tokens_per_call'] or 65536)
    missing_usage = max(0, (usage.get('calls') or 0) - len(reported))
    average = (usage['completion_tokens'] / usage['calls'] if terminal and usage.get('calls')
               and missing_usage == 0 and type(usage.get('completion_tokens')) is int else None)
    exploration = metadata.get('exploration_wall_seconds', metadata.get('exploration_seconds'))
    timing_source = 'worker_monotonic' if type(exploration) in (int, float) else None
    if exploration is None and type(wall_remaining) in (int, float):
        exploration = max(0., wall_limit - wall_remaining)
        timing_source = 'mission_budget_elapsed'
    return {'world_id': snapshot.get('world_id'), 'world_set': 'v15', 'run_id': directory.name,
            'ruleset': ruleset, 'experiment_group': ruleset.upper(),
            'model_endpoint': metadata.get('model_endpoint'),
            'status': snapshot.get('status'), 'reason': result.get('reason'),
            'running': snapshot.get('running', False), 'worker_returncode': metadata.get('worker_returncode'),
            'started_at': metadata.get('worker_started_at'), 'finished_at': metadata.get('finished_at'),
            'session_started_at': metadata.get('session_started_at'),
            'wall_seconds_including_evaluation': metadata.get('wall_seconds_including_evaluation'),
            'exploration_seconds': exploration, 'exploration_timing_source': timing_source,
            'evaluation_seconds': metadata.get('evaluation_wall_seconds', metadata.get('evaluation_seconds')),
            'exploration_finished_at': metadata.get('exploration_finished_at'),
            'exploration_deadline_at': metadata.get('exploration_deadline_at'),
            'submission_elapsed_seconds': metadata.get('submission_elapsed_seconds'),
            'exploration_deadline_seconds': wall_limit,
            'exploration_deadline_met': metadata.get('submission_deadline_met',
                bool(submission) and exploration <= wall_limit if terminal and exploration is not None else None),
            'model_elapsed_seconds': usage.get('elapsed_seconds'),
            'average_output_tokens_per_call': average,
            'max_call_output_tokens': max(output_values) if output_values else None,
            'output_limit_tokens': output_limit,
            'output_limit_exceeded_calls': sum(value > output_limit for value in output_values),
            'requests_with_reported_usage': len(reported), 'requests_without_reported_usage': missing_usage,
            'output_cap_compliant': (all(value <= output_limit for value in output_values)
                                     if terminal and output_values and missing_usage == 0 else None),
            'model_usage': usage, 'calls': usage.get('calls'), 'tokens': usage.get('total_tokens'),
            'prompt_tokens': usage.get('prompt_tokens'), 'completion_tokens': usage.get('completion_tokens'),
            'conservative_reserved_tokens': usage.get('conservative_reserved_tokens'),
            'energy_remaining': remaining,
            'energy_budget': energy_budget,
            'energy_used': energy_budget - remaining if type(remaining) in (int, float) else None,
            'wall_seconds_remaining': budget.get('wall_seconds_remaining'),
            'accepted_submission': bool(submission), 'law_versions': len(records.get('laws', [])),
            'law': {key: law.get(key) for key in ('law_id', 'law_spec', 'fitted_parameters')} if law else None,
            'claims': submission.get('claims') if submission else None,
            'physical_explanation': submission.get('physical_explanation') if submission else None,
            'evaluation_state': snapshot.get('evaluation_state'),
            'evaluation_complete': bool(valid_evaluation and evaluation.get('complete')),
            'evaluation_score': snapshot.get('evaluation_score') if valid_evaluation else None,
            'independent_rmse': evaluation.get('overall') if valid_evaluation and evaluation.get('complete') else None,
            'evaluation_failures': evaluation.get('failures') if valid_evaluation else None,
            'evaluation_error': snapshot.get('evaluation_error'),
            'n_test_trajectories': evaluation.get('n_trajectories') if valid_evaluation else None}


def markdown(summary):
    def cell(value):
        if value is None:
            return '—'
        if isinstance(value, float):
            return f'{value:.6g}'
        return str(value).replace('|', '\\|').replace('\n', ' ')

    config = summary['configuration']
    env = config['environment']
    profile = rules_for(env)
    ruleset = profile['ruleset']
    group = summary.get('experiment_group', ruleset.upper())
    energy = profile['energy_budget']
    wall = env.get('wall_seconds', profile['wall_seconds'])
    lines = ['# v15 六世界自主探索 Baseline', '',
             f"实验：`{summary['experiment_id']}`；归档：{group}；规则：`{ruleset}`；编排状态：`{summary['status']}`。", '',
             f"模型 `{config['model']['model']}`；thinking={str(config['model']['thinking']).lower()}；"
             f"噪声={'开启' if env.get('noise') else '关闭'}；seed={env.get('seed')}；"
             f'每世界 {energy} 能量、{wall:g} 秒；每世界仅一次真实模型探索，不自动重跑。', '',
             f"继承配置：总 token 预算 {config['model'].get('max_total_tokens')}，"
             f"单次输出上限 {config['model'].get('max_tokens_per_call')}，"
             f"原模型请求重试上限 {config['model'].get('max_retries')}。Agent、提示词、工具沿用当前版本。", '',
             f'评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 {energy} 能量口径。'
             '这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。', '',
             'Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，'
             '未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。', '',
             '每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；'
             '运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；'
             '总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。', '',
             '| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |',
             '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for row in summary['worlds']:
        score = row.get('evaluation_score') or {}
        rmse = row.get('independent_rmse') or {}
        status = str(row['status']) + (' / ' + str(row['reason']) if row.get('reason') else '')
        average = (row.get('completion_tokens', 0) / row['calls']
                   if row.get('calls') and row.get('conservative_reserved_tokens') == 0
                   and row['status'] not in ('running', 'queued', 'starting', 'evaluating') else None)
        cells = [row['world_id'], status, row['calls'], row['tokens'], row.get('completion_tokens'), average, row['energy_used'],
                 score.get('total'), rmse.get('position_rmse'), row.get('exploration_seconds'),
                 row.get('evaluation_seconds'), row.get('max_call_output_tokens'), row.get('output_limit_exceeded_calls'),
                 row['wall_seconds_including_evaluation']]
        lines.append('| ' + ' | '.join(cell(value) for value in cells) + ' |')
    lines += ['', '## 逐世界记录', '']
    for row in summary['worlds']:
        lines += [f"### {row['world_id']}", '', f"运行：`{row['run_id']}`。", '',
                  f"[本地研究台](http://127.0.0.1:8765/?run={row['run_id']})", '',
                  '```json', json.dumps({'law': row['law'], 'claims': row['claims'],
                                         'evaluation_error': row['evaluation_error'],
                                         'evaluation_failures': row['evaluation_failures']},
                                        ensure_ascii=False, indent=2), '```', '']
    lines += ['时间戳为 UTC；完整预算、真实模型回复、实验与候选版本保存在各运行目录。', '']
    return '\n'.join(lines)


def save_summary(output, manifest, runs, manager, *, status='running'):
    summary = dict(manifest, status=status, updated_at=now(), worlds=[
        summarize(manager.snapshot(directory.name), directory) for directory in runs.values()])
    if status != 'running':
        summary['finished_at'] = now()
        _write(output / 'manifest.json', dict(manifest, status=status,
                                             finished_at=summary['finished_at']))
    _write(output / 'summary.json', summary)
    temporary = output / '.report.md.tmp'
    temporary.write_text(markdown(summary), encoding='utf-8')
    temporary.replace(output / 'report.md')
    return summary


def run(output, config, api_key, workers=3, project=PROJECT, model_endpoints=None):
    project, output = Path(project).resolve(), Path(output).resolve()
    manifest, runs = prepare(output, config, workers, project, model_endpoints=model_endpoints)
    workers, endpoints = manifest['workers'], manifest['model_endpoints']
    manager = RunManager(project)
    pending, active = list(runs.items()), {}
    completed = False
    try:
        save_summary(output, manifest, runs, manager)
        while pending or active:
            while pending and len(active) < workers:
                occupied = {item[3] for item in active.values()}
                endpoint = next((item for item in endpoints if item not in occupied), None)
                if endpoints and endpoint is None:
                    break
                world, directory = pending.pop(0)
                if endpoint:
                    effective = read_json(directory / 'config.json')
                    effective['model']['base_url'] = endpoint
                    if 'local_model_endpoints' in effective['model']:
                        effective['model']['local_model_endpoints'][effective['model']['model']] = endpoint
                    _write(directory / 'config.json', effective)
                    metadata = read_json(directory / 'web.json')
                    metadata['model_endpoint'] = endpoint
                    _write(directory / 'web.json', metadata)
                started = time.monotonic()
                try:
                    process = launch(directory, api_key, project)
                except (OSError, ValueError, subprocess.SubprocessError):
                    finished(directory, None, time.monotonic() - started, reason='worker_start_failed')
                    print(json.dumps({'event': 'failed_to_start', 'world': world,
                                      'run_id': directory.name}), flush=True)
                    continue
                active[world] = (directory, process, started, endpoint)
                print(json.dumps({'event': 'started', 'world': world, 'run_id': directory.name,
                                  'worker_pid': process.pid}), flush=True)
            for world, (directory, process, started, _endpoint) in list(active.items()):
                code = process.poll()
                if code is None:
                    if watchdog_expired(read_json(directory / 'web.json', {})):
                        terminate(process)
                        finished(directory, process.returncode, time.monotonic() - started,
                                 reason='exploration_watchdog_timeout')
                        active.pop(world)
                    continue
                process.wait()
                finished(directory, code, time.monotonic() - started)
                active.pop(world)
                print(json.dumps({'event': 'finished', 'world': world, 'run_id': directory.name,
                                  'returncode': code}), flush=True)
            save_summary(output, manifest, runs, manager)
            if active:
                time.sleep(5)
        completed = True
        return save_summary(output, manifest, runs, manager, status='completed')
    finally:
        api_key = None
        if not completed:
            for directory, process, started, _endpoint in active.values():
                terminate(process)
                finished(directory, process.returncode, time.monotonic() - started,
                         reason='baseline_driver_interrupted')
            for _world, directory in pending:
                finished(directory, None, 0., reason='not_started_driver_interrupted')
            save_summary(output, manifest, runs, manager, status='interrupted')
        manager.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New experiment summary directory')
    parser.add_argument('--workers', type=int, default=3, choices=range(1, 7))
    parser.add_argument('--model', default='qwen3.8-27b')
    parser.add_argument('--no-thinking', action='store_true', help='Disable model thinking for all six runs')
    parser.add_argument('--config', type=Path, help='Trusted override; default config.local.web.json')
    parser.add_argument('--ruleset', choices=['e4', 'e5'], help='10 energy, 300s, 4096 output tokens; E4 noisy, E5 noise-free')
    parser.add_argument('--model-endpoints', help='Comma-separated distinct API base URLs; one active world per endpoint')
    parser.add_argument('--ask-key', action='store_true', help='Read key using a hidden terminal prompt')
    args = parser.parse_args()
    key = None
    try:
        config_kwargs = dict(model=args.model, config_path=args.config, thinking=not args.no_thinking)
        if args.ruleset:
            config_kwargs['ruleset'] = args.ruleset
        config = configuration(**config_kwargs)
        key_env, key_required = model_auth_config(config['model'])
        key = '' if args.ask_key else os.environ.get(key_env, '').strip()
        if args.ask_key or (key_required and not key):
            key = getpass.getpass(f'{key_env} (hidden, never saved): ').strip()
        if key_required and not key:
            parser.error('api_key_missing')
        if len(key) > 512 or any(ord(char) < 32 or ord(char) == 127 for char in key):
            parser.error('invalid_api_key')
        signal.signal(signal.SIGTERM, lambda *_args: (_ for _ in ()).throw(KeyboardInterrupt()))
        run_kwargs = {'model_endpoints': args.model_endpoints.split(',')} if args.model_endpoints else {}
        summary = run(args.output, config, key, args.workers, **run_kwargs)
        print(json.dumps({'event': 'baseline_completed', 'output': str(args.output.resolve()),
                          'statuses': {row['world_id']: row['status'] for row in summary['worlds']}}), flush=True)
    except KeyboardInterrupt:
        parser.exit(130, 'Baseline interrupted; completed records and partial results preserved.\n')
    except (OSError, ValueError, subprocess.SubprocessError):
        # Never dump an exception that could contain process input or a key.
        parser.exit(2, 'Baseline failed; inspect the preserved summary and run records.\n')
    finally:
        key = None


if __name__ == '__main__':
    main()
