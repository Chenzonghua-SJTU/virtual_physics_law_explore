import copy
import json

import pytest

from shore_agent.code_response import compact, execution_preview, select_field
from shore_agent.code_execution import execute_code
from shore_agent.environment import Environment
from shore_agent.runtime import ToolRuntime
from shore_agent.schemas import SCHEMAS, tool_schemas
from test_code_execution import docker_config


def test_script_contract_and_baseline_callback_unchanged():
    before = copy.deepcopy(SCHEMAS)
    schemas = tool_schemas(True)
    code = schemas[-1]['function']['parameters']
    assert set(code['properties']) == set(code['required']) == {'code','inputs'}
    baseline = next(s for s in SCHEMAS if s['function']['name']=='call_back')
    assert 'field_path' not in baseline['function']['parameters']['properties']
    assert SCHEMAS == before


def test_compact_keeps_small_comparison_and_omits_protocol_echo():
    results = [{'candidate':str(i),'rmse':1/(i+1)} for i in range(12)]
    record = {'execution_id':'code_test','status':'success','result':results,'code':'large code'*5000,
              'output_schema':{'type':'array'},'inputs':{'private_protocol':'hashes'},
              'stdout':'','stderr':'','artifacts':[]}
    old = copy.deepcopy(record)
    p = execution_preview(record)
    assert p['result'] == results and p['truncated'] is False
    assert all(k not in p for k in ['code','output_schema','inputs','sandbox'])
    assert record == old


@pytest.mark.parametrize('value', [list(range(10000)), {'table':[[i]*40 for i in range(1000)]},
    {'text':'汉字'*30000}, {'very_long_key'*4000:1}, 'x'*100000])
def test_compact_bound_explicit_truncation_and_does_not_modify(value):
    original = copy.deepcopy(value)
    view, truncated = compact(value, 1000)
    assert truncated and view['truncated']
    assert len(json.dumps(view,ensure_ascii=False)) <= 1000
    assert value == original


def test_error_reports_location_without_echoing_full_trace():
    record={'execution_id':'code_err','status':'error','result':None,'stdout':'a'*50000,'stderr':'',
            'error':{'type':'KeyError','message':'positions','line':3,'source_line':'p["positions"]',
                     'traceback':'trace'*10000,'input_layout':{'p':{'fields':['r_obs','v_obs']}}},'artifacts':[]}
    p=execution_preview(record)
    assert p['error']['type']=='KeyError' and p['error']['line']==3
    assert 'traceback' not in p['error'] and p['truncated']
    assert len(json.dumps(p))<6000


def test_field_read_is_exact_paged_and_read_only():
    record={'result':{'rows':list(range(20))},'stdout':'abcdefghijkl'}
    old=copy.deepcopy(record)
    p=select_field(record,['result','rows'],4,3)
    assert p['value']==[4,5,6] and p['total_items']==20 and p['truncated']
    assert select_field(record,['result','rows',4])['value']==4
    assert select_field(record,['stdout'],2,4)['value']=='cdef'
    assert record==old
    with pytest.raises(ValueError):select_field(record,['result','missing'])
    with pytest.raises(ValueError):select_field(record,['result','rows',-1])


def test_runtime_compact_record_and_selective_read_do_not_change_original(tmp_path,monkeypatch):
    env=Environment({'physics_version':'v4','noise':False})
    try:
        rt=ToolRuntime(env,tmp_path,code_config={'enabled':True});rt.mission()
        def run(*args):
            return {'status':'success','result':{'rows':list(range(2000))},'stdout':'','stderr':'','artifacts':[]}
        monkeypatch.setattr('shore_agent.code_execution.execute_code',run)
        out=rt.execute('run_code',{'code':'result = {}','inputs':{}})
        assert out['ok'] and out['data']['truncated'] and 'code' not in out['data']
        rid=out['data']['execution_id']
        full=rt.store.get('code_execution',rid)
        assert full['result']['rows']==list(range(2000)) and full['code']=='result = {}'
        args={'record_type':'code_execution','record_ids':[rid], 'field_path':['result','rows'],'offset':23,'limit':4}
        assert rt.execute('call_back',args)['data']['value']==[23,24,25,26]
        summary=rt.execute('call_back',{'record_type':'code_execution','record_ids':[rid]})
        assert 'code' not in summary['data']['records'][0]['content']
        assert rt.store.get('code_execution',rid)==full
        for bad in [dict(args, record_ids=['not_acquired']),dict(args,offset=-1),dict(args,limit=1001),dict(args,record_ids=[rid,rid])]:
            assert not rt.execute('call_back',bad)['ok']
        assert not rt.execute('call_back',{'offset':2})['ok']
    finally:env.close()


def test_real_script_numpy_and_print_only_without_extra_retry(tmp_path,docker_config):
    code='''import numpy as np
p=inputs['p'][0]
result={'a':np.asarray(p['v']), 'b':np.float64(2.5), 'c':(np.int64(3),np.bool_(True))}
'''
    r=execute_code(code,{'p':[{'v':[[1,2],[3,4]]}]},{},tmp_path/'array',docker_config,30)
    assert r['status']=='success',r
    assert r['result']=={'a':[[1,2],[3,4]],'b':2.5,'c':[3,True]}
    p=execute_code('print(inputs["value"])',{'value':42},{},tmp_path/'print',docker_config,30)
    assert p['status']=='success' and '42' in p['stdout'] and p['warnings']


def test_real_field_error_location_input_shape_and_nonfinite(tmp_path,docker_config):
    r=execute_code('p=inputs["probes"][0]\nresult=p["positions"]',
        {'probes':[{'r_obs':[[0,0],[1,1]],'v_obs':[[0,1],[0,1]]}]},{},tmp_path/'bad',docker_config,30)
    assert r['status']=='error' and r['error']['type']=='KeyError' and r['error']['line']==2
    assert r['error']['input_layout']['probes']['first_record_fields']['r_obs']['first_item_shape']==[2,2]
    nan=execute_code('import numpy as np\nresult=np.array([1,np.nan])',{}, {},tmp_path/'nan',docker_config,30)
    assert nan['status']=='error' and 'Nonfinite' in nan['error']['message']


def test_e3_schedule_is_separate_and_configuration_is_balanced():
    import benchmark_code_v2 as b
    from pathlib import Path
    jobs=b.schedule()
    assert len({j['run_id'] for j in jobs})==30
    assert all(j['run_id'].startswith('E3-') for j in jobs)
    base=json.loads((b.PROJECT/'config.example.json').read_text())
    for world in b.WORLDS:
        configs=[]
        for j in jobs:
            if j['world_id']!=world:continue
            c=b.configuration(base,j)
            assert c['model']['reasoning_effort']=='high' and c['model']['max_total_tokens']==5000000
            assert c['code_execution'].pop('enabled') == (j['arm']=='code')
            configs.append(c)
        assert all(c==configs[0] for c in configs)
