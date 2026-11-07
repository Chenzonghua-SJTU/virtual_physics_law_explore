"""Read-only E5 diagnostics off/on comparison; no model, simulation or scoring.

python deployment/compare_e5_ab.py --off experiments/E5/OFF --on experiments/E5/ON \
    --runs-root runs --output experiments/E5/comparisons/OFF-vs-ON
Only comparison.json and report.md in a fresh output directory are written.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

WORLDS = [f'world_{i}' for i in range(1, 7)]
ACTIVE = {'queued', 'starting', 'running', 'evaluating'}
CLEAN_REFERENCE = 'Unmodified v15 DevelopmentSimulator and fixed public validation cases; no noise'
E3_PROMPT_SHA256 = 'c20d2d37d767ba2f91601fa084f3f28c8995fcd4c625cc6720c295677fcdb74e'


def number(value):
    return type(value) in (float, int) and math.isfinite(value)


def count(value):
    return type(value) is int and value >= 0


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path, errors):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise ValueError('not an object')
        return value
    except (OSError, ValueError):
        errors.append('missing_or_invalid_json:' + str(path))
        return {}


def elapsed(start, end):
    try:
        a, b = datetime.fromisoformat(start), datetime.fromisoformat(end)
        value = (b-a).total_seconds()
        return value if a.tzinfo and b.tzinfo and value >= 0 else None
    except (ValueError, TypeError):
        return None


def normalize(config):
    value = copy.deepcopy(config)
    value.setdefault('numerics', {}).pop('diagnostics_enabled', None)
    return value


def different_paths(a, b, prefix=''):
    if isinstance(a, dict) and isinstance(b, dict):
        result = []
        for key in sorted(set(a) | set(b)):
            path = prefix + '.' + key if prefix else key
            if key not in a or key not in b:
                result.append(path)
            else:
                result.extend(different_paths(a[key], b[key], path))
        return result
    return [] if type(a) is type(b) and a == b else [prefix]


def indexed(rows, mapping, errors, label):
    if not isinstance(rows, list):
        errors.append(label + ':missing_world_rows')
        return {}
    result = {}
    for row in rows:
        if not isinstance(row, dict) or row.get('world_id') not in WORLDS:
            errors.append(label + ':invalid_world_row')
            continue
        world = row['world_id']
        if world in result:
            errors.append(label + ':duplicate_world:' + world)
        if row.get('run_id') != mapping.get(world):
            errors.append(label + ':run_identity:' + world)
        result[world] = row
    if sorted(result) != WORLDS:
        errors.append(label + ':requires_six_worlds')
    return result


def tool_counts(tools):
    completed, unfinished = tools.get('per_call'), tools.get('unfinished_tool_calls')
    if not isinstance(completed, list) or not isinstance(unfinished, list):
        return {'calls': None, 'completed': None, 'successful': None, 'failed': None, 'unfinished': None}
    selected = [row for row in completed if row.get('tool') == 'diagnose_dynamics']
    pending = sum(row.get('tool') == 'diagnose_dynamics' for row in unfinished)
    successful = sum(row.get('ok') is True for row in selected)
    return {'calls': len(selected) + pending, 'completed': len(selected), 'successful': successful,
            'failed': len(selected) - successful, 'unfinished': pending}


def raw_check(directory, row, errors):
    """Cross-check archived evidence, without invoking the archive auditor."""
    files, logs = {}, {}
    for name in ('model_events.jsonl', 'events.jsonl', 'tools.jsonl'):
        path = directory / name
        try:
            logs[name] = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
            if any(not isinstance(event, dict) for event in logs[name]):
                raise ValueError('invalid event')
            files[name] = sha(path)
        except (OSError, ValueError):
            errors.append('raw_missing_or_invalid:' + name)
            logs[name] = []
    requests = [e for e in logs['model_events.jsonl'] if e.get('event') in ('request_started', 'request')]
    request_ids = {e.get('call_number') for e in requests}
    seed_verified = bool(requests) and all(type(e.get('seed')) is int and e['seed'] == 42 for e in requests)
    if not seed_verified:
        errors.append('raw_request_seed_not_verified_42')
    if len(request_ids) != row['calls']:
        errors.append('raw_model_call_count_mismatch')
    if any(type(e.get('max_tokens')) is not int or not 0 < e['max_tokens'] <= 4096 for e in requests):
        errors.append('raw_request_output_cap_invalid')
    completed = [e for e in logs['tools.jsonl'] if e.get('tool') == 'diagnose_dynamics']
    starts = [e for e in logs['events.jsonl'] if e.get('event') == 'tool_started' and e.get('name') == 'diagnose_dynamics']
    ends = {e.get('tool_call_id') for e in logs['events.jsonl'] if e.get('event') == 'tool_finished'}
    unfinished = sum(e.get('tool_call_id') not in ends for e in starts)
    observed = {'calls': len(completed)+unfinished, 'completed': len(completed),
                'successful': sum(e.get('result', {}).get('ok') is True for e in completed),
                'failed': sum(e.get('result', {}).get('ok') is not True for e in completed), 'unfinished': unfinished}
    if observed != row['diagnostic_tool']:
        errors.append('raw_diagnostic_call_count_mismatch')
    evaluation_path = directory / 'evaluation.json'
    if evaluation_path.exists():
        evaluation = read(evaluation_path, errors)
        files['evaluation.json'] = sha(evaluation_path)
        if evaluation.get('truth_reference') != CLEAN_REFERENCE:
            errors.append('raw_evaluation_not_verified_noise_free')
        if evaluation.get('complete') != row['evaluation_complete']:
            errors.append('raw_evaluation_completion_mismatch')
        if evaluation.get('score', {}).get('total') != row['score']:
            errors.append('raw_evaluation_score_mismatch')
    elif row['evaluation_complete']:
        errors.append('raw_evaluation_missing')
    return {'files_sha256': files, 'request_seed_42_verified': seed_verified,
            'diagnostic_tool': observed}


def one_world(world, summary, audited, enabled, runs_root, errors, warnings):
    local_errors = []
    model, evaluation, timing = (audited.get(key, {}) for key in ('model', 'evaluation', 'timing'))
    per_call = model.get('per_call', [])
    calls = model.get('calls') if count(model.get('calls')) else None
    seeds_ok = (calls is not None and calls > 0 and isinstance(per_call, list) and len(per_call) == calls
                and all(type(c.get('sampling_seed')) is int and c['sampling_seed'] == 42 for c in per_call))
    if not seeds_ok:
        local_errors.append('per_call_seed_not_verified_42')
    if audited.get('diagnostics_enabled') is not enabled:
        local_errors.append('run_diagnostics_flag_mismatch')
    usage_complete = (model.get('usage_complete') is True and calls is not None and calls > 0
                      and len(per_call) == calls and all(c.get('usage_complete') is True for c in per_call))
    reported = [c.get('usage', {}).get('completion_tokens') for c in per_call if isinstance(c.get('usage'), dict)]
    if any(not count(value) for value in reported):
        local_errors.append('invalid_reported_completion_usage')
        reported = [value for value in reported if count(value)]
        usage_complete = False
    if len(reported) != calls:
        usage_complete = False
    reported_total = sum(reported)
    if model.get('completion_tokens_reported') != reported_total:
        local_errors.append('audited_output_total_mismatch')
        usage_complete = False
    if not usage_complete:
        warnings.append(world + ':output_usage_incomplete_average_unknown')
    max_output = max(reported, default=None)
    if summary.get('calls') != calls:
        local_errors.append('summary_audit_call_count_mismatch')
    eval_checks = evaluation.get('checks', {})
    complete = (evaluation.get('complete') is True and summary.get('evaluation_complete') is True
                and evaluation.get('failures_count') == 0 and bool(eval_checks) and all(eval_checks.values()))
    score = evaluation.get('score')
    score = score if number(score) and 0 <= score <= 100 else None
    if (summary.get('evaluation_score') or {}).get('total') != score:
        local_errors.append('summary_audit_score_mismatch')
    if evaluation.get('complete') is True and eval_checks.get('no_noise_truth_reference') is not True:
        local_errors.append('evaluation_not_verified_noise_free')
    finished = summary.get('status') not in ACTIVE and summary.get('status') is not None and not summary.get('running')
    timely = audited.get('submission', {}).get('timely_pair') is True
    caps_ok = (bool(per_call) and all(type(c.get('requested_max_tokens')) is int and
               0 < c['requested_max_tokens'] <= 4096 for c in per_call)
               and all(value <= 4096 for value in reported))
    if not caps_ok:
        local_errors.append('output_cap_not_verified')
    diagnostic = tool_counts(audited.get('tools', {}))
    if not enabled and diagnostic['successful'] not in (None, 0):
        local_errors.append('disabled_diagnostic_succeeded')
    if diagnostic['calls'] is None:
        warnings.append(world + ':diagnostic_call_count_unknown')
    for source_key, audit_key in (('exploration_seconds', 'exploration_seconds'),
                                 ('evaluation_seconds', 'evaluation_seconds'),
                                 ('wall_seconds_including_evaluation', 'total_seconds_including_evaluation')):
        if summary.get(source_key) != timing.get(audit_key):
            local_errors.append('summary_audit_timing_mismatch:' + source_key)
    if summary.get('energy_used') != audited.get('energy_used'):
        local_errors.append('summary_audit_energy_mismatch')
    energy = audited.get('energy_used')
    if not number(energy) or not 0 <= energy <= 10:
        local_errors.append('energy_usage_not_verified_within_10')
    result = {'world_id': world, 'run_id': summary.get('run_id'), 'status': summary.get('status'),
              'reason': summary.get('reason'), 'score': score, 'evaluation_complete': complete,
              'noise_free_evaluation_verified': eval_checks.get('no_noise_truth_reference') is True,
              'timely_submission': timely, 'at_or_above_90': bool(finished and complete and timely and score is not None and score >= 90),
              'exploration_seconds': timing.get('exploration_seconds'),
              'evaluation_seconds': timing.get('evaluation_seconds'),
              'total_seconds_including_evaluation': timing.get('total_seconds_including_evaluation'),
              'calls': calls, 'usage_complete': usage_complete,
              'completion_tokens_reported': reported_total,
              'average_output_tokens_per_call': reported_total / calls if usage_complete else None,
              'max_call_output_tokens_reported': max_output, 'max_call_output_tokens': max_output if usage_complete else None,
              'output_cap_compliant': caps_ok if usage_complete else None,
              'request_seed_42_verified': seeds_ok, 'energy_used': audited.get('energy_used'),
              'diagnostic_tool': diagnostic, 'model_endpoint': summary.get('model_endpoint')}
    if runs_root is not None and isinstance(result['run_id'], str):
        directory = (runs_root / result['run_id']).resolve()
        if not directory.is_relative_to(runs_root.resolve()):
            local_errors.append('run_path_outside_runs_root')
        else:
            result['raw_evidence'] = raw_check(directory, result, local_errors)
    result['errors'] = local_errors
    errors.extend(world + ':' + error for error in local_errors)
    return result


def arm(batch, enabled, runs_root=None):
    errors, warnings = [], []
    files = {name: batch / name for name in ('manifest.json', 'summary.json', 'audit.json')}
    manifest, summary, audited = [read(files[name], errors) for name in files]
    if audited.get('manifest_sha256') != (sha(files['manifest.json']) if files['manifest.json'].is_file() else None):
        errors.append('audit_manifest_digest_mismatch')
    for key in ('experiment_id', 'experiment_group', 'ruleset'):
        if manifest.get(key) != summary.get(key) or manifest.get(key) != audited.get(key):
            errors.append('archive_identity_mismatch:' + key)
    if manifest.get('ruleset') != 'e5' or manifest.get('experiment_group') != 'E5':
        errors.append('requires_e5_profile')
    if manifest.get('configuration') != summary.get('configuration') or manifest.get('source_sha256') != summary.get('source_sha256'):
        errors.append('manifest_summary_configuration_or_source_mismatch')
    config = manifest.get('configuration', {})
    if config.get('numerics', {}).get('diagnostics_enabled') is not enabled:
        errors.append('wrong_arm_toggle')
    if 'diagnostics_enabled' in manifest.get('protocol', {}) and manifest['protocol']['diagnostics_enabled'] is not enabled:
        errors.append('protocol_diagnostics_toggle_mismatch')
    environment, model = config.get('environment', {}), config.get('model', {})
    fixed = {'energy_10': environment.get('energy_budget') == 10, 'wall_300': environment.get('wall_seconds') == 300,
             'exploration_no_noise': environment.get('noise') is False, 'thinking_off': model.get('thinking') is False,
             'output_cap_4096': model.get('max_tokens_per_call') == 4096,
             'sampling_seed_42': type(model.get('sampling_seed')) is int and model['sampling_seed'] == 42,
             'e3_prompt_selected': config.get('agent', {}).get('guidance_profile') == 'e3',
             'e3_main_prompt_bytes': manifest.get('source_sha256', {}).get('shore_agent/prompts/main.txt') == E3_PROMPT_SHA256}
    errors.extend('fixed_condition:' + key for key, value in fixed.items() if not value)
    mapping = manifest.get('runs', {})
    if sorted(mapping) != WORLDS or len(set(mapping.values())) != 6:
        errors.append('requires_six_distinct_world_runs')
    summaries = indexed(summary.get('worlds'), mapping, errors, 'summary')
    audits = indexed(audited.get('worlds'), mapping, errors, 'audit')
    errors.extend('archived_audit:' + value for value in audited.get('errors', []))
    rows = [one_world(w, summaries.get(w, {}), audits.get(w, {}), enabled, runs_root, errors, warnings) for w in WORLDS]
    finished = (summary.get('status') == 'completed' and audited.get('all_finished') is True
                and all(r['status'] is not None and r['status'] not in ACTIVE for r in rows))
    if not finished:
        warnings.append('batch_not_finished')
    totals = [r['total_seconds_including_evaluation'] for r in rows]
    all_usage = all(r['usage_complete'] for r in rows)
    calls = sum(r['calls'] for r in rows) if all(count(r['calls']) for r in rows) else None
    successes = sum(r['at_or_above_90'] for r in rows)
    aggregate = {'worlds_at_or_above_90': successes, 'evaluated_worlds': sum(r['evaluation_complete'] for r in rows),
        'timely_submitted_worlds': sum(r['timely_submission'] for r in rows),
        'batch_wall_seconds': elapsed(manifest.get('created_at'), manifest.get('finished_at')) if finished else None,
        'mean_total_seconds_per_experiment': sum(totals)/6 if all(number(t) and t >= 0 for t in totals) else None,
        'mean_score_completed_worlds': (sum(r['score'] for r in rows if r['evaluation_complete'] and r['score'] is not None)
              / sum(r['evaluation_complete'] and r['score'] is not None for r in rows)
              if any(r['evaluation_complete'] and r['score'] is not None for r in rows) else None),
        'calls': calls, 'usage_complete': all_usage,
        'completion_tokens_reported': sum(r['completion_tokens_reported'] for r in rows),
        'average_output_tokens_per_call': sum(r['completion_tokens_reported'] for r in rows)/calls if all_usage and calls else None,
        'max_call_output_tokens_reported': max((r['max_call_output_tokens_reported'] for r in rows if r['max_call_output_tokens_reported'] is not None), default=None),
        'diagnostic_tool': {key: sum(r['diagnostic_tool'][key] for r in rows)
                           if all(count(r['diagnostic_tool'][key]) for r in rows) else None
                           for key in ('calls', 'completed', 'successful', 'failed', 'unfinished')},
        'five_world_target_met': (finished and successes >= 5 and not errors and all_usage
                                  and all(r['timely_submission'] and r['evaluation_complete'] for r in rows))}
    return {'experiment_id': manifest.get('experiment_id'), 'batch_directory': str(batch),
            'diagnostics_enabled': enabled, 'all_finished': finished,
            'configuration': config, 'source_sha256': manifest.get('source_sha256', {}),
            'model_endpoints': manifest.get('model_endpoints'), 'workers': manifest.get('workers'),
            'protocol': manifest.get('protocol'), 'fixed_condition_checks': fixed,
            'input_sha256': {name: sha(path) for name, path in files.items() if path.is_file()},
            'aggregate': aggregate, 'worlds': rows, 'errors': errors, 'warnings': warnings}


def compare(off, on, runs_root=None):
    arms = {'off': arm(Path(off), False, runs_root), 'on': arm(Path(on), True, runs_root)}
    a, b = arms.values()
    differences = different_paths(normalize(a['configuration']), normalize(b['configuration']))
    ids_a, ids_b = ({r['run_id'] for r in value['worlds'] if isinstance(r['run_id'], str)} for value in (a, b))
    protocols = [copy.deepcopy(value['protocol'] or {}) for value in (a, b)]
    for protocol in protocols:
        protocol.pop('diagnostics_enabled', None)
    checks = {'only_diagnostic_toggle_differs': not differences,
              'same_frozen_source_hashes': bool(a['source_sha256']) and a['source_sha256'] == b['source_sha256'],
              'same_workers': a['workers'] == b['workers'], 'same_protocol_except_toggle': protocols[0] == protocols[1],
              'disjoint_six_world_attempts': len(ids_a) == len(ids_b) == 6 and not ids_a & ids_b,
              'different_batch_ids': a['experiment_id'] != b['experiment_id']}
    errors = ['comparison:' + key for key, value in checks.items() if not value]
    errors += [name + ':' + error for name, value in arms.items() for error in value['errors']]
    verified = not errors and all(value['all_finished'] for value in arms.values())
    delta = b['aggregate']['worlds_at_or_above_90'] - a['aggregate']['worlds_at_or_above_90']
    winner = ('on' if delta > 0 else 'off' if delta < 0 else 'tie') if verified else None
    return {'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
            'comparison_kind': 'one_six_world_batch_per_arm_no_best_of_selection', 'checks': checks,
            'configuration_differences_other_than_toggle': differences,
            'comparison_verified': verified, 'primary_metric': 'complete_timely_local_scores_at_or_above_90_out_of_six',
            'observed_primary_winner': winner, 'on_minus_off_success_count': delta,
            'arms': arms, 'errors': errors,
            'limitations': ['One fixed six-world batch per arm, one attempt per world. No cross-batch best-score selection.',
                'Same request seed does not guarantee identical hardware scheduling or deterministic model execution.',
                'Arms use distinct local model endpoints; endpoint and GPU allocation remain execution differences.',
                'Only a single-batch observed difference is reported, not a stable or statistically established causal effect.',
                'Unfinished worlds do not pass. Missing token usage is unknown, never imputed as zero.',
                'Scores use the existing local development evaluator, not official contest scoring.'],
            'read_only_scope': 'Reads existing archives; does not run models, simulation, fitting or evaluation or alter input files.'}


def report(result):
    def cell(value):
        if value is None:
            return '未知'
        return (f'{value:.2f}' if isinstance(value, float) else str(value)).replace('|', '\\|').replace('\n', ' ')
    lines = ['# E5 诊断工具开关对照', '',
        '同一六世界，每臂每世界一次；主指标为完整无噪声测评且及时提交的原始分数 ≥90 的世界数，不按显示取整、不跨批次挑分。', '',
        f"配置/来源/记录核对：{'通过' if result['comparison_verified'] else '未通过或未完成'}。主指标本批较优：{result['observed_primary_winner'] or '暂不可判定'}。", '',
        '固定条件：E5、10 能量、300 秒探索、每调用 4096 token、关闭思考、探索与独立测评无噪声、E3 主提示词、请求 seed=42。实际核对结果见 comparison.json。', '',
        '| 分组 | ≥90 世界 | 完成测评 | 整批墙钟秒 | 平均每次含测评秒 | 模型调用 | 平均每调用输出token | 诊断调用/成功/未结束 |',
        '|---|---:|---:|---:|---:|---:|---:|---|']
    for name, value in result['arms'].items():
        a = value['aggregate']; d = a['diagnostic_tool']
        lines.append('| ' + ' | '.join(cell(x) for x in [name, str(a['worlds_at_or_above_90'])+'/6', a['evaluated_worlds'],
            a['batch_wall_seconds'], a['mean_total_seconds_per_experiment'], a['calls'], a['average_output_tokens_per_call'],
            '/'.join(cell(d[k]) for k in ('calls', 'successful', 'unfinished'))]) + ' |')
    for name, value in result['arms'].items():
        lines += ['', f"## {name}: {value['experiment_id']}", '',
            f"模型端口：{', '.join(value.get('model_endpoints') or [])}。", '',
            '| 世界 | 状态 | 分数 | ≥90 | 探索秒 | 测评秒 | 总耗时秒 | 调用数 | 平均输出token | 最大输出token | 能量 | 诊断调用/成功 |',
            '|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|']
        for row in value['worlds']:
            d = row['diagnostic_tool']
            values = [row['world_id'], row['status'], row['score'], '是' if row['at_or_above_90'] else '否',
                row['exploration_seconds'], row['evaluation_seconds'], row['total_seconds_including_evaluation'],
                row['calls'], row['average_output_tokens_per_call'], row['max_call_output_tokens'], row['energy_used'],
                cell(d['calls'])+'/'+cell(d['successful'])]
            lines.append('| ' + ' | '.join(cell(v) for v in values) + ' |')
        if value['warnings']:
            lines += ['', '数据限制：' + '；'.join(value['warnings']) + '。']
    lines += ['', '整批墙钟按批次创建至结束计算，包含编排/排队；单次总耗时含独立测评、不含排队。'
              '平均输出 token = 已报告 completion_tokens / 所有请求次数（含重试），usage 不完整时留未知；最大值缺完整usage时也不宣称完整上限。', '',
              '这是每臂一批、固定六世界的观察结果；两臂使用不同 GPU/端口，seed 相同也不保证执行完全确定。'
              '不能据此宣称稳定因果或统计显著优势；未完成保留为未达标，不把未知分数补成 0 分。', '',
              '这是本地开发评测，不是官方比赛结果。']
    if result['errors']:
        lines += ['', '核对问题：', ''] + ['- ' + error for error in result['errors']]
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--off', type=Path, required=True)
    parser.add_argument('--on', type=Path, required=True)
    parser.add_argument('--runs-root', type=Path, help='Optional original runs directory for log cross-checks')
    parser.add_argument('--output', type=Path, required=True, help='Fresh directory receiving comparison.json and report.md')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('--output must be a fresh directory; existing records are never overwritten')
    result = compare(args.off.resolve(), args.on.resolve(), args.runs_root.resolve() if args.runs_root else None)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    (args.output / 'report.md').write_text(report(result), encoding='utf-8')
    print(json.dumps({'output': str(args.output.resolve()), 'comparison_verified': result['comparison_verified'],
        'off_successes': result['arms']['off']['aggregate']['worlds_at_or_above_90'],
        'on_successes': result['arms']['on']['aggregate']['worlds_at_or_above_90'],
        'observed_primary_winner': result['observed_primary_winner'], 'errors': result['errors']}, ensure_ascii=False))
    return 0 if result['comparison_verified'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
