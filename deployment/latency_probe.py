"""Synthetic inference-only A/B; never starts a physics session."""
import argparse
import json
from pathlib import Path
import time
import httpx

parser=argparse.ArgumentParser()
parser.add_argument('--ports',default='8000,8001')
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
rows=[]
document='\n'.join(f'Record {n}: sample_count=20; region=public; checksum={n*17}; retain this record for context.' for n in range(650))
for port in [int(x) for x in args.ports.split(',')]:
 for trial in range(3):
  payload={'model':'qwen3.8-27b','messages':[{'role':'system','content':'Follow the request exactly. Reference records:\n'+document},{'role':'user','content':'Write integers 1 through 300 separated by commas. No explanation.'}],
           'temperature':0,'max_tokens':256,'stream':True,'stream_options':{'include_usage':True},'chat_template_kwargs':{'enable_thinking':False}}
  started=time.monotonic();first=None;usage=None;finish=None;reasoning=0
  with httpx.stream('POST',f'http://127.0.0.1:{port}/v1/chat/completions',json=payload,timeout=180) as response:
   response.raise_for_status()
   for line in response.iter_lines():
    if not line.startswith('data: '):continue
    raw=line[6:]
    if raw=='[DONE]':break
    event=json.loads(raw)
    if event.get('usage'):usage=event['usage']
    for choice in event.get('choices',[]):
     delta=choice.get('delta',{})
     if delta.get('content') and first is None:first=time.monotonic()-started
     reasoning+=len(delta.get('reasoning_content') or '')
     if choice.get('finish_reason'):finish=choice['finish_reason']
  row={'port':port,'trial':trial,'elapsed_seconds':time.monotonic()-started,'first_content_seconds':first,'usage':usage,'finish_reason':finish,'reasoning_characters':reasoning}
  rows.append(row);print(json.dumps(row),flush=True)
  args.output.parent.mkdir(parents=True,exist_ok=True)
  args.output.write_text(json.dumps({'kind':'synthetic_inference_only','max_output_tokens':256,'rows':rows},indent=2))
