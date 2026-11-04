"""Public interface traces only; no model reasoning or raw provider response."""
import json
from collections import Counter
from pathlib import Path
import statistics

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]


def read(p):
    return json.loads(p.read_text())


def directory(rid):
    p=ROOT/'runs'/rid
    return p if p.exists() else ROOT/'runs/.trash'/rid


def has_truncation(value):
    if isinstance(value, dict):
        return value.get('truncated') is True or any(has_truncation(v) for v in value.values())
    if isinstance(value, list):
        return any(has_truncation(v) for v in value)
    return False


def measure(summary, label):
    rows=[]
    for row in summary['rows']:
        if row['arm']!='code':continue
        p=directory(row['run_id'])
        tools=[json.loads(s) for s in (p/'tools.jsonl').read_text().splitlines() if s]
        statuses,errors,categories=Counter(),Counter(),Counter()
        sizes=[];print_only=0;warnings=[];truncated=0;duplicates=0;callback_reads=0
        before=0;seen_fit=False
        for t in tools:
            if t['tool']=='fit_law_and_rollout':seen_fit=True
            if t['tool']=='call_back' and 'field_path' in t['arguments']:callback_reads+=1
            if t['tool']!='run_code':continue
            if not seen_fit:before+=1
            ret=t['result'];data=ret.get('data') or {}
            sizes.append(len(json.dumps(ret,ensure_ascii=False,allow_nan=False).encode()))
            duplicates+=len(data.get('code','').encode())
            duplicates+=len(json.dumps(data['output_schema'],ensure_ascii=False).encode()) if 'output_schema' in data else 0
            eid=data.get('execution_id')
            if not eid:
                statuses['argument_or_runtime_error']+=1
                errors[(ret.get('error') or {}).get('code','unknown')]+=1
                categories['tool_argument_or_entry_error']+=1
                continue
            record=read(p/'records/code_execution'/f'{eid}.json')
            statuses[record['status']]+=1
            if record['status']!='success':
                error=record.get('error') or {}
                kind=error.get('type',record['status'])
                errors[kind]+=1
                message=error.get('message') or error.get('traceback','')
                if "name 'inputs' is not defined" in message or 'Define analyze(inputs)' in message:
                    category='script_entry_contract'
                elif 'not JSON serializable' in message:
                    category='scientific_type_serialization'
                elif kind=='OutputSchemaError':category='output_schema'
                elif record['status']=='timeout':category='timeout'
                elif record['status'] in ('protocol_error','unavailable'):
                    category='execution_environment_or_protocol_error'
                else:category='other_code_or_numerical_error'
                categories[category]+=1
            if record.get('warnings'):
                warnings.extend(record['warnings'])
                if any('No structured result' in w for w in record['warnings']):print_only+=1
            truncated+=has_truncation(data)
        rows.append({'experiment':label,'run_id':row['run_id'],'world_id':row['world_id'],
            'repeat':row['repeat'],'high_precision':row['high_precision'],
            'code_invocations':len(sizes),'statuses':dict(statuses),'errors':dict(errors),'error_categories':dict(categories),
            'response_bytes':sum(sizes),'median_response_bytes':statistics.median(sizes) if sizes else 0,
            'max_response_bytes':max(sizes,default=0),'response_sizes':sizes,
            'repeated_code_schema_bytes':duplicates,'print_only_calls':print_only,
            'truncated_responses':truncated,'field_reads':callback_reads,'code_before_first_formal_fit':before})
    return rows


def aggregate(rows):
    groups=[]
    for world in ['world_3','world_4','world_5','all']:
        subset=[r for r in rows if world=='all' or r['world_id']==world]
        status=sum((Counter(r['statuses']) for r in subset),Counter())
        errors=sum((Counter(r['errors']) for r in subset),Counter())
        categories=sum((Counter(r['error_categories']) for r in subset),Counter())
        sizes=[n for r in subset for n in r['response_sizes']]
        n=sum(status.values())
        groups.append({'world_id':world,'runs':len(subset),'invocations':n,
            'successful_executions':status['success'],'unsuccessful_invocations':n-status['success'],
            'unsuccessful_fraction':(n-status['success'])/n if n else None,
            'statuses':dict(status),'errors':dict(errors),'error_categories':dict(categories),'total_response_bytes':sum(sizes),
            'median_response_bytes':statistics.median(sizes) if sizes else 0,
            'mean_response_bytes':statistics.mean(sizes) if sizes else 0,
            'max_response_bytes':max(sizes,default=0),
            **{k:sum(r[k] for r in subset) for k in ['repeated_code_schema_bytes','print_only_calls','truncated_responses','field_reads']}})
    return groups


def main():
    s=read(OUT/'summary.json');assert s['status']=='completed_all_attempts' and len(s['rows'])==15
    old=read(ROOT/'benchmarks/E2/combined_summary.json')
    current_rows=measure(s,'E3');old_rows=measure(old,'E2')
    assert all(r['repeated_code_schema_bytes']==0 for r in current_rows)
    result={'E3':aggregate(current_rows),'E2':aggregate(old_rows),'runs':current_rows+old_rows,
            'notes':['E2/E3 are separate batches, not paired trajectories of the same model decisions.',
                     'truncated_responses counts explicit truncated=true flags recursively, including the older nested previews; it does not detect unmarked omissions.',
                     'Print-only scripts now count as execution success with an explicit missing-result warning; do not treat this definition change alone as improved scientific reasoning.',
                     'Response bytes measure tool message JSON, not billed tokens or total model context. Earlier code requests still remain in conversation history.']}
    (OUT/'interface_metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    for label in ['E2','E3']:
        print(label,json.dumps(result[label][-1],ensure_ascii=False))


if __name__=='__main__':main()
