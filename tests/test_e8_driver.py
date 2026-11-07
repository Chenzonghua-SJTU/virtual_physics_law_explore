"""E8 registration and preflight; no model calls, Julia import or real missions."""
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import benchmark_v15
from deployment import run_e8_symbolic as driver


class Response(io.BytesIO):
    status=200


class Opener:
    def __init__(self,active=None,running=0,missing=False):
        self.active,self.running,self.missing=active,running,missing
        self.calls=[]
    def __call__(self,url,timeout):
        assert timeout==5
        self.calls.append(url)
        if url.endswith('/bootstrap'):
            body=json.dumps({'active_run_id':self.active}).encode()
        else:
            body=(f'vllm:num_requests_running{{model_name="qwen3.8-27b"}} {self.running}\n'
                  'vllm:num_requests_waiting{model_name="qwen3.8-27b"} 0.0\n').encode()
            if self.missing: body=b'# no metrics yet\n'
        return Response(body)


@pytest.fixture
def project(tmp_path):
    root=tmp_path/'project'
    (root/'deployment').mkdir(parents=True)
    (root/'experiments/E5').mkdir(parents=True)
    for name in ('config.example.json',driver.CONFIG,driver.PROTOCOL,
                 'deployment/run_e8_symbolic.py','deployment/run_e7.py'):
        (root/name).write_bytes((benchmark_v15.PROJECT/name).read_bytes())
    return root


def test_exactly_one_six_world_plan_preserves_registered_limits(project):
    plans=driver.plans(project)
    assert len(plans)==1 and len(plans[0]['planned_runs'])==6
    assert plans[0]['experiment_group']=='E8'
    config=plans[0]['config']
    assert config['environment']['wall_seconds']==300
    assert config['environment']['energy_budget']==10
    assert config['model']['max_tokens_per_call']==4096
    assert config['model']['max_total_tokens'] is None
    assert config['model']['thinking'] is config['environment']['noise'] is False
    assert config['agent']['submission_fit_rmse_threshold']==1e-5
    assert config['agent']['submission_time_remaining_seconds']==40
    assert not plans[0]['output'].exists()


def test_second_registered_batch_keeps_first_attempts_and_all_limits(project):
    first=driver.plans(project)[0]
    first['output'].mkdir()
    second=driver.plans(project,repeat='r02')[0]
    assert second['output'].name=='e8-qwen38-pysr-stage-20261107-r02'
    assert second['config']==first['config']
    assert len(second['planned_runs'])==6
    assert set(second['planned_runs'].values()).isdisjoint(first['planned_runs'].values())
    driver.run_e7._check_fresh_paths([second])
    assert second['protocol_metadata']['registered_repeat']=='r02'
    assert second['protocol_metadata']['repeat_registration']['additional_offline_searches']==0
    second['output'].mkdir()
    with pytest.raises(ValueError,match='already_exists'):
        driver.run_e7._check_fresh_paths([second])
    with pytest.raises(ValueError,match='explicitly registered'):
        driver.plans(project,repeat='r99')


@pytest.mark.parametrize('opener,message',[
    (Opener(active='user-exploration'),'existing user'),
    (Opener(running=1),'idle model'),
    (Opener(missing=True),'cannot verify idle'),
])
def test_busy_or_unverifiable_workloads_fail_before_reserving_runs(project,opener,message):
    with pytest.raises(RuntimeError,match=message):
        driver.run_study(project,opener=opener)
    assert not (project/'runs').exists()
    assert not driver.plans(project)[0]['output'].exists()


def test_wrapper_reuses_scheduler_and_hashes_new_generic_modules(project,monkeypatch):
    module=project/'shore_agent/features/new_basis.py'
    module.parent.mkdir(parents=True)
    module.write_text('generic basis')
    calls=[]
    monkeypatch.setattr(driver,'verify_julia_threads',lambda p:{'actual_threads':4})
    monkeypatch.setattr(driver.run_e7,'run_study',lambda *args,**kwargs:calls.append((args,kwargs)))
    opener=Opener()
    driver.run_study(project,repeat='r02',opener=opener)
    kwargs=calls[0][1]
    assert len(kwargs['planned_batches'])==1
    assert kwargs['planned_batches'][0]['symbolic_runtime_preflight']=={'actual_threads':4}
    assert kwargs['planned_batches'][0]['protocol_metadata']['registered_repeat']=='r02'
    assert 'shore_agent/features/new_basis.py' in kwargs['extra_source_paths']
    assert kwargs['opener'] is opener
    assert len(opener.calls)==5


def test_julia_preflight_forces_offline_and_checks_actual_threads(project):
    for relative in ('.venv-pysr/bin/python','.venv-pysr/julia-1.13.3/bin/julia'):
        path=project/relative
        path.parent.mkdir(parents=True,exist_ok=True)
        path.touch()
    (project/'.venv-pysr/julia-depot').mkdir()
    calls=[]
    def fake_run(command,**kwargs):
        calls.append((command,kwargs))
        return SimpleNamespace(stdout='E8_JULIA {"actual_threads":4}\n')
    evidence=driver.verify_julia_threads(project,run=fake_run)
    assert evidence['actual_threads']==4 and evidence['searches_started']==0
    environment=calls[0][1]['env']
    assert environment['PYTHON_JULIAPKG_OFFLINE']=='yes'
    assert environment['PYTHON_JULIACALL_HANDLE_SIGNALS']=='yes'
    assert environment['PYTHON_JULIACALL_THREADS']==environment['JULIA_NUM_THREADS']=='4'
    with pytest.raises(RuntimeError,match='exactly four threads'):
        driver.verify_julia_threads(project,run=lambda *a,**k:SimpleNamespace(stdout='E8_JULIA {"actual_threads":192}\n'))


def test_staged_preflight_rejects_old_operator_enum_even_when_ready(project):
    from shore_agent.symbolic_regression import EARLY_UNARY_OPERATORS, UNARY_OPERATORS
    warmup=[{'warmup_stages':[
        {'stage':'algebra','maxsize':24,'unary_operators':list(EARLY_UNARY_OPERATORS)},
        {'stage':'full','maxsize':48,'unary_operators':list(UNARY_OPERATORS)},
    ]} for _ in range(4)]
    health={'ready':4,'busy':0,'actual_julia_threads':[4]*4,'worker_warmup':warmup}
    def opener(url,timeout):
        return Response(json.dumps(health if url.endswith('/health') else
                                   {'data':[{'id':driver.run_e7.MODEL}]}).encode())
    planned=driver.plans(project,repeat='r02')
    driver.run_e7.preflight(planned,opener=opener)
    warmup[0]['warmup_stages'][0]['unary_operators']=['sqrt','abs']
    with pytest.raises(RuntimeError,match='exact.*operator enums'):
        driver.run_e7.preflight(planned,opener=opener)


def test_paired_plans_change_only_noise_ruleset_and_keep_budgets(project):
    clean,noisy=driver.plans(project,repeat='paired')
    assert clean['config']['environment']['noise'] is False
    assert noisy['config']['environment']['noise'] is True
    assert clean['config']['environment']['ruleset']=='e5'
    assert noisy['config']['environment']['ruleset']=='e4'
    for plan in (clean,noisy):
        assert len(plan['planned_runs'])==6
        assert plan['config']['model']['max_tokens_per_call']==4096
        assert plan['config']['environment']['wall_seconds']==300
        assert plan['config']['environment']['energy_budget']==10


def test_r06_uses_only_user_allocated_three_model_replicas(project,monkeypatch):
    calls=[]
    monkeypatch.setattr(driver,'verify_julia_threads',lambda p:{'actual_threads':4})
    monkeypatch.setattr(driver.run_e7,'run_study',lambda *a,**kw:calls.append(kw))
    opener=Opener()
    driver.run_study(project,repeat='r06',opener=opener)
    assert len(opener.calls)==4
    assert not any(':8000/' in url for url in opener.calls)
    assert calls[0]['model_endpoints']==tuple(f'http://127.0.0.1:{p}/v1' for p in (8001,8002,8003))


def test_r08_reuses_noisy_policy_on_current_three_replicas(project):
    noisy=driver.plans(project,repeat='r08')[0]
    old=driver.plans(project,repeat='r04')[0]
    assert noisy['config']==old['config']
    assert noisy['config']['environment']['noise'] is True
    assert noisy['config']['agent']['submission_fit_rmse_threshold']==.1
    assert noisy['config']['agent']['submission_time_remaining_seconds']==60
    registration=noisy['protocol_metadata']['repeat_registration']
    assert registration['evaluation_noise'] is False
    assert registration['parallelism']==3
    assert all(':8000/' not in url for url in registration['model_endpoints'])
