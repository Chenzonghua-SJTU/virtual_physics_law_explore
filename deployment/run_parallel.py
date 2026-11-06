"""Launch independent baseline batches after their dedicated local GPU services are ready."""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
plan = [
    (8001, 'qwen3.8-27b', 'v15-local-qwen38-nothink-20261107-r02'),
    (8002, 'qwen3.5-122b-a10b', 'v15-local-qwen35-122b-nothink-20261107-r01'),
]
pending = list(plan)
started = []
deadline = time.monotonic() + 2400
while pending and time.monotonic() < deadline:
    for port, model, batch in list(pending):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/v1/models', timeout=2) as response:
                available = json.load(response)
            if model not in [item['id'] for item in available['data']]:
                continue
        except Exception:
            continue
        config = json.loads((ROOT / 'deployment/config.server.json').read_text())
        config['model'].update(model=model, base_url=f'http://127.0.0.1:{port}/v1')
        config['model']['local_model_endpoints'][model] = config['model']['base_url']
        config_path = ROOT / 'deployment' / (batch + '.config.json')
        config_path.write_text(json.dumps(config, indent=2))
        if (ROOT / 'experiments' / batch).exists():
            raise RuntimeError('Existing batch must not be overwritten: ' + batch)
        command = [str(ROOT / '.venv/bin/python'), '-u', 'benchmark_v15.py',
                   '--config', str(config_path), '--model', model,
                   '--no-thinking', '--workers', '3', '--output', 'experiments/' + batch]
        env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
        with (ROOT / 'deployment' / (batch + '.log')).open('ab') as log:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log, start_new_session=True)
        started.append(dict(batch=batch, model=model, port=port, pid=process.pid))
        pending.remove((port, model, batch))
        (ROOT / 'deployment/parallel-launch.json').write_text(json.dumps(dict(started=started,pending=pending),indent=2))
        print(batch, process.pid, flush=True)
    if pending:
        time.sleep(5)
if pending:
    raise RuntimeError('Model startup deadline reached; pending batches were not started')
