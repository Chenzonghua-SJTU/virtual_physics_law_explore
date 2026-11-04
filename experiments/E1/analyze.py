"""Read-only post-E1 analysis; exports public results and aggregate metadata only."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path.insert(0, str(ROOT))
from benchmark_reasoning import source_hashes


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def lines(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s] if path.exists() else []


def write(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def wilson(k, n):
    z = 1.959963984540054
    c = (k / n + z*z / (2*n)) / (1 + z*z/n)
    d = z * math.sqrt(k/n * (1-k/n)/n + z*z/(4*n*n)) / (1+z*z/n)
    return [max(0, c-d), min(1, c+d)]


summary = read(OUT / 'summary.json')
manifest = read(OUT / 'manifest.json')
assert summary['status'] == 'completed_all_attempts'
assert len(summary['rows']) == 45 and len({r['run_id'] for r in summary['rows']}) == 45
assert source_hashes(ROOT) == manifest['source_sha256'], 'Frozen experiment source changed'
diagnostics = []
for row in summary['rows']:
    folder = ROOT / 'runs' / row['run_id']
    messages = read(folder / 'messages.json', [])
    replies = [m for m in messages if m.get('role') == 'assistant']
    # Only sizes and booleans leave this loop; private thoughts stay on disk.
    response_metadata = [{
        'content_chars': len(m.get('content') or ''),
        'reasoning_chars': len(m.get('reasoning_content') or m.get('reasoning') or ''),
        'tool_calls': len(m.get('tool_calls') or [])} for m in replies]
    laws = [read(p) for p in (folder / 'records/law').glob('*.json')]
    validations = [read(p) for p in (folder / 'records/validation').glob('*.json')]
    requests = row['api_requests']
    final_usage = read(folder / 'result.json', {}).get('model_usage', {})
    artifact_names = ('config.json', 'mission.json', 'result.json', 'evaluation.json', 'tools.jsonl', 'model_events.jsonl')
    diagnostics.append({
        'run_id': row['run_id'], 'world_id': row['world_id'], 'effort': row['effort'],
        'repeat': row['repeat'], 'high_precision': row['high_precision'],
        'final_model_usage': final_usage,
        'response_count': len(replies),
        'progress_response_count': sum(bool(m['content_chars']) for m in response_metadata),
        'tool_only_response_count': sum(m['tool_calls'] > 0 and not m['content_chars'] for m in response_metadata),
        'no_tool_response_count': sum(not m['tool_calls'] for m in response_metadata),
        'reasoning_response_count': sum(bool(m['reasoning_chars']) for m in response_metadata),
        'response_metadata': response_metadata,
        'http_status_counts': dict(Counter(str(r.get('http_status', 'none')) for r in requests)),
        'api_error_counts': dict(Counter(r['error'] for r in requests if r.get('error'))),
        'finish_reason_counts': dict(Counter(str(r.get('finish_reason', 'none')) for r in requests)),
        'returned_models': sorted({r['response_model'] for r in requests if r.get('response_model')}),
        'system_fingerprints': sorted({r['system_fingerprint'] for r in requests if r.get('system_fingerprint')}),
        'laws': [{k: law.get(k) for k in ('law_id', 'law_spec', 'fitted_parameters', 'train_probe_ids',
                    'converged', 'fit_status', 'message', 'objective_calls', 'refinement')} | {'errors': (law.get('errors') or {}).get('overall')}
                 for law in sorted(laws, key=lambda l: int(l['law_id'].split('_')[-1]))],
        'validations': [{k: v.get(k) for k in ('validation_id', 'law_id', 'test_probe_ids')}
                        | {'errors': (v.get('errors') or {}).get('overall')} for v in validations],
        'artifact_sha256': {name: hashlib.sha256((folder/name).read_bytes()).hexdigest()
                           for name in artifact_names if (folder/name).exists()}})

groups = []
for group in summary['groups']:
    subset = [r for r in summary['rows'] if r['effort'] == group['effort']
              and (group['world_id'] == 'all' or r['world_id'] == group['world_id'])]
    diag = [r for r in diagnostics if r['effort'] == group['effort']
            and (group['world_id'] == 'all' or r['world_id'] == group['world_id'])]
    progress_fractions = [r['progress_response_count']/r['response_count'] for r in diag if r['response_count']]
    groups.append({**group,
        'high_precision_wilson_95': wilson(group['high_precision'], group['scheduled']),
        'median_calls': statistics.median(r['calls'] for r in subset),
        'median_completion_tokens': statistics.median(r['completion_tokens'] for r in subset),
        'median_progress_response_fraction': statistics.median(progress_fractions) if progress_fractions else None})

totals = {'attempts': 45, 'submitted': sum(r['accepted_submission'] for r in summary['rows']),
          'evaluated': sum(r['independent_evaluation_complete'] for r in summary['rows']),
          'high_precision': sum(r['high_precision'] for r in summary['rows']),
          'api_calls': sum(r['calls'] for r in summary['rows']),
          'tokens': sum(r['tokens'] for r in summary['rows']),
          'conservative_reserved_tokens': sum(r['final_model_usage'].get('conservative_reserved_tokens', 0) for r in diagnostics),
          'http_status_counts': dict(sum((Counter(r['http_status_counts']) for r in diagnostics), Counter())),
          'api_errors': dict(sum((Counter(r['api_error_counts']) for r in diagnostics), Counter())),
          'tool_errors': dict(sum((Counter(r['tool_error_counts']) for r in summary['rows']), Counter())),
          'fit_status_counts': dict(Counter(law['fit_status'] for r in diagnostics for law in r['laws'])),
          'numerical_wall_time_fits': [{'run_id': r['run_id'], 'law_id': law['law_id']}
                                     for r in diagnostics for law in r['laws']
                                     if 'wall-time' in (law.get('message') or '')],
          'wrong_claims': dict(Counter(check['field'] for r in summary['rows']
                                      for check in (r.get('score') or {}).get('claim_checks', [])
                                      if not check.get('correct'))),
          'returned_models': sorted({m for r in diagnostics for m in r['returned_models']})}
write('diagnostics.json', {'experiment_id': 'E1', 'source_unchanged': True,
                         'totals': totals, 'groups': groups, 'runs': diagnostics})
print(json.dumps({'totals': totals, 'pooled_groups': [g for g in groups if g['world_id'] == 'all']}, ensure_ascii=False, indent=2))
