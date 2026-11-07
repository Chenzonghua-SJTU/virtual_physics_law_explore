"""One six-world, B-only observation replay against isolated warmed service 8891.

The service receives training probes only. Existing exact holdout labels are
used afterwards for diagnostics, never for search, fitting or answer selection.
This script never starts a service, changes a model deployment or runs an Agent.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import signal
import sys
import threading
import time
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from deployment.check_symbolic_identifiability import aligned_data, evaluate_search, write_json
from shore_agent.symbolic_service import search_remote

ENDPOINT='http://127.0.0.1:8891'
BUDGET=47
WORKERS=4
SEED=42
WORLD_IDS={f'world_{i}' for i in range(1,7)}


def preflight(dataset_file,output,*,opener=urlopen):
    output=Path(output).resolve()
    if output.exists() or output.is_symlink():
        raise ValueError('Offline replay output already exists; no retries or overwrite')
    if any(output==ROOT/name or output.is_relative_to(ROOT/name) for name in ('runs','shore_agent','shore_v15','shore_sim')):
        raise ValueError('Offline evidence must remain outside Agent runs and source packages')
    bundle=json.loads(Path(dataset_file).read_text())
    datasets=bundle['datasets']
    if len(datasets)!=6 or {d['world_id'] for d in datasets}!=WORLD_IDS:
        raise ValueError('Expected exactly one dataset for each development world')
    for dataset in datasets:
        train,heldout=dataset['train_probes'],dataset['heldout_probes']
        if len(train)!=24 or len(heldout)!=8 or any(len(p['times'])!=50 for p in train+heldout):
            raise ValueError('Registered dataset requires 24/8 trajectories with 50 observations')
        if {p['probe_id'] for p in train}&{p['probe_id'] for p in heldout}:
            raise ValueError('Training and heldout probes must be disjoint')
        if any(set(p)-{'probe_id','initial_conditions','times','r_obs','v_obs'} for p in train):
            raise ValueError('Search probes must not contain exact acceleration or diagnostic fields')
        aligned_data(dataset,'train'); aligned_data(dataset,'heldout')
    with opener(ENDPOINT+'/health',timeout=5) as response:
        if response.status!=200: raise RuntimeError('Isolated symbolic service unavailable')
        health=json.load(response)
    if (health.get('ready')!=4 or health.get('busy')!=0
            or health.get('actual_julia_threads')!=[4]*4):
        raise RuntimeError('Isolated service requires four idle, warmed four-thread workers')
    warmup=health.get('worker_warmup',[])
    if len(warmup)!=4 or any(
        {(s.get('stage'),s.get('maxsize')) for s in w.get('warmup_stages',[])}!={('algebra',24),('full',48)}
        for w in warmup):
        raise RuntimeError('Both algebra24 and full48 operator enums must be warmed')
    return datasets,health


def replay_one(dataset,output,stop_requested=None,search=search_remote):
    world=dataset['world_id']
    result={'world_id':world,'mode':'B_velocity_difference_only','status':'queued',
            'requested_search_seconds':BUDGET,'model_calls':0,'agent_missions':0}
    file=Path(output)/(world+'.json')
    if stop_requested is not None and stop_requested():
        result.update(status='not_started',reason='study_interrupted')
        write_json(file,result)
        return result
    started=time.monotonic()
    result['status']='searching'
    write_json(file,result)
    try:
        begin=time.monotonic()
        # This is the complete request boundary. No world ID, formula, exact
        # acceleration or independent holdout data enters the production tool.
        raw=search(dataset['train_probes'],BUDGET,endpoint=ENDPOINT,random_state=SEED)
        result.update(search_result=raw,search_client_seconds=time.monotonic()-begin,status='evaluating')
        write_json(file,result)
        begin=time.monotonic()
        result['diagnostics']=evaluate_search(raw,dataset)
        result.update(evaluation_seconds=time.monotonic()-begin,status='completed')
    except Exception as exc:
        result.update(status='error',error={'type':type(exc).__name__,'message':str(exc)[:1000]})
    result['total_seconds']=time.monotonic()-started
    write_json(file,result)
    return result


def run(dataset_file,output,*,opener=urlopen,search=search_remote,stop_requested=None):
    datasets,health=preflight(dataset_file,output,opener=opener)
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    sources=set(str(p.relative_to(ROOT)) for p in (ROOT/'shore_agent').glob('symbolic*.py'))
    sources.update(('deployment/replay_e8_symbolic.py','deployment/check_symbolic_identifiability.py',
                    'shore_agent/expressions.py','experiments/E5/e8-protocol.json'))
    summary={'kind':'e8_single_observation_replay_not_agent_score','status':'running',
             'created_at':datetime.now(timezone.utc).isoformat(),'worlds':[],
             'dataset_sha256':hashlib.sha256(Path(dataset_file).read_bytes()).hexdigest(),
             'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(sources)},
             'service_endpoint':ENDPOINT,'service_health_at_start':health,'mode':'B_only',
             'attempts_per_world':1,'automatic_retries':False,'workers':WORKERS,
             'requested_search_seconds':BUDGET,'heldout_used_for_selection':False,
             'model_calls':0,'agent_missions':0}
    write_json(output/'summary.json',summary)
    started=time.monotonic()
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures=[executor.submit(replay_one,dataset,output,stop_requested,search) for dataset in datasets]
        for future in as_completed(futures):
            result=future.result()
            summary['worlds'].append(result)
            write_json(output/'summary.json',summary)
            pair=result.get('diagnostics',{}).get('raw_training_best_pair') or {}
            print(json.dumps({'world_id':result['world_id'],'status':result['status'],
                              'search_seconds':result.get('search_client_seconds'),
                              'raw_training_best_pair_heldout':pair.get('heldout')}),flush=True)
    summary.update(status='interrupted' if stop_requested is not None and stop_requested() else 'completed',
                   total_seconds=time.monotonic()-started)
    write_json(output/'summary.json',summary)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    stopped=threading.Event()
    previous={sig:signal.signal(sig,lambda *_:stopped.set()) for sig in (signal.SIGINT,signal.SIGTERM)}
    try:
        run(args.dataset,args.output,stop_requested=stopped.is_set)
    finally:
        for sig,handler in previous.items():signal.signal(sig,handler)


if __name__=='__main__':
    main()
