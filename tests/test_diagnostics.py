"""Mathematical contracts on synthetic observations, independent of any universe."""
import copy
import json
import math

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from shore_agent.diagnostics import diagnose


TASK = {'allowed_properties': ['mass', 'charge'],
        'property_controls': {'mass': {'default': 1.}, 'charge': {'default': 1.}},
        'velocity_noise_sigma': 0., 'position_noise_sigma': 0.}


def observed(pid, t, r, v, properties=None):
    return {'probe_id': pid, 'times': np.asarray(t).tolist(),
            'r_obs': np.asarray(r).tolist(), 'v_obs': np.asarray(v).tolist(),
            'initial_conditions': {'r0': list(r[0]), 'v0': list(v[0]), 't0': float(t[0]),
                                   'properties': properties or {}}}


def trajectories(acceleration, count=8):
    rng = np.random.default_rng(141)
    t = np.linspace(0, .49, 50)
    result = []
    for i in range(count):
        initial = np.r_[rng.uniform(-2, 2, 2), rng.uniform(-.5, .5, 2)]
        def rhs(time, state):
            return np.r_[state[2:], acceleration(state[:2])]
        solution = solve_ivp(rhs, (0, t[-1]), initial, t_eval=t, rtol=2e-12, atol=1e-13)
        assert solution.success
        result.append(observed(f'p{i:03}', t, solution.y[:2].T, solution.y[2:].T))
    return result


def coefficients(model):
    return {c['term']: np.array([c['ax'], c['ay']]) for c in model['diagnostic_coefficients']}


def test_integral_regression_recovers_independent_axes_and_cross_terms():
    matrix = np.array([[-.6, .25], [.1, -.4]])
    probes = trajectories(lambda r: matrix @ r)
    before = copy.deepcopy(probes)
    result = diagnose(probes, TASK)
    model = result['space_regression']['models'][0]
    beta = coefficients(model)
    assert model['basis'] == ['1', 'x', 'y']
    np.testing.assert_allclose(beta['x'], matrix[:, 0], rtol=2e-5, atol=2e-7)
    np.testing.assert_allclose(beta['y'], matrix[:, 1], rtol=2e-5, atol=2e-7)
    np.testing.assert_allclose(beta['1'], 0, atol=2e-7)
    assert model['design']['full_column_rank'] and model['cross_validation']['status'] == 'available'
    assert model['cross_validation']['errors']['relative_rmse'] < 1e-6
    assert probes == before
    assert 'law_id' not in result
    json.dumps(result, allow_nan=False)


def test_complete_cubic_dictionary_detects_nonlinearity_without_an_axis_shared_template():
    def acceleration(r):
        x, y = r
        return np.array([.12+.2*x-.17*y+.03*x*x-.04*x*y+.02*y*y-.02*x**3+.015*x*x*y-.01*x*y*y+.005*y**3,
                         -.07-.13*x+.09*y-.01*x*x+.02*x*y-.03*y*y+.006*x**3-.011*x*x*y+.017*x*y*y-.023*y**3])
    models = diagnose(trajectories(acceleration), TASK)['space_regression']['models']
    linear, quadratic, cubic = models
    assert [len(m['basis']) for m in models] == [3, 6, 10]
    assert set(cubic['basis']) == {'1', 'x', 'y', 'x^2', 'x*y', 'y^2', 'x^3', 'x^2*y', 'x*y^2', 'y^3'}
    assert cubic['cross_validation']['status'] == 'available'
    assert cubic['cross_validation']['errors']['relative_rmse'] < .01 * linear['cross_validation']['errors']['relative_rmse']
    assert cubic['cross_validation']['errors']['relative_rmse'] < .05 * quadratic['cross_validation']['errors']['relative_rmse']
    np.testing.assert_allclose(coefficients(cubic)['x*y^2'], [-.01, .017], rtol=.005, atol=1e-5)
    np.testing.assert_allclose(coefficients(cubic)['y^3'], [.005, -.023], rtol=.005, atol=1e-5)


def radial_probes(power=2., *, paired_properties=False, direction=-1.):
    probes = []
    combinations = [(r, m, q) for r in (1., 2., 4.) for m in (.7, 1.3) for q in (.8, 1.7)]
    for i, (radius, mass, charge) in enumerate(combinations):
        if paired_properties:
            charge = mass
        magnitude = .12 * radius**power * mass**-.7 * charge**1.3
        r = np.array([[radius, 0.]] * 3)
        t = np.array([0., .1, .25])
        v = np.column_stack([direction * magnitude * t, np.zeros(3)])
        probes.append(observed(f'p{i:03}', t, r, v, {'mass': mass, 'charge': charge}))
    return probes


@pytest.mark.parametrize('power', [2., -1.5, 0.])
def test_radial_magnitude_exponent_and_vector_factor_power_are_distinguished(power):
    result = diagnose(radial_probes(power), TASK)['radial_diagnostic']
    assert result['status'] == 'empirical_fit'
    assert result['acceleration_magnitude_radius_power'] == pytest.approx(power, abs=1e-12)
    assert result['vector_factor_power'] == pytest.approx(power-1, abs=1e-12)
    assert result['positive_property_powers']['mass'] == pytest.approx(-.7, abs=1e-12)
    assert result['positive_property_powers']['charge'] == pytest.approx(1.3, abs=1e-12)
    assert result['radial_direction'] == 'inward'
    assert result['transverse_acceleration_rms_fraction'] < 1e-7
    assert result['reference_point'] == [0., 0.]
    assert 'not an inferred force center' in result['reference_point_meaning']


def test_collinear_property_changes_are_not_reported_as_identified_powers():
    result = diagnose(radial_probes(paired_properties=True), TASK)['radial_diagnostic']
    assert result['status'] == 'unavailable'
    assert not result['design']['full_column_rank']
    assert result['acceleration_magnitude_radius_power'] is None and result['vector_factor_power'] is None
    assert 'positive_property_powers' not in result


def test_constant_properties_are_explicitly_unidentified_not_assigned_zero_effect():
    probes = radial_probes()
    for p in probes:
        p['initial_conditions']['properties'] = {'mass': 1., 'charge': 1.}
    result = diagnose(probes, TASK)['radial_diagnostic']
    assert result['unvaried_controls'] == ['charge', 'mass']
    assert result['positive_property_powers'] == {}
    assert 'causal effects' in ' '.join(result['limitations'])


def test_noise_cutoff_and_transverse_motion_do_not_produce_a_radial_power_claim():
    noisy = dict(TASK, velocity_noise_sigma=100)
    result = diagnose(radial_probes(), noisy)['radial_diagnostic']
    assert result['status'] == 'unavailable' and result['vector_factor_power'] is None
    probes = radial_probes()
    for p in probes:
        p['v_obs'] = [[0., v[0]] for v in p['v_obs']]
    result = diagnose(probes, TASK)['radial_diagnostic']
    assert result['status'] == 'unavailable' and result['vector_factor_power'] is None
    assert result['transverse_acceleration_rms_fraction'] == pytest.approx(1.)


def test_rank_deficient_spatial_design_suppresses_nonunique_coefficients_and_cv():
    t = np.array([0., .1, .2, .3])
    probes = [observed(f'p{i}', t, np.column_stack([np.ones(4)*i, np.zeros(4)]), np.zeros((4, 2))) for i in (1, 2, 3)]
    result = diagnose(probes, TASK)
    for model in result['space_regression']['models']:
        assert not model['design']['full_column_rank']
        assert model['diagnostic_coefficients'] is None
        assert model['cross_validation']['status'] == 'unavailable'
    json.dumps(result, allow_nan=False)


def test_cross_validation_holds_out_whole_probes_once_and_single_probe_has_no_cv():
    probes = trajectories(lambda r: -.2*r)
    result = diagnose(probes, TASK)
    for model in result['space_regression']['models']:
        folds = model['cross_validation']['folds']
        assert len(folds) == 5
        held_out = [pid for fold in folds for pid in fold['held_out_probe_ids']]
        assert sorted(held_out) == sorted(p['probe_id'] for p in probes)
        assert len(set(held_out)) == len(held_out)
    single = diagnose(probes[:1], TASK)
    assert all(m['cross_validation']['status'] == 'unavailable' for m in single['space_regression']['models'])


def test_world_labels_do_not_affect_diagnostics_and_no_external_reads_are_used(monkeypatch):
    probes = radial_probes()
    def refuse(*args, **kwargs):
        pytest.fail('diagnostics must not read files or historical/evaluation data')
    monkeypatch.setattr('builtins.open', refuse)
    first = diagnose(probes, dict(TASK, world_id='arbitrary-label', hidden_truth='not a real input'))
    second = diagnose(list(reversed(probes)), dict(TASK, world_id='another-label', hidden_truth='changed'))
    assert first == second


@pytest.mark.parametrize('change', ['nan', 'unsorted', 'duplicate', 'too_many'])
def test_invalid_input_fails_before_diagnostic_inference(change):
    probes = radial_probes()
    if change == 'nan':
        probes[0]['r_obs'][0][0] = float('nan')
    elif change == 'unsorted':
        probes[0]['times'] = [0., .2, .1]
    elif change == 'duplicate':
        probes[1]['probe_id'] = probes[0]['probe_id']
    else:
        probes = probes * 10
    with pytest.raises(ValueError):
        diagnose(probes, TASK)


@pytest.mark.parametrize('mode,reason', [
    ('transverse', 'substantial_or_unavailable_transverse_acceleration'),
    ('mixed_sign', 'mixed_radial_sign'), ('narrow_radius', 'radius_span_below_1_2')])
def test_stable_log_fit_is_not_enough_for_radial_power_interpretation(mode, reason):
    probes = radial_probes()
    for i, p in enumerate(probes):
        if mode == 'transverse':
            p['v_obs'] = [[v[0], .8*v[0]] for v in p['v_obs']]
        elif mode == 'mixed_sign' and i % 2:
            p['v_obs'] = [[-v[0], v[1]] for v in p['v_obs']]
        elif mode == 'narrow_radius':
            p['r_obs'] = [[1.+.001*r[0], r[1]] for r in p['r_obs']]
    radial = diagnose(probes, TASK)['radial_diagnostic']
    assert radial['status'] == 'empirical_fit'
    assert radial['usable_for_power_interpretation'] is False
    assert reason in radial['power_interpretation_reasons']


def test_radial_interpretation_screen_remains_conditional_and_lists_unknown_property_effects():
    probes = radial_probes()
    for p in probes:
        p['initial_conditions']['properties'] = {'mass': 1., 'charge': 1.}
    radial = diagnose(probes, TASK)['radial_diagnostic']
    assert radial['usable_for_power_interpretation'] is True
    assert radial['unidentified_property_controls'] == ['charge', 'mass']
    assert radial['conditional_on_fixed_property_values'] == {'mass': [1.], 'charge': [1.]}
    assert radial['positive_property_powers'] == {}


def test_numerics_compatible_thousand_samples_and_six_top_terms():
    probes = trajectories(lambda r: -.2*r, count=2)
    original = probes[0]
    times = np.linspace(0, .49, 1000)
    original['r_obs'] = np.column_stack([np.interp(times, original['times'], np.asarray(original['r_obs'])[:, i]) for i in (0, 1)]).tolist()
    original['v_obs'] = np.column_stack([np.interp(times, original['times'], np.asarray(original['v_obs'])[:, i]) for i in (0, 1)]).tolist()
    original['times'] = times.tolist()
    result = diagnose(probes, TASK)
    assert len(result['space_regression']['models'][2]['largest_terms_by_increment_contribution']) <= 6
    assert result['probe_ids'] == ['p000', 'p001']
