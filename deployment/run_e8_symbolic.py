"""One registered six-world Agent attempt, using the existing robust scheduler.

No service/model is launched or restarted here. All four identical Qwen endpoints
and the warmed symbolic service must already be ready and idle. Previous scores
and failed attempts are retained; an existing output directory is never reused.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from benchmark_v15 import configuration
from deployment import run_e7
from shore_worlds import V15_WORLD_IDS

BATCH_ID = 'e8-qwen38-pysr-stage-20261107-r01'
REGISTERED_REPEATS = ('r01', 'r02')
CONFIG = 'deployment/config.e8.symbolic.json'
PROTOCOL = 'experiments/E5/e8-protocol.json'


def plans(project=ROOT, *, repeat='r01'):
    if repeat not in REGISTERED_REPEATS:
        raise ValueError('E8 repeat must be explicitly registered as r01 or r02')
    project = Path(project).resolve()
    batch_id = BATCH_ID.removesuffix('r01') + repeat
    config = configuration(project, config_path=project/CONFIG, thinking=False, ruleset='e5')
    config['model'].pop('sampling_seed',None)
    required = {
        ('environment','wall_seconds'):300, ('environment','energy_budget'):10,
        ('environment','noise'):False, ('environment','world_set'):'v15',
        ('model','model'):run_e7.MODEL, ('model','max_tokens_per_call'):4096,
        ('model','max_total_tokens'):None, ('model','thinking'):False,
        ('agent','guidance_profile'):'baseline', ('agent','loop_recovery'):True,
        ('agent','submission_fit_rmse_threshold'):1e-5,
        ('agent','submission_time_remaining_seconds'):40,
        ('numerics','symbolic_regression_enabled'):True,
        ('numerics','symbolic_regression_endpoint'):run_e7.SYMBOLIC_ENDPOINT,
    }
    for (section,key), value in required.items():
        if config.get(section,{}).get(key) != value:
            raise ValueError(f'E8 registered setting differs: {section}.{key}')
    registration = json.loads((project/PROTOCOL).read_text())['registered_agent_batches'][repeat]
    return [{'output':project/'experiments/E5'/batch_id, 'config':config, 'experiment_group':'E8',
             'protocol_metadata':{'registered_repeat':repeat, 'repeat_registration':registration},
             'require_staged_warmup':True,
             'planned_runs':{world:project/'runs'/f'{batch_id}-{world}' for world in V15_WORLD_IDS}}]


def source_paths(project):
    project = Path(project)
    # Discover any new generic basis/feature module and conditional prompt, so
    # provenance cannot silently omit a new scientific input to the Agent.
    paths = {CONFIG, PROTOCOL, 'deployment/run_e8_symbolic.py', 'deployment/run_e7.py'}
    paths.update(str(p.relative_to(project)) for p in (project/'shore_agent').rglob('*.py'))
    paths.update(str(p.relative_to(project)) for p in (project/'shore_agent/prompts').rglob('*.txt'))
    return sorted(paths)


def verify_julia_threads(project, *, run=subprocess.run):
    """Compile no search and launch no service: verify the fixed local runtime."""
    project=Path(project)
    python=project/'.venv-pysr/bin/python'
    julia=project/'.venv-pysr/julia-1.13.3/bin/julia'
    depot=project/'.venv-pysr/julia-depot'
    if not all(path.exists() for path in (python,julia,depot)):
        raise RuntimeError('E8 requires the existing local Julia executable, depot and PySR interpreter')
    fixed={'PYTHON_JULIAPKG_EXE':str(julia),'JULIA_DEPOT_PATH':str(depot),
           'PYTHON_JULIAPKG_OFFLINE':'yes','PYTHON_JULIACALL_THREADS':'4','JULIA_NUM_THREADS':'4',
           'PYTHON_JULIACALL_HANDLE_SIGNALS':'yes',
           'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    code="import pysr; from juliacall import Main as jl; import json; print('E8_JULIA '+json.dumps({'actual_threads':int(jl.seval('Threads.nthreads()'))}))"
    try:
        result=run([str(python),'-c',code],env=dict(os.environ,**fixed),cwd=project,
                   capture_output=True,text=True,timeout=120,check=True)
        rows=[line.removeprefix('E8_JULIA ') for line in result.stdout.splitlines() if line.startswith('E8_JULIA ')]
        metadata=json.loads(rows[-1])
        if type(metadata.get('actual_threads')) is not int or metadata['actual_threads']!=4:
            raise ValueError('thread_count')
    except (OSError,ValueError,IndexError,subprocess.SubprocessError):
        raise RuntimeError('E8 local Julia runtime could not confirm exactly four threads') from None
    return dict(metadata,environment=fixed,searches_started=0,model_calls=0)


def idle_workloads(opener=None):
    opener = opener or urlopen
    bootstrap = run_e7._remote_json('http://127.0.0.1:8765/api/bootstrap',opener)
    if bootstrap.get('active_run_id'):
        raise RuntimeError('E8 waits for the existing user exploration to finish')
    for endpoint in run_e7.ENDPOINTS:
        url = endpoint.removesuffix('/v1')+'/metrics'
        try:
            with opener(url,timeout=5) as response:
                if response.status != 200: raise ValueError('http_status')
                body = response.read(run_e7.MAX_PREFLIGHT_BYTES+1)
            if len(body)>run_e7.MAX_PREFLIGHT_BYTES: raise ValueError('response_size')
            metrics = {}
            for metric,value in re.findall(
                    r'^vllm:(num_requests_running|num_requests_waiting)(?:\{[^\n]*\})?\s+([0-9.eE+-]+)\s*$',
                    body.decode(),re.MULTILINE):
                metrics.setdefault(metric,[]).append(float(value))
            if set(metrics)!={'num_requests_running','num_requests_waiting'}:
                raise ValueError('missing_request_metrics')
            if any(value!=0 for values in metrics.values() for value in values):
                raise RuntimeError(f'E8 waits for idle model endpoint: {endpoint}')
        except RuntimeError:
            raise
        except Exception:
            raise RuntimeError(f'E8 cannot verify idle model endpoint: {endpoint}') from None


def run_study(project=ROOT, *, repeat='r01', opener=None, stop_requested=None):
    project = Path(project).resolve()
    planned = plans(project, repeat=repeat)
    run_e7._check_fresh_paths(planned)
    idle_workloads(opener)
    planned[0]['symbolic_runtime_preflight']=verify_julia_threads(project)
    return run_e7.run_study(project,opener=opener,stop_requested=stop_requested,
                            planned_batches=planned,extra_source_paths=source_paths(project))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeat', choices=REGISTERED_REPEATS, default='r01')
    args = parser.parse_args(argv)
    stopped = False
    def request_stop(*_):
        nonlocal stopped
        stopped=True
    previous={sig:signal.signal(sig,request_stop) for sig in (signal.SIGINT,signal.SIGTERM)}
    try:
        run_study(repeat=args.repeat, stop_requested=lambda:stopped)
    finally:
        for sig,handler in previous.items(): signal.signal(sig,handler)


if __name__=='__main__':
    main()
