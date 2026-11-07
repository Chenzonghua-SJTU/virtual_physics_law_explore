"""Frozen-tool synthetic transfer check, no Agent/model/world-catalogue access."""
import concurrent.futures,hashlib,json,pathlib,time
import numpy as np
from shore_agent.numerics import rollout
from shore_agent.symbolic_service import search_remote
root=pathlib.Path.cwd();out=root/'experiments/E5/e8-r06-generic-transfer.json'
if out.exists():raise RuntimeError('never_overwrite_completed_diagnostic')
rng=np.random.default_rng(834719)
# Reference expressions stay in this evaluator; only simulated observations enter SR.
cases=[('damped_coupled',{'ax':'-a*x-b*vx+c*y','ay':'-a*y-b*vy-c*x'},
        {'a':float(rng.uniform(.17,.43)),'b':float(rng.uniform(.08,.22)),'c':float(rng.uniform(.07,.19))}),
       ('velocity_cubic',{'ax':'-a*vx-b*vx**3','ay':'-a*vy-b*vy**3'},
        {'a':float(rng.uniform(.11,.31)),'b':float(rng.uniform(.02,.08))}),
       ('coordinate_sines',{'ax':'-a*sin(x)','ay':'-b*sin(y)'},
        {'a':float(rng.uniform(.16,.38)),'b':float(rng.uniform(.18,.42))}),
       ('decaying_drive',{'ax':'a*exp(-b*t)-c*vx','ay':'-d*vy'},
        {'a':float(rng.uniform(.24,.51)),'b':float(rng.uniform(.17,.33)),
         'c':float(rng.uniform(.06,.16)),'d':float(rng.uniform(.08,.21))})]
def observations(law,params,index,heldout=False):
 seed=np.random.default_rng(75001+100*index+int(heldout));records=[]
 for i in range(6 if heldout else 5):
  t0=float(i%3)*2.5;dt=.12 if heldout else .1
  p={'probe_id':('test_' if heldout else 'train_')+str(i),'times':(t0+np.arange(50)*dt).tolist(),
     'initial_conditions':{'r0':seed.uniform(-2.8,2.8,2).tolist(),'v0':seed.uniform(-.9,.9,2).tolist(),'t0':t0,'properties':{}},
     'observation_noise':{'position_sigma':0.,'velocity_sigma':0.}}
  z=rollout(law,params,p,[]);p.update(r_obs=z['r_pred'],v_obs=z['v_pred']);records.append(p)
 return records
registered=[]
for index,(name,law,params) in enumerate(cases):
 registered.append({'name':name,'reference_law':law,'reference_parameters':params,
                    'train':observations(law,params,index),'test':observations(law,params,index,True)})
registration={'source_commit':'19a83f9','scientific_commit':'5b6eef6','seed':834719,
 'purpose':'Supplemental tool-only transfer check, not six-world score nor hidden-test prediction. Random parameters and structures not identical to development laws.',
 'selection':'Evaluate returned rank 1 only, no oracle selection. All four outcomes retained; no retuning this frozen version from these results.',
 'references_visible_to_search':False,'search_seconds':40,'cases':registered}
reg=root/'experiments/E5/e8-r06-generic-transfer-registration.json'
with reg.open('x') as f:json.dump(registration,f,indent=2)
def one(case):
 start=time.monotonic();result=search_remote(case['train'],40,endpoint='http://127.0.0.1:8890',random_state=42)
 rows=result.get('candidates',[]);selected=rows[0] if rows else None;errors=[];failures=[]
 if selected:
  params=selected.get('fitted_parameters') or {p['name']:p['initial'] for p in selected['parameter_spec']}
  for probe in case['test']:
   try:
    z=rollout(selected['law_spec'],params,probe,[])
    errors.append(float(np.mean(np.sum((np.asarray(z['r_pred'])-probe['r_obs'])**2,axis=1))))
   except Exception as exc:failures.append({'probe_id':probe['probe_id'],'error_type':type(exc).__name__,'message':str(exc)[:180]})
 row={'name':case['name'],'status':result.get('status'),'wall_seconds':time.monotonic()-start,
      'selected_candidate':selected,'heldout_position_rmse':float(np.sqrt(np.mean(errors))) if errors and not failures else None,
      'heldout_failures':failures,'search_diagnostics':result.get('basis_diagnostics'),
      'search_result':result,'candidate_count':len(rows),'public_input_sha256':hashlib.sha256(json.dumps(case['train'],sort_keys=True).encode()).hexdigest()}
 print(json.dumps({k:row[k] for k in ['name','status','wall_seconds','heldout_position_rmse','candidate_count']}),flush=True)
 return row
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(one,registered))
with out.open('x') as f:json.dump({'protocol':{k:v for k,v in registration.items() if k!='cases'},'results':results},f,indent=2)
