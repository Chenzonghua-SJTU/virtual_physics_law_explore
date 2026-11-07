"""B-only replay plumbing with synthetic arrays and a fake service; no search."""
import copy
import io
import json

import numpy as np
import pytest

from deployment import replay_e8_symbolic as replay


def bundle():
    datasets=[]
    for world in range(1,7):
        dataset={'world_id':f'world_{world}','exact_acceleration':{}}
        for split,count in (('train',24),('heldout',8)):
            probes,labels=[],{}
            for i in range(count):
                t=np.arange(50)*.02+i
                v=np.array([.1+i*.01,.2+i*.01])
                r=np.array([1+i*.1,2+i*.1])+(t-t[0])[:,None]*v
                name=f'{split}_{i}'
                probes.append({'probe_id':name,'times':t.tolist(),'r_obs':r.tolist(),
                               'v_obs':np.tile(v,(50,1)).tolist(),
                               'initial_conditions':{'r0':r[0].tolist(),'v0':v.tolist(),'t0':float(t[0]),
                                                    'properties':{'mass':1+i*.1,'charge':2+i*.1}}})
                labels[name]={'times':t[1:-1].tolist(),'values':[[7.,11.]]*48}
            dataset[split+'_probes']=probes
            dataset['exact_acceleration'][split]=labels
        datasets.append(dataset)
    return {'datasets':datasets}


class Response(io.BytesIO):
    status=200


def opener(url,timeout):
    assert url=='http://127.0.0.1:8891/health' and timeout==5
    health={'ready':4,'busy':0,'actual_julia_threads':[4]*4,
            'worker_warmup':[{'warmup_stages':[{'stage':'algebra','maxsize':24},{'stage':'full','maxsize':48}]}]*4}
    return Response(json.dumps(health).encode())


def test_one_request_per_world_receives_only_observations_and_47_seconds(tmp_path):
    dataset=tmp_path/'dataset.json'
    original=bundle()
    dataset.write_text(json.dumps(original))
    calls=[]
    def search(probes,budget,**kwargs):
        calls.append(copy.deepcopy(probes))
        assert len(probes)==24 and budget==47
        assert kwargs=={'endpoint':replay.ENDPOINT,'random_state':42}
        assert all(set(p)=={'probe_id','initial_conditions','times','r_obs','v_obs'} for p in probes)
        return {'status':'completed','candidates':[],
                'axis_equations':{'ax':[{'source':'7.0','loss':0.,'complexity':1,'origin':'pysr'}],
                                  'ay':[{'source':'11.0','loss':0.,'complexity':1,'origin':'pysr'}]}}
    summary=replay.run(dataset,tmp_path/'results',opener=opener,search=search)
    assert len(calls)==len(summary['worlds'])==6
    assert summary['mode']=='B_only' and summary['model_calls']==summary['agent_missions']==0
    assert all(row['diagnostics']['raw_training_best_pair']['heldout']['nrmse']==0 for row in summary['worlds'])
    assert json.loads(dataset.read_text())==original
    with pytest.raises(ValueError,match='already exists'):
        replay.run(dataset,tmp_path/'results',opener=opener,search=lambda *a,**k:pytest.fail('No rerun'))


def test_cold_or_incorrect_thread_service_is_rejected_before_output_creation(tmp_path):
    dataset=tmp_path/'dataset.json'
    dataset.write_text(json.dumps(bundle()))
    bad=lambda *a,**k:Response(json.dumps({'ready':4,'busy':0,'actual_julia_threads':[192]*4}).encode())
    with pytest.raises(RuntimeError,match='four-thread'):
        replay.run(dataset,tmp_path/'out',opener=bad)
    assert not (tmp_path/'out').exists()


def test_oracle_label_in_probe_is_rejected_at_request_boundary(tmp_path):
    data=bundle()
    data['datasets'][0]['train_probes'][0]['exact_acceleration']=[7.,11.]
    dataset=tmp_path/'dataset.json'
    dataset.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='exact acceleration'):
        replay.preflight(dataset,tmp_path/'out',opener=opener)
