"""Launch one loopback Qwen replica for E4 latency testing and execution."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--gpu', type=int, choices=range(4), required=True)
parser.add_argument('--port', type=int, required=True)
parser.add_argument('--mode', choices=['optimized','cached-eager','control'], default='optimized')
args = parser.parse_args()
with socket.socket() as sock:
    if sock.connect_ex(('127.0.0.1',args.port)) == 0:
        raise SystemExit('Port already listening; existing service was not changed')
label=f'e4-gpu{args.gpu}-{args.mode}'
launch=ROOT/'deployment'/f'{label}.launch.json'
if launch.exists():
    pid=json.loads(launch.read_text())['pid']
    cmdline=Path(f'/proc/{pid}/cmdline')
    if cmdline.exists() and b'vllm.entrypoints' in cmdline.read_bytes():
        raise SystemExit('Previous service still running or warming up')
cuda=str(ROOT.parent/'.cuda13-toolchain/nvidia/cu13')
package='/opt/shore-test5-forge2/lib/python3.12/site-packages/nvidia/cu13'
env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(args.gpu),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OMP_NUM_THREADS='1',CUDA_HOME=cuda)
env['PATH']='/opt/shore-test5-forge2/bin:'+cuda+'/bin:'+env.get('PATH','')
env['LD_LIBRARY_PATH']='/opt/shore-test5-forge2/lib:'+package+'/lib:'+env.get('LD_LIBRARY_PATH','')
env['CPATH']=package+'/include:'+env.get('CPATH','')
env['LIBRARY_PATH']=package+'/lib:'+env.get('LIBRARY_PATH','')
env['NVCC_APPEND_FLAGS']='-std=c++17 -I'+package+'/include -L'+package+'/lib'
command=['/opt/shore-test5-forge2/bin/python','-m','vllm.entrypoints.cli.main','serve',
 '/inspire/hdd/project/26-the-other-shore/public/models/Qwen3.8-27B','--served-model-name','qwen3.8-27b',
 '--host','127.0.0.1','--port',str(args.port),'--tensor-parallel-size','1','--max-model-len','262144',
 '--max-num-seqs','1' if args.mode!='control' else '3','--gpu-memory-utilization','0.90',
 '--enable-auto-tool-choice','--tool-call-parser','qwen3_xml','--reasoning-parser','qwen3','--language-model-only',
 '--enable-prefix-caching' if args.mode!='control' else '--no-enable-prefix-caching']
if args.mode!='optimized':command.append('--enforce-eager')
with (ROOT/'deployment'/f'{label}.log').open('ab') as log:
    p=subprocess.Popen(command,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
launch.write_text(json.dumps(dict(pid=p.pid,command=command,gpus=str(args.gpu),mode=args.mode),indent=2))
print(label,p.pid,flush=True)
