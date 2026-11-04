"""E2 recovery amendment: retry only 402-aborted cells, preserving every attempt.

User confirmed restored API quota after the first batch ended. This controller
does not replace or edit that batch, and never retries completed scientific misses.
"""
import copy
import getpass
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import benchmark_code as bench
from shore_agent.code_execution import sandbox_info
from shore_agent.web_jobs import _write


def run(key):
    parent = ROOT/'benchmarks/E2'
    initial = json.loads((parent/'summary.json').read_text())
    registered = json.loads((parent/'manifest.json').read_text())
    assert initial['status'] == 'completed_all_attempts'
    jobs = [dict(row, original_run_id=row['run_id'], run_id=row['run_id'].replace('E2-', 'E2R1-', 1))
            for row in registered['rows']
            if next(r for r in initial['rows'] if r['run_id'] == row['run_id'])['reason'] == 'http_status_402']
    assert len(jobs) == 21
    out, staging = parent/'recovery-1', ROOT/'runs/.E2R1-active'
    if out.exists() or staging.exists() or any((ROOT/'runs'/j['run_id']).exists() for j in jobs):
        raise ValueError('Recovery already exists; never silently replace attempts')
    assert bench.source_hashes(ROOT) == registered['source_sha256']
    assert sandbox_info(jobs[0]['configuration'].get('code_execution')) == registered['sandbox']
    out.mkdir()
    staging.mkdir(mode=0o700)
    manifest = {'experiment_id':'E2R1','parent_experiment':'E2','started_at':bench.now(),'status':'running',
        'amendment':'User confirmed restored quota. Retry only 21 HTTP402 cells from fresh sessions; keep all 9 completed sessions including scientific misses. No outcome-based reruns.',
        'frozen_git_commit':registered['git_commit'], 'source_sha256':registered['source_sha256'],
        'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'sandbox':registered['sandbox'], 'concurrency':3,'numerical_threads':1,
        'automatic_reruns':False, 'rows':[{**j, 'state':'pending'} for j in jobs]}
    keys = ('world_id','arm','repeat','order','run_id','original_run_id')
    summary = {'experiment_id':'E2R1','started_at':manifest['started_at'],'status':'running',
               'rows':[{**{k:j[k] for k in keys}, 'status':'pending'} for j in jobs]}
    active, index = {}, 0

    def checkpoint():
        summary['groups'] = bench.aggregate(summary['rows'])
        _write(out/'manifest.json', manifest)
        _write(out/'summary.json', summary)

    checkpoint()
    try:
        while index < len(jobs) or active:
            while index < len(jobs) and len(active) < 3:
                assert bench.source_hashes(ROOT) == registered['source_sha256']
                assert sandbox_info(jobs[index]['configuration'].get('code_execution')) == registered['sandbox']
                job = jobs[index]
                directory = staging/job['run_id']
                directory.mkdir(mode=0o700)
                _write(directory/'config.json', job['configuration'])
                _write(directory/'web.json', {'id':job['run_id'],'created_at':bench.now(),'status':'running',
                    'world_id':job['world_id'],'mode':'autonomous_discovery','experiment_id':'E2R1',
                    'reasoning_effort':'high','arm':job['arm'],'repeat':job['repeat'],'original_run_id':job['original_run_id']})
                env = dict(os.environ)
                env.pop('DEEPSEEK_API_KEY', None)
                env.update({name:'1' for name in bench.THREAD_VARS})
                env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(ROOT))
                process = subprocess.Popen([sys.executable,'-u','-m','shore_agent.web_worker','--run-dir',str(directory)],
                    cwd=ROOT,env=env,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                    text=True,start_new_session=True)
                active[index]=(process,time.monotonic(),directory)
                process.stdin.write(json.dumps({'api_key':key})+'\n')
                process.stdin.close()
                manifest['rows'][index].update(state='running',started_at=bench.now(),worker_pid=process.pid)
                summary['rows'][index]['status']='running'
                index+=1
                print(f'E2R1 {index}/21 START {job["run_id"]}',flush=True)
                checkpoint()
            for slot,(process,start,directory) in list(active.items()):
                code=process.poll()
                if code is None:
                    continue
                job={k:jobs[slot][k] for k in keys}
                row=bench.collect(directory,job,time.monotonic()-start,code)
                directory.rename(ROOT/'runs'/job['run_id'])
                summary['rows'][slot]=row
                manifest['rows'][slot].update(state='finished',finished_at=bench.now(),returncode=code)
                del active[slot]
                checkpoint()
                print(f'E2R1 DONE {job["run_id"]} status={row["status"]} rmse={row["position_rmse"]} reason={row["reason"]}',flush=True)
                # Do not burn through the remaining schedule if quota fails again.
                if row.get('reason') in ('http_status_402','http_status_401'):
                    raise ValueError('Account unavailable again; queued cells not launched')
            if active:
                time.sleep(2)
        manifest['status']=summary['status']='completed_all_attempts'
        manifest['source_unchanged']=bench.source_hashes(ROOT)==registered['source_sha256']
        staging.rmdir()
    except BaseException:
        manifest['status']=summary['status']='interrupted_no_replacement'
        for process,_,_ in active.values():
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
        raise
    finally:
        manifest['finished_at']=summary['finished_at']=bench.now()
        checkpoint()
    combined=[]
    for row in initial['rows']:
        replacement=next((r for r in summary['rows'] if r['original_run_id']==row['run_id']),None)
        combined.append(dict(replacement or row, initial_attempt_id=row['run_id'],
            initial_attempt_reason=row['reason'], recovery_used=replacement is not None))
    value={'experiment_id':'E2-recovered-cells','status':'completed_all_attempts',
           'initial_batch':'summary.json','recovery_batch':'recovery-1/summary.json',
           'note':'30 planned cells after account-quota recovery; original 30 plus 21 recovery attempts retained. Not the original first-attempt success rate.',
           'rows':combined,'groups':bench.aggregate(combined)}
    _write(parent/'combined_summary.json',value)
    return value


if __name__=='__main__':
    import httpx
    key=getpass.getpass('API key (hidden; memory only): ')
    try:
        balance=httpx.get('https://api.deepseek.com/user/balance',headers={'Authorization':'Bearer '+key},timeout=30)
        if balance.status_code!=200 or balance.json().get('is_available') is not True:
            raise ValueError('Account not available; no exploration started')
        print('API balance availability confirmed; starting registered recovery.',flush=True)
        run(key)
    finally:
        key=None
