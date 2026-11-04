"""Post-session E2 audit. Reads public scientific records, never private thoughts."""
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
from benchmark_code import source_hashes


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def lines(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s] if path.exists() else []


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def preview(value, depth=0):
    if isinstance(value, dict):
        if depth >= 4:
            return {'keys': list(value)[:20], 'key_count': len(value)}
        return {k: preview(v, depth + 1) for k, v in list(value.items())[:20]}
    if isinstance(value, list):
        return {'length': len(value), 'first_items': [preview(v, depth + 1) for v in value[:4]]}
    if isinstance(value, str):
        return value[:1000]
    return value


def wilson(k, n):
    z = 1.959963984540054
    center = (k/n + z*z/(2*n)) / (1+z*z/n)
    half = z * math.sqrt(k/n*(1-k/n)/n + z*z/(4*n*n)) / (1+z*z/n)
    return [max(0, center-half), min(1, center+half)]


def main():
    initial, manifest = read(OUT/'summary.json'), read(OUT/'manifest.json')
    summary = read(OUT/'combined_summary.json', initial)
    recovery = read(OUT/'recovery-1/summary.json', {'rows': []})
    assert summary['status'] == initial['status'] == 'completed_all_attempts'
    assert len(summary['rows']) == len({r['run_id'] for r in summary['rows']}) == 30
    attempts = initial['rows'] + recovery['rows']
    if recovery['rows']:
        assert recovery['status'] == 'completed_all_attempts' and len(recovery['rows']) == 21
        for row in recovery['rows']:
            original = next(r for r in initial['rows'] if r['run_id'] == row['original_run_id'])
            assert original['reason'] == 'http_status_402'
    assert source_hashes(ROOT) == manifest['source_sha256']
    main_prompt = (ROOT/'shore_agent/prompts/main.txt').read_text()
    code_prompt = main_prompt.replace('7 个工具', '8 个工具').replace(
        '不可访问任意文件、Shell、网络、源码或任意 Python。',
        '代码只可通过run_code在隔离环境执行，不可访问宿主文件、网络或仿真源码。')
    code_prompt += '\n\n' + (ROOT/'shore_agent/prompts/code.txt').read_text()
    diagnostics, audit = [], []
    for row in attempts:
        folder = ROOT/'runs'/row['run_id']
        if not folder.exists():
            folder = ROOT/'runs/.trash'/row['run_id']
        assert folder.is_dir(), f'Missing raw record: {row["run_id"]}'
        config = read(folder/'config.json')
        registered = next(r for r in manifest['rows'] if r['run_id'] == row.get('original_run_id', row['run_id']))
        assert config == registered['configuration']
        # Extract the initial public system prompt only; no assistant reasoning is exported.
        message_file = folder/'model_messages.jsonl'
        prompt_hash = None
        if message_file.exists():
            with message_file.open() as stream:
                initial_prompt = json.loads(stream.readline())['messages'][0]['content']
            assert initial_prompt == (code_prompt if row['arm'] == 'code' else main_prompt)
            prompt_hash = hashlib.sha256(initial_prompt.encode()).hexdigest()
        tools = lines(folder/'tools.jsonl')
        assert row['arm'] != 'baseline' or not any(t['tool'] == 'run_code' for t in tools)
        law_records = [read(p) for p in (folder/'records/law').glob('*.json')]
        validations = [read(p) for p in (folder/'records/validation').glob('*.json')]
        errors = Counter()
        for index, tool in enumerate(tools):
            if tool['tool'] != 'run_code':
                continue
            result = tool.get('result') or {}
            returned = result.get('data') or {}
            execution_id = returned.get('execution_id')
            if not execution_id:
                errors[(result.get('error') or {}).get('code', 'unknown')] += 1
                audit.append({'run_id': row['run_id'], 'tool_index': index,
                              'status': 'argument_or_runtime_error', 'error': result.get('error')})
                continue
            execution = read(folder/'records/code_execution'/(execution_id+'.json'))
            sandbox = execution['sandbox']
            assert sandbox['image_id'] == manifest['sandbox']['image_id']
            assert sandbox['network'] == 'none' and sandbox['host_mounts'] is False
            assert sandbox['cpus'] == 1 and sandbox['memory_mb'] == 1024
            assert 0 < sandbox['timeout_seconds'] <= 90
            artifacts = folder/'code_executions'/execution_id
            assert (artifacts/'analysis.py').read_text() == execution['code']
            inputs = read(artifacts/'inputs.json')
            for alias, provenance in execution['inputs'].items():
                assert [digest(v) for v in inputs[alias]] == provenance['sha256']
            for item in execution['artifacts']:
                assert hashlib.sha256((artifacts/'artifacts'/item['name']).read_bytes()).hexdigest() == item['sha256']
            error_type = (execution.get('error') or {}).get('type')
            if execution['status'] != 'success':
                errors[error_type or execution['status']] += 1
            following = []
            for next_tool in tools[index+1:index+6]:
                args = next_tool.get('arguments') or {}
                following.append({'tool': next_tool['tool'],
                    'law_spec': args.get('law_spec'), 'parameter_spec': args.get('parameter_spec'),
                    'law_id': args.get('law_id'), 'probe_count': len(args.get('probes', []))})
            audit.append({'run_id': row['run_id'], 'world_id': row['world_id'], 'tool_index': index,
                'execution_id': execution_id, 'status': execution['status'],
                'inputs': execution['inputs'], 'code': execution['code'], 'code_sha256': hashlib.sha256(execution['code'].encode()).hexdigest(),
                'output_schema': execution['output_schema'], 'result_preview': preview(execution.get('result')),
                'stdout_preview': execution.get('stdout', '')[:2000], 'error': execution.get('error'),
                'elapsed_seconds': execution.get('elapsed_seconds'), 'compute_seconds': execution.get('compute_seconds'),
                'cpu_seconds_reported': execution.get('cpu_seconds_reported'),
                'artifacts': execution['artifacts'], 'sandbox': execution.get('sandbox'),
                'following_tools': following,
                'full_record_sha256': hashlib.sha256((folder/'records/code_execution'/(execution_id+'.json')).read_bytes()).hexdigest()})
        filenames = ('config.json','mission.json','result.json','evaluation.json','tools.jsonl','model_events.jsonl')
        diagnostics.append({'run_id': row['run_id'], 'world_id': row['world_id'], 'arm': row['arm'],
            'raw_record_location':str(folder.relative_to(ROOT)),
            'repeat': row['repeat'], 'high_precision': row['high_precision'], 'system_prompt_sha256': prompt_hash,
            'final_usage': read(folder/'result.json', {}).get('model_usage'), 'code_error_types': dict(errors),
            'laws': [{k: law.get(k) for k in ('law_id','law_spec','fitted_parameters','train_probe_ids','fit_status','message','refinement')}
                     | {'errors': (law.get('errors') or {}).get('overall')} for law in sorted(law_records, key=lambda l: int(l['law_id'][4:]))],
            'validations': [{k: val.get(k) for k in ('validation_id','law_id','test_probe_ids')}
                            | {'errors': (val.get('errors') or {}).get('overall')} for val in validations],
            'artifact_sha256': {name:hashlib.sha256((folder/name).read_bytes()).hexdigest()
                               for name in filenames if (folder/name).exists()}})
    groups = []
    for group in summary['groups']:
        rows = [r for r in summary['rows'] if r['arm'] == group['arm']
                and (group['world_id'] == 'all' or r['world_id'] == group['world_id'])]
        groups.append({**group, 'high_precision_wilson_95': wilson(group['high_precision'], group['scheduled']),
                       'median_api_seconds': statistics.median(r['api_elapsed_seconds'] for r in rows),
                       'median_code_seconds': statistics.median(r['code_elapsed_seconds'] for r in rows),
                       'total_code_cpu_seconds_reported': sum(r['code_cpu_seconds_reported'] for r in rows),
                       'median_model_calls': statistics.median(r['calls'] for r in rows),
                       'median_tokens': statistics.median(r['tokens'] for r in rows)})
    requests = [request for row in attempts for request in row['api_requests']]
    retained_ids = {r['run_id'] for r in summary['rows']}
    retained_code = [e for e in audit if e['run_id'] in retained_ids]
    report = {'experiment_id':'E2','source_unchanged':True, 'groups': groups, 'runs': diagnostics,
              'initial_attempt_groups': initial['groups'], 'total_attempts':len(attempts),
              'retained_cell_run_ids':[r['run_id'] for r in summary['rows']],
              'account_quota_interrupted_attempts':sum(r['reason']=='http_status_402' for r in attempts),
              'http_status_counts':dict(Counter(str(r.get('http_status')) for r in requests)),
              'finish_reason_counts':dict(Counter(str(r.get('finish_reason')) for r in requests)),
              'response_models':sorted({r['response_model'] for r in requests if r.get('response_model')}),
              'system_fingerprints':sorted({r['system_fingerprint'] for r in requests if r.get('system_fingerprint')}),
              'code_status_counts':dict(Counter(e['status'] for e in audit)),
              'code_error_types':dict(sum((Counter(d['code_error_types']) for d in diagnostics), Counter())),
              'retained_code_status_counts':dict(Counter(e['status'] for e in retained_code)),
              'retained_code_error_types':dict(sum((Counter(d['code_error_types']) for d in diagnostics if d['run_id'] in retained_ids), Counter())),
              'all_attempt_tokens':sum(r['tokens'] for r in attempts),
              'retained_cell_tokens':sum(r['tokens'] for r in summary['rows']),
              'quota_interrupted_attempt_tokens':sum(r['tokens'] for r in attempts if r['reason']=='http_status_402'),
              'code_result_preview_note':'Previews truncate nested arrays/dictionaries/text. Full immutable records remain in runs/; SHA256 recorded.'}
    for name, value in [('diagnostics.json', report), ('code_audit.json', audit)]:
        (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k:report[k] for k in ('source_unchanged','http_status_counts','code_status_counts','code_error_types')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
