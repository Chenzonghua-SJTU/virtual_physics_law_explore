"""Soft residual warnings use synthetic readouts, not hidden evaluation data."""
import copy
import json
import math

import pytest

from shore_agent.runtime import ToolRuntime
from test_e5_property_coverage import runtime, probe, acquire, fit


def diagnostic_runtime():
    value = ToolRuntime.__new__(ToolRuntime)
    value.task = {'position_noise_sigma': 0, 'velocity_noise_sigma': 0,
                  'reference_length': 10, 'velocity_limit': 3}
    return value


def errors(position=.005, velocity=.000015):
    return {'overall': {'position_rmse': position, 'velocity_rmse': velocity}}


def readouts():
    return [{'r_obs': [[3., 4.]], 'v_obs': [[0., 0.]]},
            {'r_obs': [[0., 0.]] * 3, 'v_obs': [[0., 0.]] * 3}]


def test_scales_weight_trajectories_equally_and_floor_zero_speed_at_public_reference():
    data = readouts()
    original = copy.deepcopy(data)
    checked = diagnostic_runtime()._residual_scale_check(data, errors())
    assert checked['status'] == 'available' and checked['warning'] is True
    assert checked['relative_warning_threshold'] == .001
    position, velocity = checked['metrics']['position'], checked['metrics']['velocity']
    assert position['observed_vector_rms'] == pytest.approx(math.sqrt(12.5))  # Not sample-weighted sqrt(25/4).
    assert position['normalization_scale'] == pytest.approx(math.sqrt(12.5))
    assert position['relative_rmse'] == pytest.approx(.005 / math.sqrt(12.5))
    assert position['warning'] is True
    assert velocity['observed_vector_rms'] == 0
    assert velocity['public_reference'] == 3 and velocity['normalization_scale'] == .03
    assert velocity['relative_rmse'] == .0005 and velocity['warning'] is False
    assert data == original
    json.dumps(checked, allow_nan=False)


def test_at_threshold_is_not_over_threshold_and_never_declares_a_pass():
    rt = diagnostic_runtime()
    rt.task.update(reference_length=100, velocity_limit=100)
    result = rt._residual_scale_check([{'r_obs': [[0, 0]], 'v_obs': [[0, 0]]}], errors(.001, .001))
    assert result['warning'] is False
    assert 'accepted' not in result and 'passed' not in result
    assert 'does not prove the law correct' in result['interpretation']


@pytest.mark.parametrize('changes,reason,status', [
    ({'position_noise_sigma': .01}, 'requires_explicitly_noise_free_readouts', 'not_applicable'),
    ({'velocity_noise_sigma': .01}, 'requires_explicitly_noise_free_readouts', 'not_applicable'),
    ({'velocity_noise_sigma': None}, 'noise_metadata_missing_or_invalid', 'unavailable'),
    ({'position_noise_sigma': False}, 'noise_metadata_missing_or_invalid', 'unavailable'),
])
def test_warning_requires_both_explicit_numeric_zero_noise_sigmas(changes, reason, status):
    rt = diagnostic_runtime()
    rt.task.update(changes)
    result = rt._residual_scale_check(readouts(), errors())
    assert result['status'] == status and result['reason'] == reason
    assert result['warning'] is None and result['metrics'] == {}


@pytest.mark.parametrize('field,bad', [('reference_length', None), ('reference_length', 0),
                                      ('velocity_limit', float('nan')), ('velocity_limit', True)])
def test_missing_or_invalid_reference_is_not_replaced_by_an_invented_scale(field, bad):
    rt = diagnostic_runtime()
    rt.task[field] = bad
    checked = rt._residual_scale_check(readouts(), errors())
    affected = checked['metrics']['position' if field == 'reference_length' else 'velocity']
    assert affected['status'] == 'unavailable'
    assert affected['warning'] is None and 'normalization_scale' not in affected
    json.dumps(checked, allow_nan=False)


@pytest.mark.parametrize('bad_errors', [None, {}, {'overall': None}, {'overall': {'position_rmse': -1}}])
def test_missing_or_invalid_residual_stays_unavailable(bad_errors):
    checked = diagnostic_runtime()._residual_scale_check(readouts(), bad_errors)
    assert checked['status'] == 'unavailable' and checked['warning'] is None


@pytest.mark.parametrize('bad_readouts', [[], [{}], [{'r_obs': [], 'v_obs': []}],
    [{'r_obs': [[float('nan'), 0]], 'v_obs': [[float('inf'), 0]]}],
    [{'r_obs': [[1e308, 1e308]], 'v_obs': [[1e308, 1e308]]}]])
def test_bad_readouts_never_generate_nonfinite_diagnostics(bad_readouts):
    checked = diagnostic_runtime()._residual_scale_check(bad_readouts, errors())
    assert checked['status'] == 'unavailable' and checked['warning'] is None
    json.dumps(checked, allow_nan=False)


@pytest.mark.parametrize('ruleset', ['e3', 'e4', 'e5'])
def test_fit_validation_diagnostics_are_e5_only_and_do_not_change_fit(tmp_path, ruleset):
    rt = runtime(tmp_path, ruleset)
    rt.task.update(position_noise_sigma=0, velocity_noise_sigma=0, reference_length=10, velocity_limit=3)
    acquire(rt, probe('train', {}), probe('test', {'load': 3, 'marker': 7}))
    law = fit(rt, ['train'])
    saved = rt.store.get('law', law['law_id'])
    result = rt.execute('validate_law', {'law_id': law['law_id'], 'test_probe_ids': ['test']})
    assert result['ok'], result
    assert rt.store.get('law', law['law_id']) == saved
    for record in (law, result['data']):
        if ruleset == 'e5':
            assert record['residual_scale_check']['status'] == 'available'
            assert record['residual_scale_check']['warning'] is False
        else:
            assert 'residual_scale_check' not in record
    assert set(rt.environment.requests) == {'budget'}
    assert law['fitted_parameters'] == {} and law['law_spec'] == {'ax': '0', 'ay': '0'}
    assert law['errors']['overall']['position_rmse'] < 1e-10


def test_visible_residual_warning_does_not_block_a_model_chosen_submission(tmp_path):
    rt = runtime(tmp_path)
    rt.task.update(position_noise_sigma=0, velocity_noise_sigma=0, reference_length=10, velocity_limit=3)
    data = probe('train', {})
    data['r_obs'][1][0] += .1
    data['v_obs'][1][0] += .1
    acquire(rt, data)
    law = fit(rt, ['train'])
    assert law['residual_scale_check']['warning'] is True
    original_request = rt.environment.request
    def request(method, **kwargs):
        if method == 'end_session':
            return {'ok': True, 'data': {'session_ended': True}, 'error': None}
        return original_request(method, **kwargs)
    rt.environment.request = request
    submitted = rt.execute('submit', {'law_id': law['law_id'],
        'claims': {'dynamics_order': 2, 'hidden_matter': False, 'time_dependence': False},
        'physical_explanation': '合成工程测试：即使当前候选有可见残差，诊断也不替代模型的提交决定。'})
    assert submitted['ok'] and submitted['data']['status'] == 'accepted'
    assert submitted['data']['session_ended'] is True
