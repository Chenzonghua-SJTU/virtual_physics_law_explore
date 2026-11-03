"""Temporal input/state contract checks, without invoking a research model."""
import copy
import importlib.util
import json

import numpy as np
import pytest

from shore_agent.expressions import BodyTimeCoverageError, Expression, ExpressionError, body_positions
from shore_agent.numerics import fit, rollout
from shore_agent.submission import export_submission


def moving_context():
    return {'kind': 'observed_body_trajectories', 'body_ids': ['visible'],
            'times': [0., 2., 6.], 'positions': [[[1., 4.]], [[5., 4.]], [[13., 4.]]],
            'observation_ids': ['measured_a', 'measured_b']}


def moving_acceleration_probe(k=.4, t0=3.):
    times = np.linspace(t0, t0 + 2, 21)
    tau = times - t0
    a0 = 1 + 2*t0
    r = np.column_stack([.2 + .3*tau + k*(a0*tau**2/2 + tau**3/3), -.1 + .7*tau])
    v = np.column_stack([.3 + k*(a0*tau + tau**2), np.full_like(tau, .7)])
    return {'probe_id': 'controlled', 'times': times.tolist(),
            'initial_conditions': {'r0': [.2, -.1], 'v0': [.3, .7], 't0': t0, 'properties': {}},
            'r_obs': r.tolist(), 'v_obs': v.tolist()}


LAW = {'ax': 'k*sum_b(bx)', 'ay': '0'}


def test_body_interpolation_uses_absolute_time_and_preserves_input():
    context = moving_context()
    before = copy.deepcopy(context)
    np.testing.assert_allclose(body_positions(context, 3.5), [[8, 4]])
    np.testing.assert_allclose(body_positions(context, 6 + 1e-12), [[13, 4]])
    assert context == before
    # Historical static data remain independent of t.
    np.testing.assert_array_equal(body_positions([{'position': [8, 4]}], 100), [[8, 4]])


@pytest.mark.parametrize('t', [None, -.01, 6.01])
def test_body_context_refuses_missing_time_or_extrapolation(t):
    with pytest.raises(BodyTimeCoverageError) as caught:
        body_positions(moving_context(), t)
    assert caught.value.code == 'body_time_coverage'


@pytest.mark.parametrize('change', [
    {'times': [0, 0, 6]}, {'body_ids': ['a', 'a']}, {'positions': [[[0, 0]]]},
    {'times': [0, 2, float('nan')]}, {'positions': [[[1, 4]], [[5, 4]], [[float('inf'), 4]]]},
])
def test_invalid_body_context_is_rejected(change):
    with pytest.raises(ExpressionError):
        body_positions(dict(moving_context(), **change), 1.)


def test_expression_resolves_current_body_state_without_averaging():
    expression = Expression(LAW, [{'name': 'k', 'initial': .4}])
    assert expression.uses_bodies
    np.testing.assert_allclose(expression.acceleration(3, [0, 0], [0, 0], moving_context(), {}, {'k': .4}), [2.8, 0])
    np.testing.assert_allclose(expression.acceleration(5, [0, 0], [0, 0], moving_context(), {}, {'k': .4}), [4.4, 0])


def test_rollout_and_fit_use_changing_body_state_and_do_not_reset_t0():
    context = moving_context()
    before = copy.deepcopy(context)
    probe = moving_acceleration_probe()
    prediction = rollout(LAW, {'k': .4}, probe, context)
    np.testing.assert_allclose(prediction['r_pred'], probe['r_obs'], atol=1e-8)
    np.testing.assert_allclose(prediction['v_pred'], probe['v_obs'], atol=1e-8)
    result = fit(LAW, [{'name': 'k', 'initial': .2}], [probe], context)
    assert result['converged']
    assert result['fitted_parameters']['k'] == pytest.approx(.4, abs=1e-7)
    assert result['errors']['overall']['position_rmse'] < 1e-7
    assert context == before


def test_missing_coverage_is_reported_before_fitting():
    probe = moving_acceleration_probe(t0=5)
    with pytest.raises(BodyTimeCoverageError):
        fit(LAW, [{'name': 'k', 'initial': .2}], [probe], moving_context())
    with pytest.raises(BodyTimeCoverageError):
        rollout(LAW, {'k': .4}, probe, moving_context())


def test_state_only_law_does_not_require_body_coverage_or_call_provider():
    probe = moving_acceleration_probe(t0=10)
    law = {'ax': 'a', 'ay': '0'}
    expression = Expression(law, [{'name': 'a', 'initial': 0}])
    assert not expression.uses_bodies
    np.testing.assert_array_equal(expression.acceleration(10, [0, 0], [0, 0], moving_context(), {}, {'a': 0}), [0, 0])
    assert rollout(law, {'a': 0}, probe, moving_context())['times'] == probe['times']
    assert fit(law, [{'name': 'a', 'initial': 0}], [probe], moving_context())['converged']

    def forbidden(_t):
        raise AssertionError('Unused body input must not be consulted')

    assert rollout(law, {'a': 0}, probe, forbidden)['times'] == probe['times']


def test_internal_callable_provider_matches_observed_interpolation():
    probe = moving_acceleration_probe()
    called = []

    def supplied(t):
        called.append(t)
        return [[1 + 2*t, 4]]

    result = rollout(LAW, {'k': .4}, probe, supplied)
    np.testing.assert_allclose(result['r_pred'], probe['r_obs'], atol=1e-8)
    assert min(called) >= 3 and max(called) <= 5
    with pytest.raises(ExpressionError):
        Expression(LAW, [{'name': 'k', 'initial': .4}]).acceleration(3, [0, 0], [0, 0], supplied, {}, {'k': .4})


def test_export_uses_training_context_for_checks_and_caller_state_afterwards(tmp_path):
    law = {'law_id': 'law_1', 'law_spec': LAW, 'fitted_parameters': {'k': .4},
           'parameter_spec': [{'name': 'k', 'initial': .2}], 'known_bodies': [],
           'body_context': moving_context(), 'body_input_protocol': 'instantaneous_visible_state'}
    folder = tmp_path/'submission'
    checks = export_submission(folder, law, {'dynamics_order': 2, 'hidden_matter': False,
                                             'time_dependence': False},
                               [moving_acceleration_probe()], '随瞬时可见位置改变的候选。')
    assert checks['body_input_protocol'] == 'instantaneous_visible_state'
    spec = importlib.util.spec_from_file_location('temporal_export', folder/'law.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # The standalone law accepts a new visible state at a time outside the
    # training observations: the supplied state is input, not a fitted ephemeris.
    result = module.acceleration(100, {'r': [0, 0], 'v': [0, 0], 'visible': [[29, 4]], 'properties': {}})
    np.testing.assert_allclose(result, [11.6, 0])
    assert module.PARAMS == {'k': .4}


def write_evaluation_archive(root, version, world='world_6'):
    (root/'records/submission').mkdir(parents=True)
    (root/'records/law').mkdir()
    (root/'config.json').write_text(json.dumps({'environment': {'world_id': world, 'physics_version': version,
                                                             'time_max': 6, 'position_limit': 3, 'velocity_limit': 2}}))
    (root/'mission.json').write_text(json.dumps({'task': {'world_id': world, 'physics_version': version}}))
    (root/'records/submission/submission_1.json').write_text(json.dumps({
        'submission_id': 'submission_1', 'law_id': 'law_1', 'status': 'accepted', 'session_ended': True,
        'claims': {'dynamics_order': 2, 'hidden_matter': False, 'time_dependence': False}}))
    (root/'records/law/law_1.json').write_text(json.dumps({
        'law_id': 'law_1', 'law_spec': {'ax': 'sum_b(k*(bx-x))', 'ay': 'sum_b(k*(by-y))'},
        'fitted_parameters': {'k': .1}, 'known_bodies': [{'position': [99, 99]}],
        'body_input_protocol': 'instantaneous_visible_state',
        'body_context': {'kind': 'observed_body_trajectories', 'times': [0], 'body_ids': ['old'],
                         'positions': [[[99, 99]]]}}))


def test_v4_post_session_evaluation_supplies_current_visible_state(tmp_path):
    from evaluate import evaluate_run
    write_evaluation_archive(tmp_path, 'v4')
    before = {p: p.read_bytes() for p in tmp_path.rglob('*.json')}
    result = evaluate_run(tmp_path, n_probes=2)
    assert result['complete'] and result['overall']['position_rmse'] < 1e-6
    assert result['body_input_protocol'] == 'instantaneous_visible_state'
    assert before == {p: p.read_bytes() for p in tmp_path.rglob('*.json')}


def test_legacy_evaluation_keeps_frozen_positions(tmp_path):
    from evaluate import evaluate_run
    write_evaluation_archive(tmp_path, 'v3', 'world_1')
    result = evaluate_run(tmp_path, n_probes=2)
    assert result['complete'] and result['overall']['position_rmse'] > 1
    assert result['body_input_protocol'] == 'frozen_static_observed_positions'


def test_new_world_cannot_be_evaluated_as_historical_physics(tmp_path):
    from evaluate import _evaluation_environment
    write_evaluation_archive(tmp_path, 'v3')
    with pytest.raises(ValueError, match='world_physics_version_mismatch'):
        _evaluation_environment(tmp_path)
