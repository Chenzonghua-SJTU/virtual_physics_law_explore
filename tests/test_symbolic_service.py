"""Real subprocess and HTTP boundaries without importing or installing PySR."""
import http.client
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from shore_agent import symbolic_service
from shore_agent.symbolic_service import SymbolicServiceError, WorkerPool, make_server, search_remote


FAKE_WORKER = r'''
import json, pathlib, sys, time, subprocess
directory=pathlib.Path(sys.argv[1])
(directory/'ready.json').write_text('{"ready":true,"actual_julia_threads":4}')
def save(path,data):
 temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data));temp.replace(path)
for line in sys.stdin:
 job=pathlib.Path(json.loads(line)['job_directory'])
 data=json.loads((job/'request.json').read_text())
 probe=data['probes'][0]
 result={'status':'completed','elapsed_seconds':.01,'search_axes_completed':['ax','ay'],
         'output_directory':'/private/worker/path',
         'axis_equations':{'ax':[{'source':'2.5*x','complexity':3,'loss':.01,'origin':'pysr',
                                 'parameter_count':1,'domain_valid':True,'host_path':'/private/secret'}],
                           'ay':[{'source':'0','complexity':1,'loss':0,'origin':'constant_initialization'}]},
         'rejection_counts':{'initial_domain':2},
         'rejection_examples':[{'stage':'domain','reason':'initial_domain','ax':'vx/t','ay':'0',
                                'host_path':'/private/secret'}],
         'candidate_selection':{'strategy':'power_law','rollout_checks':1,'debug_path':'/private/secret'},
         'data_quality':{'sample_counts':{'p':30},'body_positions_included':False,'host_path':'/private/secret'},
         'search_stages':[{'stage':'axis_0_algebra','elapsed_seconds':.01,'output_directory':'/private/secret'}],
         'basis_diagnostics':{'status':'completed','selected_terms':['x','y'],'debug_path':'/private/secret'},
         'geometric_features':{'radius':'sqrt(x*x+y*y)'},
         'projection_diagnostics':{'radial_supported':True,'relative_tangential_residual':.001},
         'axis_candidates':{'ax':[{'component':'ax','source':'2.5*x','law_spec':{'ax':'c1 * x','ay':'0'},
                                  'parameter_spec':[{'name':'c1','initial':2.5}], 'parameter_count':1,
                                  'joint_fit_ready':False,'parameter_budget_compatible':True,
                                  'loss':.01,'complexity':3,'origin':'pysr','host_path':'/private/secret'}],
                            'ay':[]},
         'candidates':[{'law_spec':{'ax':'c1*x','ay':'0'},
                        'parameter_spec':[{'name':'c1','initial':float(data['random_state'])}],
                        'discovery_probe_ids':['wrong'], 'host_path':'/private/secret',
                        'component_sources':['pysr','constant_initialization'],
                        'parameter_sharing':{'status':'data_validated','groups':[['c1','c2']],
                                             'host_path':'/private/secret'},
                        'joint_fit_ready':True,'prediction_accuracy_status':'not_independently_validated',
                        'parameter_count':1,'initial_domain_check':{'status':'passed','probe_count':1},
                        'short_rollout_check':{'status':'passed','probe_count':1,'position_rmse':.002}}],
         'used_probe_ids':['wrong']}
 save(job/'progress.json',dict(result,status='running',search_axes_completed=['ax']))
 if probe.get('crash'):
  sys.exit(2)
 if probe.get('error'):
  save(job/'result.json',{'status':'error','message':'/private/secret'});continue
 if probe.get('spawn_child'):
  subprocess.Popen([sys.executable,'-c',"import pathlib,time;time.sleep(.7);pathlib.Path("+repr(probe['marker'])+").write_text('alive')"])
 time.sleep(probe.get('sleep',0))
 save(job/'result.json',result)
'''


def wait_until(condition, seconds=4):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(.01)
    pytest.fail('condition not reached')


@pytest.fixture
def pool(tmp_path):
    value = WorkerPool(1, spool_dir=tmp_path,
        worker_command_factory=lambda directory: [sys.executable, '-u', '-c', FAKE_WORKER, str(directory)])
    wait_until(lambda: value.health()['ready'] == 1)
    try:
        yield value
    finally:
        value.close()


def test_each_job_has_isolated_input_output_and_server_owned_provenance(pool):
    first = pool.search([{'probe_id': 'a'}], 2, random_state=11)
    second = pool.search([{'probe_id': 'b'}], 2, random_state=22)
    assert first['used_probe_ids'] == ['a'] and second['used_probe_ids'] == ['b']
    assert first['candidates'][0]['discovery_probe_ids'] == ['a']
    assert second['candidates'][0]['parameter_spec'][0]['initial'] == 22
    assert first['candidates'][0]['parameter_spec'][0]['initial'] == 11
    assert '/private/' not in json.dumps(first)
    assert not list((pool.root / 'jobs').iterdir())


def test_worker_survives_juliacall_nonblocking_stdin_import_and_multiple_searches(tmp_path):
    fake_package = tmp_path / 'fake_package'
    fake_package.mkdir()
    (fake_package / 'pysr.py').write_text('''
import os, pathlib, sys
os.set_blocking(0, False)
(pathlib.Path(sys.argv[1])/'nonblocking-import').write_text(str(os.get_blocking(0)))
class PySRRegressor:
    def __init__(self, **kwargs): pass
    def fit(self, *args, **kwargs): os.set_blocking(0, False)
''')
    (fake_package/'juliacall.py').write_text('''
class Main:
    @staticmethod
    def seval(code):
        assert code == 'Threads.nthreads()'
        return 4
''')
    command = '''
import os, sys
sys.path.insert(0, sys.argv[2])
from shore_agent import symbolic_regression
from shore_agent.symbolic_service import _worker
def search(probes, budget, **kwargs):
    os.set_blocking(0, False)
    return {'status':'completed', 'elapsed_seconds':0.01,
            'search_axes_completed':['ax','ay'],
            'candidates':[{'law_spec':{'ax':'c1*x','ay':'0'},
                           'parameter_spec':[{'name':'c1','initial':kwargs['random_state']}]}]}
symbolic_regression.run_search = search
_worker(sys.argv[1])
'''
    value = WorkerPool(1, spool_dir=tmp_path,
        worker_command_factory=lambda directory: [sys.executable, '-u', '-c', command,
                                                  str(directory), str(fake_package)])
    try:
        wait_until(lambda: value.health()['ready'] == 1)
        worker = value.workers[0]
        assert (worker.directory / 'nonblocking-import').read_text() == 'False'
        # The parent keeps its write end open without sending a command.
        time.sleep(.1)
        assert value.health()['ready'] == 1 and worker.process.poll() is None
        for index in (11, 22):
            result = value.search([{'probe_id': 'p' + str(index)}], 2, random_state=index)
            assert result['candidates'][0]['parameter_spec'][0]['initial'] == index
            time.sleep(.05)
            assert value.health()['ready'] == 1 and value.workers[0] is worker
    finally:
        value.close()


def test_no_hidden_queue_when_pool_is_busy(pool):
    outcomes = []
    thread = threading.Thread(target=lambda: outcomes.append(pool.search([{'probe_id': 'busy', 'sleep': .4}], 2)))
    thread.start()
    wait_until(lambda: pool.health()['busy'] == 1)
    started = time.monotonic()
    with pytest.raises(SymbolicServiceError) as exc:
        pool.search([{'probe_id': 'next'}], 1)
    assert exc.value.code == 'symbolic_service_busy' and exc.value.http_status == 409
    assert time.monotonic() - started < .1
    thread.join(3)
    assert len(outcomes) == 1


def test_hard_timeout_kills_reaps_owned_group_recovers_checkpoint_and_rewarms(pool, tmp_path):
    marker = tmp_path / 'child-survived'
    old = pool.workers[0]
    started = time.monotonic()
    result = pool.search([{'probe_id': 'slow', 'sleep': 5, 'spawn_child': True, 'marker': str(marker)}], .15)
    assert time.monotonic() - started < .6
    assert result['status'] == 'timeout' and result['stop_reason'] == 'hard_timeout'
    assert result['worker_search_budget_seconds'] < .15
    assert result['cleanup_reserve_seconds'] == pytest.approx(.015)
    assert result['service_elapsed_seconds'] == result['elapsed_seconds']
    assert result['search_axes_completed'] == ['ax']
    assert result['candidates'][0]['discovery_probe_ids'] == ['slow']
    assert old.process.poll() is not None and old.stopped
    wait_until(lambda: pool.health()['ready'] == 1)
    assert pool.workers[0].process.pid != old.process.pid
    time.sleep(.8)
    assert not marker.exists()
    assert pool.search([{'probe_id': 'after'}], 2)['status'] == 'completed'


def test_worker_crash_is_generic_and_pool_can_recover(pool):
    with pytest.raises(SymbolicServiceError) as exc:
        pool.search([{'probe_id': 'crash', 'crash': True}], 1)
    assert exc.value.code == 'symbolic_worker_failed'
    wait_until(lambda: pool.health()['ready'] == 1)


def test_worker_exception_does_not_expose_host_paths(pool):
    with pytest.raises(SymbolicServiceError) as exc:
        pool.search([{'probe_id': 'error', 'error': True}], 1)
    assert str(exc.value) == 'symbolic_search_failed'
    assert pool.health()['ready'] == 1


@pytest.mark.parametrize('endpoint', [
    'http://example.com:8890', 'https://127.0.0.1:8890', 'http://127.0.0.1:8890/other',
    'http://user:password@127.0.0.1:8890', 'http://localhost:8890/search?data=secret',
    'http://127.0.0.1', 'http://127.0.0.1:8890#fragment', 'http://127.0.0.1:99999',
])
def test_remote_client_rejects_nonlocal_or_ambiguous_endpoints(endpoint):
    with pytest.raises(SymbolicServiceError) as exc:
        search_remote([{'probe_id': 'p'}], 1, endpoint)
    assert exc.value.code == 'invalid_symbolic_endpoint'


def test_http_round_trip_and_request_path_control(pool):
    server = make_server(pool, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        endpoint = f'http://localhost:{server.server_port}'
        result = search_remote([{'probe_id': 'p'}], 2, endpoint)
        assert result['used_probe_ids'] == ['p']
        assert result['candidates'][0]['parameter_spec'][0]['initial'] == 42
        assert result['tool_client_wall_seconds'] >= result['service_elapsed_seconds']
        assert result['requested_time_budget_seconds'] == 2
        assert result['axis_equations']['ax'][0]['source'] == '2.5*x'
        assert result['axis_equations']['ax'][0]['parameter_count'] == 1
        assert result['rejection_counts'] == {'initial_domain': 2}
        assert result['rejection_examples'][0]['ax'] == 'vx/t'
        assert result['candidate_selection'] == {'strategy': 'power_law', 'rollout_checks': 1}
        assert result['candidates'][0]['short_rollout_check']['position_rmse'] == .002
        assert result['candidates'][0]['initial_domain_check']['status'] == 'passed'
        assert result['candidates'][0]['parameter_sharing'] == {'status':'data_validated','groups':[['c1','c2']]}
        assert result['candidates'][0]['prediction_accuracy_status'] == 'not_independently_validated'
        assert result['axis_candidates']['ax'][0]['law_spec'] == {'ax':'c1 * x','ay':'0'}
        assert result['axis_candidates']['ax'][0]['joint_fit_ready'] is False
        assert result['axis_candidates']['ax'][0]['discovery_probe_ids'] == ['p']
        assert result['data_quality'] == {'sample_counts':{'p':30},'body_positions_included':False}
        assert result['search_stages']==[{'stage':'axis_0_algebra','elapsed_seconds':.01}]
        assert result['basis_diagnostics']=={'status':'completed','selected_terms':['x','y']}
        assert result['geometric_features']=={'radius':'sqrt(x*x+y*y)'}
        assert result['projection_diagnostics']['radial_supported'] is True
        assert '/private/' not in json.dumps(result)
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port)
        connection.request('GET', '/health')
        response = connection.getresponse()
        health=json.load(response)
        assert response.status == 200 and health['ready'] == 1
        assert health['actual_julia_threads']==[4]
        connection.close()
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port)
        connection.request('POST', '/search', json.dumps({'probes': [{'probe_id': 'p'}],
                           'time_budget_seconds': 1, 'job_directory': '/private/secret'}),
                           {'Content-Type': 'application/json'})
        response = connection.getresponse()
        assert response.status == 400 and '/private/' not in response.read().decode()
        connection.close()
    finally:
        server.shutdown(); server.server_close(); thread.join(2)


def test_close_terminates_idle_owned_workers_and_rejects_more_jobs(pool):
    worker = pool.workers[0]
    pool.close()
    assert worker.process.poll() is not None
    with pytest.raises(SymbolicServiceError, match='service_closed'):
        pool.search([{'probe_id': 'p'}], 1)


def test_missing_worker_interpreter_reports_failed_instead_of_warming_forever(tmp_path):
    pool = WorkerPool(1, worker_python=tmp_path/'missing-python', spool_dir=tmp_path)
    try:
        wait_until(lambda: pool.health()['failed'] == 1)
        assert pool.health()['status'] == 'failed'
        assert pool.health()['warming'] == 0
    finally:
        pool.close()


def test_worker_venv_executable_symlink_is_not_resolved(tmp_path):
    executable = tmp_path / 'venv-python'
    executable.symlink_to(sys.executable)
    pool = WorkerPool(1, worker_python=executable, spool_dir=tmp_path,
        worker_command_factory=lambda directory: [sys.executable, '-u', '-c', FAKE_WORKER, str(directory)])
    try:
        wait_until(lambda: pool.health()['ready'] == 1)
        assert pool.worker_python == str(executable)
    finally:
        pool.close()


def test_validation_time_is_charged_and_expired_request_never_reaches_worker(pool, monkeypatch):
    original = symbolic_service._request
    worker = pool.workers[0]

    def slow_validation(*args, **kwargs):
        time.sleep(.12)
        return original(*args, **kwargs)

    monkeypatch.setattr(symbolic_service, '_request', slow_validation)
    result = pool.search([{'probe_id': 'late'}], .1)
    assert result['stop_reason'] == 'budget_exhausted_before_dispatch'
    assert result['elapsed_seconds'] >= .12
    assert result['service_budget_exceeded'] is True
    assert result['worker_search_budget_seconds'] == 0
    assert pool.workers[0] is worker and pool.health()['ready'] == 1
    assert not list((pool.root / 'jobs').iterdir())


def test_service_elapsed_includes_completed_cleanup(pool, monkeypatch):
    original = symbolic_service.shutil.rmtree

    def slow_cleanup(*args, **kwargs):
        time.sleep(.025)
        return original(*args, **kwargs)

    monkeypatch.setattr(symbolic_service.shutil, 'rmtree', slow_cleanup)
    started = time.monotonic()
    result = pool.search([{'probe_id': 'cleanup'}], 1)
    actual = time.monotonic() - started
    assert result['elapsed_seconds'] >= .025
    assert result['elapsed_seconds'] <= actual < result['elapsed_seconds'] + .05
    assert result['cleanup_pending'] is False
    assert result['service_budget_exceeded'] is False


def test_slow_cleanup_is_explicitly_pending_instead_of_blocking_response(pool, monkeypatch):
    original = symbolic_service.shutil.rmtree
    gate = threading.Event()

    def blocked_cleanup(*args, **kwargs):
        gate.wait(2)
        return original(*args, **kwargs)

    monkeypatch.setattr(symbolic_service.shutil, 'rmtree', blocked_cleanup)
    try:
        started = time.monotonic()
        result = pool.search([{'probe_id': 'cleanup'}], .3)
        assert time.monotonic() - started < .5
        assert result['cleanup_pending'] is True
        assert result['elapsed_seconds'] >= .04
    finally:
        gate.set()
        wait_until(lambda: not list((pool.root / 'jobs').iterdir()))


def test_result_validation_overrun_is_reported_honestly(pool, monkeypatch):
    original = symbolic_service._public_result

    def slow_validation(*args, **kwargs):
        time.sleep(.15)
        return original(*args, **kwargs)

    monkeypatch.setattr(symbolic_service, '_public_result', slow_validation)
    result = pool.search([{'probe_id': 'result'}], .1)
    assert result['status'] == 'timeout' and result['stop_reason'] == 'service_budget_exceeded'
    assert result['service_budget_exceeded'] is True
    assert result['elapsed_seconds'] >= .15


def test_slow_reap_uses_background_wait_and_reports_pending(pool, monkeypatch):
    worker = pool.workers[0]
    original = worker.process.wait
    gate = threading.Event()
    called = []

    def slow_wait(timeout=None):
        called.append(timeout)
        if timeout is not None:
            raise subprocess.TimeoutExpired(worker.process.args, timeout)
        gate.wait(2)
        return original()

    monkeypatch.setattr(worker.process, 'wait', slow_wait)
    try:
        started = time.monotonic()
        result = pool.search([{'probe_id': 'reap', 'sleep': 2}], .2)
        assert time.monotonic() - started < .4
        assert result['worker_reap_pending'] is True
        assert result['cleanup_pending'] is True
        assert called[0] <= .05
    finally:
        gate.set()
        wait_until(worker.reaped.is_set)
        wait_until(lambda: not list((pool.root / 'jobs').iterdir()))


def test_excess_audit_rows_are_explicitly_bounded_without_changing_formula():
    candidate = {'law_spec': {'ax': 'c1*x', 'ay': 'c2*y'},
                 'parameter_spec': [{'name': 'c1', 'initial': -0.03}, {'name': 'c2', 'initial': -.07}]}
    raw = {'status': 'completed', 'candidates': [candidate],
           'axis_equations': {'ax': [{'source': f'{i}.0*x', 'complexity': 3, 'loss': .1}
                                    for i in range(180)], 'ay': []}}
    first = symbolic_service._public_result(raw, ['p'])
    assert first['candidates'][0]['law_spec'] == candidate['law_spec']
    assert first['candidates'][0]['parameter_spec'] == candidate['parameter_spec']
    assert len(first['axis_equations']['ax']) == 160
    assert first['transport_audit_omitted_rows'] == {'ax': 20}
    assert first['candidate_selection']['full_axis_equations_retained'] is False
    # search_remote applies the public boundary again; omission accounting must survive.
    assert symbolic_service._public_result(first, ['p']) == first


def test_over_budget_axis_survives_both_boundaries_and_audit_trimming():
    from shore_agent.symbolic_regression import export_candidate, FEATURES, MAX_INTERNAL_PARAMETERS
    source = '.1*y+.2*x*y+.3*y**2+.4*x**2*y+.5*y**3+.6*t*y'
    exported = export_candidate('0', source, FEATURES, _parameter_limit=MAX_INTERNAL_PARAMETERS)
    parameters = exported['parameter_spec']
    component = {**exported, 'component': 'ay', 'source': source, 'parameter_count': 6,
                 'joint_fit_ready': False, 'parameter_budget_compatible': False,
                 'loss': 1e-9, 'complexity': 23, 'origin': 'pysr'}
    raw = {'status':'completed', 'candidates':[], 'axis_candidates':{'ax':[], 'ay':[component]},
           'axis_equations':{'ax':[], 'ay':[{'source':'x'*4000, 'complexity':40, 'loss':.1} for _ in range(160)]}}
    first = symbolic_service._public_result(raw, ['a', 'b'])
    second = symbolic_service._public_result(first, ['a', 'b'])
    assert second == first
    assert second['axis_candidates']['ay'][0]['parameter_spec'] == parameters
    assert second['axis_candidates']['ay'][0]['law_spec'] == component['law_spec']
    assert second['axis_candidates']['ay'][0]['discovery_probe_ids'] == ['a', 'b']
    assert second['transport_audit_omitted_rows']['ay'] > 0
    assert len(symbolic_service._json_bytes(second)) <= symbolic_service.MAX_RESPONSE_BYTES


@pytest.mark.parametrize('update', [
    {'joint_fit_ready':True}, {'component':'ay'}, {'parameter_count':2},
    {'parameter_budget_compatible':False}, {'parameter_spec':[{'name':'c1','initial':float('nan')}]},
])
def test_axis_metadata_cannot_claim_complete_or_misrepresent_parameter_budget(update):
    row = {'component':'ax', 'source':'.1*x', 'law_spec':{'ax':'c1 * x','ay':'0'},
           'parameter_spec':[{'name':'c1','initial':.1}], 'parameter_count':1,
           'joint_fit_ready':False, 'parameter_budget_compatible':True}
    row.update(update)
    with pytest.raises(SymbolicServiceError, match='invalid_worker_result'):
        symbolic_service._public_result({'axis_candidates':{'ax':[row]}}, ['p'])


def test_both_operator_enums_are_warmed_before_worker_ready(tmp_path):
    calls=[]
    class Model:
        def __init__(self,**options): self.options=options
        def fit(self,X,y,**kwargs):
            calls.append(self.options)
            assert X.shape==(64,7) and len(y)==64
    class Julia:
        @staticmethod
        def seval(code): return 4
    result=symbolic_service._warmup_models(tmp_path,Model,Julia)
    assert result['actual_julia_threads']==4
    assert [r['stage'] for r in result['warmup_stages']]==['algebra','full']
    assert calls[0]['unary_operators']==['sqrt','abs'] and calls[0]['maxsize']==24
    assert calls[1]['unary_operators']==['sin','cos','exp','sqrt','log','abs']
    assert calls[1]['maxsize']==48
    Julia.seval=lambda code:192
    with pytest.raises(RuntimeError,match='four_julia_threads'):
        symbolic_service._warmup_models(tmp_path,Model,Julia)


def test_worker_environment_forces_juliacall_thread_and_signal_settings(pool):
    assert pool.worker_env['PYTHON_JULIACALL_THREADS']==pool.worker_env['JULIA_NUM_THREADS']=='4'
    assert pool.worker_env['PYTHON_JULIACALL_HANDLE_SIGNALS']=='yes'
    assert pool.worker_env['OPENBLAS_NUM_THREADS']==pool.worker_env['OMP_NUM_THREADS']=='1'
