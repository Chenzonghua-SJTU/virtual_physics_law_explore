"""Start three local inference instances on qz-infer's four GPUs, without downloads."""
import json
import os
from pathlib import Path
import socket
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PYTHON = '/opt/shore-test5-forge2/bin/python'
MODELS = [('Qwen3.8-27B', 'qwen3.8-27b', '0', 8000),
          ('Qwen3.8-27B', 'qwen3.8-27b', '1', 8001),
          ('Qwen3.5-122B-A10B-FP8', 'qwen3.5-122b-a10b', '2,3', 8002)]
for folder, model, gpus, port in MODELS:
    label = model + ('-replica' if port == 8001 else '')
    launch_file = ROOT / 'deployment' / (label + '.launch.json')
    if launch_file.exists():
        previous = json.loads(launch_file.read_text())
        proc_file = Path('/proc') / str(previous['pid']) / 'cmdline'
        if proc_file.exists() and folder.encode() in proc_file.read_bytes() and b'vllm.entrypoints' in proc_file.read_bytes():
            print(label, 'already running or warming up; left unchanged')
            continue
    checkpoint = Path('/inspire/hdd/project/26-the-other-shore/public/models') / folder
    if not (checkpoint / 'model.safetensors.index.json').is_file() or not (checkpoint / 'tokenizer.json').is_file():
        print(model, 'checkpoint incomplete; not started')
        continue
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1', port)) == 0:
            print(model, 'port already listening; left unchanged')
            continue
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=gpus, HF_HUB_OFFLINE='1',
               TRANSFORMERS_OFFLINE='1', OMP_NUM_THREADS='1',
               CUDA_HOME=str(ROOT.parent / '.cuda13-toolchain/nvidia/cu13'))
    env['PATH'] = '/opt/shore-test5-forge2/bin:' + env['CUDA_HOME'] + '/bin:' + env.get('PATH', '')
    cuda_package = '/opt/shore-test5-forge2/lib/python3.12/site-packages/nvidia/cu13'
    env['LD_LIBRARY_PATH'] = '/opt/shore-test5-forge2/lib:' + cuda_package + '/lib:' + env.get('LD_LIBRARY_PATH', '')
    env['CPATH'] = cuda_package + '/include:' + env.get('CPATH', '')
    env['LIBRARY_PATH'] = cuda_package + '/lib:' + env.get('LIBRARY_PATH', '')
    env['NVCC_APPEND_FLAGS'] = '-std=c++17 -I' + cuda_package + '/include -L' + cuda_package + '/lib'
    command = [PYTHON, '-m', 'vllm.entrypoints.cli.main', 'serve',
               '/inspire/hdd/project/26-the-other-shore/public/models/' + folder,
               '--served-model-name', model, '--host', '127.0.0.1', '--port', str(port),
               '--tensor-parallel-size', str(len(gpus.split(','))), '--max-model-len', '262144',
               '--max-num-seqs', '3', '--gpu-memory-utilization', '0.90',
               '--enable-auto-tool-choice', '--tool-call-parser', 'qwen3_xml',
               '--reasoning-parser', 'qwen3', '--language-model-only', '--enforce-eager']
    if model == 'qwen3.5-122b-a10b':
        command += ['--linear-backend', 'triton', '--moe-backend', 'triton']
        env['VLLM_USE_DEEP_GEMM'] = '0'
        env['VLLM_MOE_USE_DEEP_GEMM'] = '0'
    with (ROOT / 'deployment' / (label + '.log')).open('ab') as log:
        proc = subprocess.Popen(command, env=env, cwd=ROOT, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=log, start_new_session=True)
    (ROOT / 'deployment' / (label + '.launch.json')).write_text(
        json.dumps(dict(pid=proc.pid, command=command, gpus=gpus), indent=2))
    print(model, proc.pid)
