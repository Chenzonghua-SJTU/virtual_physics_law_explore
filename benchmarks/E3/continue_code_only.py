"""User scope amendment: preserve attempts, finish only the 15 code cells."""
import copy
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import benchmark_code_v2 as bench
from shore_agent.code_execution import sandbox_info
from shore_agent.web_jobs import _write


def live(pid):
    state=subprocess.run(['ps','-p',str(pid),'-o','stat='],capture_output=True,text=True).stdout.strip()
    return bool(state and not state.startswith('Z'))


def main(key):
    out=ROOT/'benchmarks/E3';staging=ROOT/'runs/.E3-active'
    registered=json.loads((out/'original_schedule/manifest.json').read_text())
    original=json.loads((out/'original_schedule/summary.json').read_text())
    amendment=json.loads((out/'scope_change.json').read_text())
    if json.loads((out/'manifest.json').read_text()).get('scope')=='code_only_15':
        raise ValueError('Code-only amendment already started; no replacement/retry')
    assert bench.source_hashes(ROOT)==registered['source_sha256']
    jobs=[copy.deepcopy(j) for j in registered['rows'] if j['arm']=='code']
    assert len(jobs)==15
    manifest={**registered,'scope':'code_only_15','status':'running','rows':jobs,
        'scope_amended_at':bench.now(),'amendment':amendment,
        'controller_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'original_schedule':'original_schedule/manifest.json',
        'primary_diagnostic':'15 code-only cells, complete hidden position RMSE < 1e-6; baseline extras excluded'}
    summary={'experiment_id':'E3','scope':'code_only_15','started_at':registered['started_at'],
             'status':'running','rows':[copy.deepcopy(next(r for r in original['rows'] if r['run_id']==j['run_id'])) for j in jobs]}
    extras=[]
    for j in registered['rows']:
        if j['arm']!='baseline':continue
        row=copy.deepcopy(next(r for r in original['rows'] if r['run_id']==j['run_id']))
        if j['state']=='running':
            directory=staging/j['run_id']
            elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(j['started_at'])).total_seconds()
            row=bench.collect(directory,{k:j[k] for k in ('world_id','arm','repeat','order','run_id')},elapsed,None)
            changed=next(c for c in amendment['baseline_changes'] if c['run_id']==j['run_id'])
            if changed['interrupted']:
                row.update(status='cancelled_by_user',reason='user_requested_code_only_15',interrupted=True)
            directory.rename(ROOT/'runs'/j['run_id'])
        elif j['state']=='pending':row.update(status='not_started',reason='user_requested_code_only_15')
        row['excluded_from_primary_retest']=True
        extras.append(row)
    _write(out/'excluded_baseline_summary.json',{'note':'Not part of the 15 code-only retests; preserve completed/cancelled/never-started controls.','rows':extras})
    active={}
    for i,j in enumerate(jobs):
        if j['state']=='running':active[i]={'pid':j['worker_pid'],'process':None,'started_at':j['started_at'],'directory':staging/j['run_id']}
    pending=[i for i,j in enumerate(jobs) if j['state']=='pending']

    def checkpoint():
        summary['groups']=[g for g in bench.aggregate(summary['rows']) if g['arm']=='code']
        _write(out/'manifest.json',manifest);_write(out/'summary.json',summary)
        text=bench.markdown(summary).replace('世界3/4/5 × baseline/code × 每组5次。','用户调整范围：世界3/4/5 × 简化code × 每世界5次，共15次。')
        (out/'comparison.md').write_text(text)

    checkpoint()
    try:
        while pending or active:
            for i,item in list(active.items()):
                process=item['process'];rc=process.poll() if process is not None else None
                if (process is not None and rc is None) or (process is None and live(item['pid'])):continue
                j=jobs[i];elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(item['started_at'])).total_seconds()
                row=bench.collect(item['directory'],{k:j[k] for k in ('world_id','arm','repeat','order','run_id')},elapsed,rc)
                row['returncode_observed']=process is not None
                item['directory'].rename(ROOT/'runs'/j['run_id'])
                summary['rows'][i]=row
                manifest['rows'][i].update(state='finished',finished_at=bench.now(),returncode=rc)
                del active[i];checkpoint()
                print(f'E3 CODE DONE {j["run_id"]} rmse={row["position_rmse"]} reason={row["reason"]}',flush=True)
                if row['reason'] in ('http_status_401','http_status_402'):raise ValueError('Account unavailable; stop pending cells')
            while pending and len(active)<3:
                i=pending.pop(0);j=jobs[i]
                assert bench.source_hashes(ROOT)==registered['source_sha256']
                assert sandbox_info(j['configuration'].get('code_execution'))==registered['sandbox']
                directory=staging/j['run_id'];directory.mkdir(mode=0o700)
                _write(directory/'config.json',j['configuration'])
                _write(directory/'web.json',{'id':j['run_id'],'created_at':bench.now(),'status':'running',
                    'world_id':j['world_id'],'mode':'autonomous_discovery','experiment_id':'E3',
                    'reasoning_effort':'high','arm':'code','repeat':j['repeat']})
                env=dict(os.environ);env.pop('DEEPSEEK_API_KEY',None)
                env.update({k:'1' for k in bench.THREAD_VARS});env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(ROOT))
                process=subprocess.Popen([sys.executable,'-u','-m','shore_agent.web_worker','--run-dir',str(directory)],
                    cwd=ROOT,env=env,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,text=True,start_new_session=True)
                start=bench.now();active[i]={'pid':process.pid,'process':process,'started_at':start,'directory':directory}
                process.stdin.write(json.dumps({'api_key':key})+'\n');process.stdin.close()
                manifest['rows'][i].update(state='running',started_at=start,worker_pid=process.pid)
                summary['rows'][i]['status']='running';checkpoint()
                print(f'E3 CODE START {j["run_id"]}',flush=True)
            if active:time.sleep(2)
        manifest['status']=summary['status']='completed_all_attempts'
        manifest['source_unchanged']=bench.source_hashes(ROOT)==registered['source_sha256']
        staging.rmdir()
    except BaseException:
        manifest['status']=summary['status']='interrupted_no_replacement'
        for item in active.values():
            if live(item['pid']):os.killpg(item['pid'],signal.SIGTERM)
        raise
    finally:
        manifest['finished_at']=summary['finished_at']=bench.now();checkpoint()


if __name__=='__main__':
    key=getpass.getpass('API key (hidden; memory only): ')
    try:main(key)
    finally:key=None
