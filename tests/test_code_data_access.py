import copy

import numpy as np
import pytest

from code_sandbox.runner import get_record, input_layout, probe_arrays
from shore_agent.environment import Environment
from shore_agent.runtime import ToolRuntime
from shore_agent.code_execution import execute_code
from test_code_execution import docker_config


def probe():
    return {'probe_id': 'probe_0007', 'times': [2., 3., 4., 5.],
            'r_obs': [[2., 4.], [3., 6.], [4., 8.], [5., 10.]],
            'v_obs': [[1., 2.]] * 4, 'a_est_times': [3., 4.], 'a_est': [[0., 0.]] * 2}


def test_exact_alignment_uses_times_not_prefix_or_truncation():
    p = probe(); old = copy.deepcopy(p)
    s = probe_arrays(p, time_axis='acceleration')
    np.testing.assert_array_equal(s['t'], [3., 4.])
    np.testing.assert_array_equal(s['r'], [[3., 6.], [4., 8.]])
    assert s['alignment'] == 'exact' and 'estimate' in s['acceleration_source']
    s['r'][0, 0] = 999
    assert p == old
    assert 'a' not in probe_arrays(p)


def test_interpolation_requires_explicit_choice_and_never_extrapolates():
    p = probe(); p['a_est_times'] = [2.5, 4.5]
    with pytest.raises(ValueError, match='exactly match'):
        probe_arrays(p, 'acceleration')
    s = probe_arrays(p, 'acceleration', 'linear')
    np.testing.assert_array_equal(s['r'], [[2.5, 5.], [4.5, 9.]])
    assert s['alignment'] == 'linear'
    p['a_est_times'] = [1.5, 4.5]
    with pytest.raises(ValueError, match='no extrapolation'):
        probe_arrays(p, 'acceleration', 'linear')


@pytest.mark.parametrize('field,value', [
    ('a_est', [[0., 0.]]), ('a_est_times', []), ('times', [2., 3., 3., 5.]),
    ('v_obs', [[float('nan'), 2.]] * 4), ('r_obs', [[0., 0.]] * 3),
])
def test_invalid_arrays_are_rejected_without_repair(field, value):
    p = probe(); p[field] = value
    with pytest.raises(ValueError):
        probe_arrays(p, 'acceleration')


def test_helpers_only_expose_explicitly_loaded_records():
    p = probe(); inputs = {'p': [p]}
    assert get_record(inputs, 'p', 'probe_0007') == p
    with pytest.raises(KeyError, match='probe_0007'):
        get_record(inputs, 'p', 'probe_0008')
    with pytest.raises(KeyError, match='available aliases'):
        get_record(inputs, 'not_loaded', 'probe_0007')
    info = input_layout(inputs)
    assert info['p']['record_ids'] == ['probe_0007']
    assert info['p']['first_record_fields']['a_est']['first_item_shape'] == [2, 2]


def test_optional_files_and_acquired_metadata(tmp_path, monkeypatch):
    env = Environment({'physics_version': 'v4', 'noise': False})
    try:
        rt = ToolRuntime(env, tmp_path, code_config={'enabled': True})
        mission = rt.mission()['data']
        hints = mission['code_inputs']
        ph = next(h for h in hints if h['record_type'] == 'probe')
        assert ph['record_ids'] == ['probe_0001', 'probe_0002']
        assert ph['fields']['r_obs']['shape'] == [8, 2]
        assert ph['fields']['a_est']['shape'] == [6, 2]
        bh = next(h for h in hints if h['record_type'] == 'body_observation')
        assert bh['fields']['positions_obs']['shape'] == [8, 3, 2]
        seen = []
        def run(code, inputs, *args, files=None):
            seen.append(files)
            return {'status': 'success', 'result': 2, 'stdout': '', 'stderr': '', 'artifacts': []}
        monkeypatch.setattr('shore_agent.code_execution.execute_code', run)
        out = rt.execute('run_code', {'code': 'result = 1 + 1'})
        assert out['ok'] and seen == [{}]
        assert rt.store.get('code_execution', out['data']['execution_id'])['files'] == []
        assert not rt.execute('run_code', {'code': 'result=1', 'files': None})['ok']
        bad = rt.execute('run_code', {'code': 'result=1', 'files': ['observations/probe_9999.json']})
        assert not bad['ok'] and seen == [{}]
        observed = rt.execute('observe_body', {'times': [0., .5]})
        assert observed['ok']
        assert observed['data']['code_inputs'][0]['record_ids'] == [observed['data']['observation_id']]
        added = rt.execute('insert_probe', {'probes': [{'r0': [0., 0.], 'v0': [0., 1.], 'properties': {}}], 't0': 0., 'dt': .1, 'n_samples': 5})
        assert added['ok'], added
        assert added['data']['code_inputs'][0]['record_ids'] == [added['data']['probes'][0]['probe_id']]
        assert rt.mission()['data'] == mission
    finally:
        env.close()


def test_disabled_code_does_not_add_metadata(tmp_path):
    env = Environment({'physics_version': 'v4', 'noise': False})
    try:
        rt = ToolRuntime(env, tmp_path)
        assert 'code_inputs' not in rt.mission()['data']
        assert 'code_inputs' not in rt.execute('observe_body', {'times': [0.]})['data']
    finally:
        env.close()


def test_real_container_has_helpers_and_preserves_raw_inputs(tmp_path, docker_config):
    script = '''p = get_record("p", "probe_0007")
s = probe_arrays(p, time_axis="acceleration")
s["r"][0,0] = 99
result = {"info":input_info, "t":s["t"], "raw":p["r_obs"], "alignment":s["alignment"]}
'''
    r = execute_code(script, {'p': [probe()]}, {}, tmp_path / 'helper', docker_config, 30)
    assert r['status'] == 'success', r
    assert r['result']['t'] == [3., 4.]
    assert r['result']['raw'][1] == [3., 6.]
    assert r['result']['info']['p']['record_ids'] == ['probe_0007']
