import base64
import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

from shore_agent.code_execution import _decode, execute_code, sandbox_info, validate_output_schema
from shore_agent.environment import Environment
from shore_agent.runtime import ToolRuntime
from shore_agent.schemas import SCHEMAS, tool_schemas


def test_baseline_surface_unchanged_and_code_is_opt_in():
    original = copy.deepcopy(SCHEMAS)
    enabled = tool_schemas(True)
    assert len(SCHEMAS) == 8 and len(enabled) == 9
    assert tool_schemas(False) == original
    assert SCHEMAS == original
    assert enabled[-1]['function']['name'] == 'run_code'


@pytest.mark.parametrize('schema', [{'$ref': 'https://example.com/schema'}, {'pattern': '(a+)+$'},
    {'properties': {'x': {'$ref': 'file:///etc/passwd'}}}, {'type': 'invalid'}])
def test_output_schema_cannot_resolve_external_resources(schema):
    with pytest.raises(Exception):
        validate_output_schema(schema)


def response(**updates):
    return dict(status='success', result={'value': 3}, error=None, stdout='', stderr='',
                compute_seconds=.1, cpu_seconds_reported=.05, peak_rss_kib_reported=1234,
                artifacts=[], **updates)


def test_output_contract_and_artifact_traversal_are_checked_on_host(tmp_path):
    result = _decode(response(), tmp_path / 'good', {'type': 'object', 'required': ['missing']})
    assert result['status'] == 'schema_error'
    for name in ('../escape.txt', '/tmp/escape.txt', 'x.html', 'x.svg'):
        r = response()
        r['artifacts'] = [{'name': name, 'base64': base64.b64encode(b'bad').decode()}]
        with pytest.raises(ValueError):
            _decode(r, tmp_path / 'bad', {})
    assert not (tmp_path / 'bad').exists()


def test_input_record_provenance_full_arrays_and_immutable_cache(tmp_path, monkeypatch):
    env = Environment({'physics_version': 'v4', 'noise': False})
    try:
        rt = ToolRuntime(env, tmp_path, code_config={'enabled': True})
        rt.mission()
        rid = next(iter(rt.store.records['probe']))
        original = copy.deepcopy(rt.store.records['probe'][rid])
        seen = []

        def run(code, inputs, schema, artifact_dir, config, timeout, files=None):
            seen.append(copy.deepcopy(files))
            data=json.loads(base64.b64decode(files[f'observations/{rid}.json']))
            assert len(data['r_obs']) == 8
            data['r_obs'][0][0] = 999
            return dict(status='success', result={'n': 8}, elapsed_seconds=.01, artifacts=[])

        monkeypatch.setattr('shore_agent.code_execution.execute_code', run)
        args = dict(code='result = {}', files=[f'observations/{rid}.json'])
        reply = rt.execute('run_code', args)
        assert reply['ok'] and reply['data']['status'] == 'success'
        execution = reply['data']['execution_id']
        record = rt.store.get('code_execution', execution)
        raw=rt.files.read_bytes(f'observations/{rid}.json')
        assert record['files'][0]['sha256'] == hashlib.sha256(raw).hexdigest()
        assert rt.store.get('probe', rid) == original
        assert rt.execute('read_file', {'path':f'analyses/{execution}/record.json'})['ok']
        args['files'] = ['observations/probe_never_acquired.json']
        assert not rt.execute('run_code', args)['ok']
        assert len(seen) == 1
    finally:
        env.close()


@pytest.fixture
def docker_config():
    if os.environ.get('SHORE_CODE_INTEGRATION') != '1':
        pytest.skip('Set SHORE_CODE_INTEGRATION=1 to run real isolated Docker tests')
    config = {'timeout_seconds': 20, 'memory_mb': 256}
    assert sandbox_info(config)['available'], 'Build code_sandbox image first'
    return config


def test_real_scientific_code_artifact_and_error_retry(tmp_path, docker_config):
    code = '''import numpy as np
from scipy.optimize import least_squares
from pathlib import Path
def analyze(inputs):
    x = np.array(inputs['x'])
    fit = least_squares(lambda p: p[0]*x - 3*x, [1.0])
    Path('output/test.txt').write_text('computed')
    print('done')
    return {'slope': float(fit.x[0])}
'''
    schema = {'type': 'object', 'required': ['slope'], 'properties': {'slope': {'type': 'number'}}}
    result = execute_code(code, {'x': [1, 2, 3]}, schema, tmp_path / 'artifacts', docker_config, 30)
    assert result['status'] == 'success', result
    assert result['result']['slope'] == pytest.approx(3)
    assert 'done' in result['stdout']
    assert (tmp_path / 'artifacts/test.txt').read_text() == 'computed'
    error = execute_code('def analyze(inputs): return 1/0', {}, {}, tmp_path / 'error', docker_config, 30)
    assert error['status'] == 'error'
    assert 'ZeroDivisionError' in error['error']['traceback']
    retry = execute_code('def analyze(inputs): return 1', {}, {'type': 'integer'}, tmp_path / 'retry', docker_config, 30)
    assert retry['status'] == 'success' and retry['result'] == 1


def test_real_no_host_truth_network_or_secrets(tmp_path, docker_config, monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-secret-not-for-container')
    secret = tmp_path / 'truth.txt'
    secret.write_text('host-only-sentinel')
    code = '''import os, socket
from pathlib import Path
def analyze(inputs):
    checks = {}
    try: Path(inputs['host_path']).read_text(); checks['host_denied'] = False
    except OSError: checks['host_denied'] = True
    try: import shore_sim; checks['truth_denied'] = False
    except ImportError: checks['truth_denied'] = True
    try: socket.create_connection(('1.1.1.1', 443), 1); checks['network_denied'] = False
    except OSError: checks['network_denied'] = True
    checks['key_absent'] = 'DEEPSEEK_API_KEY' not in os.environ
    checks['docker_socket_absent'] = not Path('/var/run/docker.sock').exists()
    try: Path('/opt/shore/injected').write_text('x'); checks['root_read_only'] = False
    except OSError: checks['root_read_only'] = True
    return checks
'''
    result = execute_code(code, {'host_path': str(secret)}, {}, tmp_path / 'artifacts', docker_config, 30)
    assert result['status'] == 'success', result
    assert all(result['result'].values()), result


def test_real_timeout_memory_and_finite_output(tmp_path, docker_config):
    timeout = execute_code('def analyze(inputs):\n while True: pass', {}, {}, tmp_path / 'loop',
                           dict(docker_config, timeout_seconds=1), 30)
    assert timeout['status'] == 'timeout', timeout
    assert timeout['elapsed_seconds'] < 12
    memory = execute_code('def analyze(inputs): return bytearray(1024**3)', {}, {}, tmp_path / 'memory', docker_config, 30)
    assert memory['status'] == 'memory_limit', memory
    nan = execute_code('def analyze(inputs): return float("nan")', {}, {}, tmp_path / 'nan', docker_config, 30)
    assert nan['status'] == 'error', nan


def test_real_previous_result_is_explicit_input_not_global_state(tmp_path, docker_config):
    first = execute_code('value=10\ndef analyze(inputs): return value', {}, {}, tmp_path/'first', docker_config, 30)
    second = execute_code('def analyze(inputs): return {"value": inputs["previous"]+1, "state_leaked": "value" in globals()}',
                          {'previous': first['result']}, {}, tmp_path/'second', docker_config, 30)
    assert second['result'] == {'value': 11, 'state_leaked': False}


def test_real_symbolic_analysis_plot_and_bounded_logging(tmp_path, docker_config):
    code = '''import sympy as sp
import matplotlib.pyplot as plt
def analyze(inputs):
    x = sp.symbols('x')
    derivative = sp.diff(x**3, x)
    plt.plot([0,1,2], [0,1,4])
    plt.savefig('output/curve.png')
    print('z'*50000)
    return {'derivative': str(derivative)}
'''
    r = execute_code(code, {}, {}, tmp_path/'plot', dict(docker_config, memory_mb=512), 30)
    assert r['status'] == 'success', r
    assert r['result'] == {'derivative': '3*x**2'}
    assert (tmp_path/'plot/curve.png').read_bytes().startswith(b'\x89PNG')
    assert len(r['stdout']) < 17000 and '[output truncated]' in r['stdout']
