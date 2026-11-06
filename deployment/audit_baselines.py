"""Audit server-local baselines against their raw submissions and evaluations."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
result = {'audited_at': datetime.now(timezone.utc).isoformat(), 'batches': [], 'errors': []}
for path in sorted((root / 'experiments').glob('v15-local-*/summary.json')):
    data = json.loads(path.read_text())
    batch = {'id': data['experiment_id'], 'status': data['status'], 'worlds': []}
    model = data['configuration']['model']
    batch['model'] = {key: model[key] for key in ('model', 'deployment', 'thinking', 'base_url')}
    errors = []
    if model['thinking'] is not False or model['deployment'] != 'local':
        errors.append('model_settings_mismatch')
    if model['base_url'] not in [f'http://127.0.0.1:{port}/v1' for port in (8000, 8001, 8002)]:
        errors.append('unexpected_endpoint')
    for name, digest in data['source_sha256'].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            errors.append('source_changed:' + name)
    if sorted(row['world_id'] for row in data['worlds']) != [f'world_{n}' for n in range(1, 7)]:
        errors.append('world_set_mismatch')
    for row in data['worlds']:
        entry = {key: row.get(key) for key in ('world_id', 'run_id', 'status', 'reason',
                 'calls', 'tokens', 'completion_tokens', 'energy_used', 'evaluation_complete',
                 'n_test_trajectories', 'wall_seconds_including_evaluation')}
        events = root / 'runs' / row['run_id'] / 'model_events.jsonl'
        requests = [json.loads(line) for line in events.read_text().splitlines()
                    if line.strip()] if events.exists() else []
        reported = [event for event in requests if event.get('event') == 'request'
                    and isinstance(event.get('usage'), dict)]
        entry['requests_with_reported_usage'] = len(reported)
        entry['requests_without_reported_usage'] = (row.get('calls') or 0) - len(reported)
        entry['average_output_tokens_per_call'] = (
            row['completion_tokens'] / row['calls'] if row.get('calls')
            and len(reported) == row['calls'] else None)
        if row['status'] not in ('running', 'queued', 'starting', 'evaluating') and sum(
                event['usage']['completion_tokens'] for event in reported) != (row.get('completion_tokens') or 0):
            errors.append(row['world_id'] + ':output_token_total_mismatch')
        entry['score'] = (row.get('evaluation_score') or {}).get('total')
        entry['position_rmse'] = (row.get('independent_rmse') or {}).get('position_rmse')
        if row['status'] == 'submitted':
            directory = root / 'runs' / row['run_id']
            raw = json.loads((directory / 'result.json').read_text())
            evaluation = json.loads((directory / 'evaluation.json').read_text())
            submission = raw['submission']
            checks = {
                'accepted': submission['status'] == 'accepted' and submission['session_ended'] is True,
                'submission_matches': evaluation['submission_id'] == submission['submission_id'],
                'law_matches': evaluation['law_id'] == submission['law_id'],
                'world_matches': evaluation['world_id'] == row['world_id'] and evaluation['world_set'] == 'v15',
                'full_cases': evaluation['n_trajectories'] == (32 if row['world_id'] == 'world_6' else 24),
                'complete': evaluation['complete'] is True and not evaluation['failures'],
                'rmse_matches': evaluation['overall'] == row['independent_rmse'],
            }
            entry['checks'] = checks
            errors.extend(row['world_id'] + ':' + name for name, passed in checks.items() if not passed)
        batch['worlds'].append(entry)
    batch['errors'] = errors
    result['errors'].extend(batch['id'] + ':' + error for error in errors)
    result['batches'].append(batch)
result['all_finished'] = len(result['batches']) == 3 and all(b['status'] == 'completed' for b in result['batches'])
result['evaluated_worlds'] = sum(w['evaluation_complete'] for b in result['batches'] for w in b['worlds'])
destination = root / 'experiments' / 'server-baseline-audit.json'
destination.write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps({'all_finished': result['all_finished'], 'evaluated_worlds': result['evaluated_worlds'],
                  'errors': result['errors']}, ensure_ascii=False))
if result['errors'] or ('--require-complete' in sys.argv and not result['all_finished']):
    raise SystemExit(1)
