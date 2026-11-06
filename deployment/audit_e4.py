"""Post-run E4/E5 audit; reads archives and writes only <batch>/audit.json.

Example (from physics_discovery, after the benchmark has finished):
    .venv/bin/python deployment/audit_e4.py \
        --batch experiments/E4/e4-qwen38-nothink-20261107-r01 --require-complete

Uses only the standard library: no Agent, simulator, model, evaluator or network
is invoked. Missing usage remains unknown, not zero. This is a local adapter
audit, not certification of the contest SDK or of the scientific answers.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile


ROOT = Path(__file__).resolve().parents[1]
ACTIVE = {'queued', 'starting', 'running', 'evaluating'}
WORLDS = [f'world_{n}' for n in range(1, 7)]
PROFILES = {'e4': {'group': 'E4', 'noise': True}, 'e5': {'group': 'E5', 'noise': False}}
NO_NOISE_REFERENCE = 'Unmodified v15 DevelopmentSimulator and fixed public validation cases; no noise'


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inside(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('archive_path_outside_root')
    return path


def read(path, errors, *, required=True):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise ValueError('not an object')
        return value
    except (OSError, ValueError):
        if required or path.exists():
            errors.append('missing_or_invalid_json:' + path.name)
        return {}


def events(path, errors):
    if not path.exists():
        return []
    result = []
    for line_number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError('not an object')
            result.append(value)
        except ValueError:
            errors.append(f'invalid_jsonl:{path.name}:{line_number}')
    return result


def instant(value):
    try:
        result = datetime.fromisoformat(value)
        return result if result.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def seconds(start, end):
    start, end = instant(start), instant(end)
    return (end - start).total_seconds() if start and end else None


def usage_valid(value):
    return (isinstance(value, dict)
            and all(type(value.get(k)) is int and value[k] >= 0
                    for k in ('prompt_tokens', 'completion_tokens', 'total_tokens'))
            and value['total_tokens'] >= value['prompt_tokens'] + value['completion_tokens'])


def model_audit(log, result_usage, errors, warnings):
    starts = [e for e in log if e.get('event') == 'request_started']
    ends = [e for e in log if e.get('event') == 'request']
    by_start, by_end = {}, {}
    for label, rows, target in (('started', starts, by_start), ('ended', ends, by_end)):
        for event in rows:
            call = event.get('call_number')
            if type(call) is not int or call <= 0 or call in target:
                errors.append('invalid_or_duplicate_model_call_' + label)
                continue
            target[call] = event
    calls = []
    sums = Counter()
    for call in sorted(set(by_start) | set(by_end)):
        start, end = by_start.get(call, {}), by_end.get(call, {})
        value = end.get('usage')
        valid = usage_valid(value)
        usage = {k: value[k] for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')} if valid else None
        if usage:
            sums.update(usage)
        cap = end.get('max_tokens', start.get('max_tokens'))
        thinking = (end or start).get('reasoning_parameters', {}).get('chat_template_kwargs', {}).get('enable_thinking')
        elapsed = end.get('elapsed_seconds')
        if not number(elapsed) or elapsed < 0:
            elapsed = None
        calls.append({'call_number': call, 'attempt': end.get('attempt', start.get('attempt')),
                      'started_at': start.get('started_at'), 'elapsed_seconds': elapsed,
                      'started_event_present': bool(start), 'terminal_event_present': bool(end),
                      'requested_max_tokens': cap, 'enable_thinking': thinking,
                      'http_status': end.get('http_status'), 'finish_reason': end.get('finish_reason'),
                      'error': end.get('error'), 'usage_complete': valid, 'usage': usage})
        if type(cap) is not int or not 0 < cap <= 4096:
            errors.append(f'call_{call}:invalid_requested_output_cap')
        if thinking is not False:
            errors.append(f'call_{call}:thinking_not_disabled_in_request')
        if valid and usage['completion_tokens'] > 4096:
            errors.append(f'call_{call}:reported_output_above_4096')
    reported = [c for c in calls if c['usage_complete']]
    reported_calls = result_usage.get('calls')
    count_consistent = type(reported_calls) is int and reported_calls == len(calls)
    if not count_consistent:
        errors.append('model_call_count_differs_from_result')
    for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
        if result_usage.get(key) != sums[key]:
            errors.append('reported_usage_total_differs_from_result:' + key)
    complete = bool(calls) and count_consistent and len(reported) == len(calls)
    if not complete:
        warnings.append('usage_incomplete: average across all calls and observed output compliance are unknown')
    elapsed_values = [c['elapsed_seconds'] for c in calls if c['elapsed_seconds'] is not None]
    elapsed_complete = len(elapsed_values) == len(calls)
    if not elapsed_complete:
        warnings.append('model_elapsed_incomplete: logged model time is a lower bound')
    elapsed_total = sum(elapsed_values)
    result_elapsed = result_usage.get('elapsed_seconds')
    if number(result_elapsed) and abs(result_elapsed - elapsed_total) > .01:
        errors.append('model_elapsed_total_differs_from_result')
    observed = [c['usage']['completion_tokens'] for c in reported]
    return {'calls': len(calls), 'result_reported_calls': reported_calls,
            'request_starts': len(starts), 'terminal_requests': len(ends),
            'usage_complete': complete, 'calls_with_usage': len(reported),
            'calls_without_usage': len(calls) - len(reported),
            'prompt_tokens_reported': sums['prompt_tokens'],
            'completion_tokens_reported': sums['completion_tokens'],
            'total_tokens_reported': sums['total_tokens'],
            'average_output_tokens_per_call': sums['completion_tokens'] / len(calls) if complete else None,
            'average_output_tokens_per_reported_call': sums['completion_tokens'] / len(reported) if reported else None,
            'max_call_output_tokens_reported': max(observed) if observed else None,
            'calls_above_4096': sum(v > 4096 for v in observed),
            'observed_output_cap_compliant': all(v <= 4096 for v in observed) if complete else None,
            'elapsed_seconds_logged': elapsed_total, 'elapsed_complete': elapsed_complete,
            'ttft_seconds': None, 'ttft_note': 'Per-call first-token timestamps are not logged; no TTFT or prefill time is inferred.',
            'per_call': calls}


def tool_audit(log, event_log):
    groups = defaultdict(lambda: {'calls': 0, 'failed_calls': 0, 'elapsed_seconds': 0., 'max_seconds': 0.})
    per_call = []
    for index, event in enumerate(log, 1):
        name = event.get('tool', 'unknown')
        elapsed = event.get('elapsed_seconds')
        elapsed = elapsed if number(elapsed) and elapsed >= 0 else None
        category = ('fit' if name == 'fit_law_and_rollout' else 'validate' if name == 'validate_law'
                    else 'observe' if name in ('insert_probe', 'observe_body') else name)
        row = groups[category]
        row['calls'] += 1
        failed = event.get('result', {}).get('ok') is not True
        row['failed_calls'] += failed
        if elapsed is not None:
            row['elapsed_seconds'] += elapsed
            row['max_seconds'] = max(row['max_seconds'], elapsed)
        per_call.append({'index': index, 'tool': name, 'elapsed_seconds': elapsed, 'ok': not failed})
    started = {e.get('tool_call_id'): e.get('name') for e in event_log if e.get('event') == 'tool_started'}
    ended = {e.get('tool_call_id') for e in event_log if e.get('event') == 'tool_finished'}
    unfinished = [{'tool_call_id': key, 'tool': name} for key, name in started.items() if key not in ended]
    return {'calls_logged': len(log), 'elapsed_seconds_logged': sum(g['elapsed_seconds'] for g in groups.values()),
            'elapsed_complete': not unfinished and all(c['elapsed_seconds'] is not None for c in per_call),
            'by_category': dict(groups), 'unfinished_tool_calls': unfinished, 'per_call': per_call,
            'note': 'Interrupted tools may have no tools.jsonl completion row; their duration is not invented.'}


def noise_audit(directory, mission, errors, *, enabled=True):
    task = mission.get('task', {})
    sigmas = {key: task.get(key) for key in ('position_noise_sigma', 'velocity_noise_sigma')}
    for key, value in sigmas.items():
        if not number(value) or (value <= 0 if enabled else value != 0):
            errors.append(('mission_noise_not_enabled:' if enabled else 'mission_noise_not_disabled:') + key)
    differences = {'position': [], 'velocity': []}
    matched = 0
    for path in sorted((directory / 'records' / 'probe').glob('*.json')):
        probe = read(path, errors)
        initial = probe.get('initial_conditions', {})
        for index, value in enumerate(probe.get('times', [])):
            if not number(value) or not number(initial.get('t0')) or abs(value-initial['t0']) > 1e-9:
                continue
            matched += 1
            for label, key, reference in (('position', 'r_obs', 'r0'), ('velocity', 'v_obs', 'v0')):
                observations = probe.get(key, [])
                control = initial.get(reference)
                if index >= len(observations) or not isinstance(control, list):
                    continue
                measured = observations[index]
                if (isinstance(measured, list) and len(measured) == len(control) == 2
                        and all(number(v) for v in measured + control)):
                    differences[label].extend(a-b for a, b in zip(measured, control))
    if not enabled:
        for label, values in differences.items():
            if any(abs(value) > 1e-10 for value in values):
                errors.append('noiseless_t0_readout_differs_from_launch:' + label)
    return {**sigmas, 'expected_noise_enabled': enabled,
            'noise_note': task.get('noise_note'), 't0_readings_compared': matched,
            't0_position_max_abs_difference': max(map(abs, differences['position']), default=None),
            't0_velocity_max_abs_difference': max(map(abs, differences['velocity']), default=None),
            'note': 'Measured t0 readings are compared with exact launch controls, without loading hidden truth. '
                    'Nonzero residuals corroborate noisy readouts; this small sample does not establish a Gaussian distribution.'}


def submission_audit(directory, result, metadata, event_log, errors):
    records = [read(p, errors) for p in sorted((directory / 'records' / 'submission').glob('*.json'))]
    accepted = [r for r in records if r.get('status') == 'accepted' and r.get('session_ended') is True]
    out = {'accepted_count': len(accepted), 'timely_pair': False, 'pair_source': None}
    if len(accepted) != 1:
        if result.get('status') == 'submitted' or accepted:
            errors.append('submitted_status_requires_one_accepted_record')
        return out
    selected = accepted[0]
    if (result.get('submission') or {}).get('submission_id') != selected.get('submission_id'):
        errors.append('result_submission_does_not_match_record')
    elapsed = selected.get('pair_validated_elapsed_seconds')
    at, deadline = instant(selected.get('pair_validated_at')), instant(metadata.get('exploration_deadline_at'))
    timely = (selected.get('submission_deadline_met') is True and number(elapsed)
              and 0 <= elapsed <= 300 and bool(at and deadline and at <= deadline))
    if not timely:
        errors.append('accepted_pair_not_verified_before_deadline')
    draft_id, submission_id = selected.get('draft_id'), selected.get('submission_id')
    tool = 'save_draft' if draft_id else 'submit'
    explicit = any(e.get('event') == 'tool_started' and e.get('name') == tool
                   and all(e.get('arguments', {}).get(k) == selected.get(k)
                           for k in ('law_id', 'claims', 'physical_explanation')) for e in event_log)
    if not explicit:
        errors.append('accepted_pair_missing_explicit_model_tool_call')
    artifacts = {}
    if not isinstance(submission_id, str) or not re.fullmatch(r'submission_[A-Za-z0-9_-]+', submission_id):
        errors.append('invalid_submission_id')
    else:
        for name in ('law.py', 'claims.json', 'law.json', 'physical_explanation.txt'):
            path = directory / 'submissions' / submission_id / name
            artifacts[name] = {'submission_sha256': digest(path) if path.is_file() else None}
            if not path.is_file():
                errors.append('missing_submission_artifact:' + name)
            if draft_id:
                if not isinstance(draft_id, str) or not re.fullmatch(r'draft_[A-Za-z0-9_-]+', draft_id):
                    errors.append('invalid_draft_id')
                    continue
                source = directory / 'drafts' / draft_id / name
                sha = digest(source) if source.is_file() else None
                artifacts[name].update(draft_sha256=sha, identical=sha is not None and sha == artifacts[name]['submission_sha256'])
                if not artifacts[name]['identical']:
                    errors.append('draft_submission_bytes_differ:' + name)
        claims_path = directory / 'submissions' / submission_id / 'claims.json'
        if read(claims_path, errors) != selected.get('claims'):
            errors.append('claims_artifact_differs_from_accepted_pair')
    out.update(timely_pair=timely, pair_source='timely_saved_draft' if draft_id else 'direct_submit',
               explicit_model_tool_call=explicit, submission_id=submission_id, law_id=selected.get('law_id'),
               pair_validated_at=selected.get('pair_validated_at'), submission_elapsed_seconds=elapsed,
               finalized_at=selected.get('finalized_at'), artifacts=artifacts)
    return out


def world_audit(root, world, run_id, *, ruleset='e4'):
    errors, warnings = [], []
    profile = PROFILES[ruleset]
    directory = inside(root / 'runs', run_id)
    config = read(directory / 'config.json', errors)
    metadata = read(directory / 'web.json', errors)
    result = read(directory / 'result.json', errors)
    mission = read(directory / 'mission.json', errors)
    env, model = config.get('environment', {}), config.get('model', {})
    task = mission.get('task', {})
    checks = {'ruleset_' + ruleset: env.get('ruleset') == ruleset, 'world_v15': env.get('world_set') == 'v15',
              'world_id': env.get('world_id') == world == task.get('world_id'),
              'energy_10': env.get('energy_budget') == 10, 'wall_300': env.get('wall_seconds') == 300,
              ('noise_on' if profile['noise'] else 'noise_off'): env.get('noise') is profile['noise'],
              'thinking_off': model.get('thinking') is False,
              'model_ruleset_' + ruleset: model.get('ruleset') == ruleset,
              'output_cap_le_4096': type(model.get('max_tokens_per_call')) is int and 0 < model['max_tokens_per_call'] <= 4096,
              'mission_energy_10': task.get('limits', {}).get('initial_energy') == 10,
              'mission_wall_300': task.get('limits', {}).get('wall_seconds') == 300}
    errors.extend('configuration:' + key for key, passed in checks.items() if not passed)
    model_log = events(directory / 'model_events.jsonl', errors)
    event_log = events(directory / 'events.jsonl', errors)
    model_data = model_audit(model_log, result.get('model_usage') or {}, errors, warnings)
    configured = [e for e in model_log if e.get('event') == 'configuration']
    if len(configured) != 1 or any(e.get('thinking') is not False or e.get('deployment') != 'local'
                                 or type(e.get('max_tokens_per_call')) is not int
                                 or not 0 < e['max_tokens_per_call'] <= 4096 for e in configured):
        errors.append('effective_model_configuration_not_verified')
    tools = tool_audit(events(directory / 'tools.jsonl', errors), event_log)
    submission = submission_audit(directory, result, metadata, event_log, errors)
    evaluation = read(directory / 'evaluation.json', errors, required=False)
    evaluation_after = seconds(metadata.get('exploration_finished_at'), metadata.get('evaluation_started_at'))
    if evaluation:
        evaluation_started = instant(metadata.get('evaluation_started_at'))
        calls_after = [c['call_number'] for c in model_data['per_call']
                       if instant(c['started_at']) and evaluation_started
                       and instant(c['started_at']) >= evaluation_started]
        eval_checks = {'after_exploration': evaluation_after is not None and evaluation_after >= 0,
                       'no_model_requests_after_evaluation_start': not calls_after,
                       'submission_identity': evaluation.get('submission_id') == submission.get('submission_id') and submission['accepted_count'] == 1,
                       'law_identity': evaluation.get('law_id') == submission.get('law_id'),
                       'world_identity': evaluation.get('world_id') == world and evaluation.get('world_set') == 'v15',
                       'ruleset_' + ruleset: evaluation.get('ruleset') == ruleset,
                       'energy_10': evaluation.get('score', {}).get('energy_budget') == 10,
                       'all_fixed_cases': evaluation.get('n_trajectories') == (32 if world == 'world_6' else 24),
                       'no_noise_truth_reference': evaluation.get('truth_reference') == NO_NOISE_REFERENCE,
                       'all_cases_completed': (evaluation.get('complete') is True and evaluation.get('failures') == []
                                               and evaluation.get('n_successful') == evaluation.get('n_trajectories'))}
        errors.extend('evaluation:' + key for key, passed in eval_checks.items() if not passed)
    else:
        eval_checks = {}
        if submission['accepted_count'] == 1:
            warnings.append('accepted_submission_has_no_evaluation_archive')
    exploration = metadata.get('exploration_wall_seconds')
    model_seconds = model_data['elapsed_seconds_logged']
    tools_seconds = tools['elapsed_seconds_logged']
    total = metadata.get('wall_seconds_including_evaluation')
    timing = {'total_seconds_including_evaluation': total, 'exploration_seconds': exploration,
              'evaluation_seconds': metadata.get('evaluation_wall_seconds'),
              'queue_seconds': seconds(metadata.get('created_at'), metadata.get('worker_started_at')),
              'model_seconds_logged': model_seconds, 'tools_seconds_logged': tools_seconds,
              'model_fraction_of_exploration': model_seconds / exploration if number(exploration) and exploration > 0 else None,
              'model_fraction_of_total': model_seconds / total if number(total) and total > 0 else None,
              'unattributed_exploration_seconds': exploration-model_seconds-tools_seconds if number(exploration) else None,
              'note': 'Total excludes queue; exploration includes final sealing and bookkeeping. Deadline compliance uses the timely pair, '
                      'not total or finalization time. Unattributed time may include interrupted tools; it is not measured Python overhead.'}
    noise = noise_audit(directory, mission, errors, enabled=profile['noise'])
    score = evaluation.get('score', {}).get('total')
    scored = evaluation.get('score', {}).get('status') == 'scored' and number(score) and 0 <= score <= 100
    return {'world_id': world, 'run_id': run_id, 'status': metadata.get('status', result.get('status')),
            'reason': result.get('reason'), 'configuration_checks': checks,
            'model_name': model.get('model'), 'model_endpoint': metadata.get('model_endpoint'),
            'output_limit_tokens': model.get('max_tokens_per_call'),
            'energy_remaining': result.get('budget', {}).get('energy_remaining'),
            'energy_used': 10-result['budget']['energy_remaining'] if number(result.get('budget', {}).get('energy_remaining')) else None,
            'timing': timing, 'model': model_data, 'tools': tools, 'noise': noise, 'submission': submission,
            'evaluation': {'checks': eval_checks, 'complete': evaluation.get('complete'),
                           'score': score, 'score_at_or_above_90': bool(scored and score >= 90 and eval_checks and all(eval_checks.values())),
                           'position_rmse': (evaluation.get('overall') or {}).get('position_rmse'),
                           'failures_count': len(evaluation.get('failures', [])), 'official_score': False},
            'errors': errors, 'warnings': warnings}


def audit(root, batch):
    errors = []
    manifest = read(batch / 'manifest.json', errors)
    source = []
    for name, expected in manifest.get('source_sha256', {}).items():
        path = inside(root, name)
        actual = digest(path) if path.is_file() else None
        source.append({'path': name, 'manifest_sha256': expected, 'current_sha256': actual, 'matches': actual == expected})
    if not source or not all(s['matches'] for s in source):
        errors.append('source_manifest_missing_or_current_source_mismatch')
    mapping = manifest.get('runs', {})
    if sorted(mapping) != WORLDS:
        errors.append('manifest_must_contain_exactly_six_worlds')
    ruleset = manifest.get('ruleset')
    profile = PROFILES.get(ruleset)
    if profile is None:
        errors.append('unsupported_manifest_ruleset')
    elif manifest.get('experiment_group') != profile['group']:
        errors.append('manifest_experiment_group_ruleset_mismatch')
    rows = ([world_audit(root, world, mapping[world], ruleset=ruleset) for world in WORLDS if world in mapping]
            if profile else [])
    errors.extend(row['world_id'] + ':' + error for row in rows for error in row['errors'])
    aggregate = {}
    for field in ('total_seconds_including_evaluation', 'exploration_seconds', 'evaluation_seconds', 'model_seconds_logged', 'tools_seconds_logged'):
        values = [r['timing'][field] for r in rows if number(r['timing'][field])]
        aggregate[field] = {'sum': sum(values), 'mean': sum(values)/len(values) if values else None, 'worlds_with_measurement': len(values)}
    calls = sum(r['model']['calls'] for r in rows)
    output = sum(r['model']['completion_tokens_reported'] for r in rows)
    complete_usage = bool(rows) and all(r['model']['usage_complete'] for r in rows)
    exploration = aggregate['exploration_seconds']['sum']
    aggregate.update(calls=calls, completion_tokens_reported=output,
                     average_output_tokens_per_call=output/calls if calls and complete_usage else None,
                     max_call_output_tokens_reported=max((r['model']['max_call_output_tokens_reported'] for r in rows
                                                          if r['model']['max_call_output_tokens_reported'] is not None), default=None),
                     calls_above_4096=sum(r['model']['calls_above_4096'] for r in rows),
                     usage_complete=complete_usage,
                     model_fraction_of_exploration=aggregate['model_seconds_logged']['sum']/exploration if exploration > 0 else None)
    target_count = sum(r['evaluation']['score_at_or_above_90'] for r in rows)
    all_finished = len(rows) == 6 and all(r['status'] not in ACTIVE and r['status'] is not None for r in rows)
    target_met = (all_finished and target_count >= 5 and not errors and complete_usage
                  and all(r['submission']['timely_pair'] for r in rows))
    return {'schema_version': 2, 'audited_at': datetime.now(timezone.utc).isoformat(),
            'experiment_id': manifest.get('experiment_id', batch.name),
            'experiment_group': profile['group'] if profile else None, 'ruleset': ruleset,
            'manifest_sha256': digest(batch/'manifest.json') if (batch/'manifest.json').is_file() else None,
            'all_finished': all_finished,
            'submitted_worlds': sum(r['submission']['accepted_count'] == 1 for r in rows),
            'timely_submitted_worlds': sum(r['submission']['timely_pair'] for r in rows),
            'evaluated_worlds': sum(r['evaluation']['complete'] is True for r in rows),
            'worlds_at_or_above_90': target_count, 'five_world_target_met': target_met,
            'target_note': 'At least five scores >=90 in this single six-world batch; no rounding or best-of-run selection. '
                           'Target confirmation also requires a clean audit, complete token usage and six timely submissions. '
                           'This is a user baseline target, not an official contest pass threshold.',
            'source_checks': source, 'source_note': 'Compares current on-disk source with the run manifest; cannot prove historical file immutability.',
            'aggregate': aggregate, 'worlds': rows, 'errors': errors,
            'read_only_scope': 'No execution, scoring, model requests or feedback to Agent; only this derived audit.json is written.',
            'official_score': False, 'official_sdk_compatible': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', required=True, help='Existing experiments/E4/<batch> or experiments/E5/<batch> directory')
    parser.add_argument('--require-complete', action='store_true', help='Fail if any of the six attempts is still active or missing')
    args = parser.parse_args()
    batch = Path(args.batch).resolve()
    if not batch.is_dir() or not any(batch.is_relative_to(ROOT / 'experiments' / p['group']) for p in PROFILES.values()):
        parser.error('--batch must be an existing directory under this project experiments/E4 or experiments/E5')
    result = audit(ROOT, batch)
    destination = batch / 'audit.json'
    # A unique atomic output avoids touching or replacing any original run record.
    with tempfile.NamedTemporaryFile('w', dir=batch, prefix='.audit-', suffix='.tmp', encoding='utf-8', delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    try:
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    print(json.dumps({'audit': str(destination), 'experiment_group': result['experiment_group'], 'all_finished': result['all_finished'],
                      'submitted_worlds': result['submitted_worlds'], 'timely_submitted_worlds': result['timely_submitted_worlds'],
                      'evaluated_worlds': result['evaluated_worlds'],
                      'worlds_at_or_above_90': result['worlds_at_or_above_90'],
                      'five_world_target_met': result['five_world_target_met'], 'errors': result['errors'],
                      'aggregate': result['aggregate']}, ensure_ascii=False))
    return 1 if result['errors'] or (args.require_complete and not result['all_finished']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
