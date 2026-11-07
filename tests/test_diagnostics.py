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


def test_summary_keeps_all_degree_cv_comparisons_and_independent_axis_coefficients():
    from shore_agent.diagnostics import summarize
    full = diagnose(trajectories(lambda r: np.array([-.2*r[0]+.03*r[1]**3, -.4*r[1]])), TASK)
    before = copy.deepcopy(full)
    summary = summarize(full)
    assert full == before
    rows = summary['spatial_model_comparison']
    assert [row['degree'] for row in rows] == [1, 2, 3]
    for source, row in zip(full['space_regression']['models'], rows):
        assert row['basis_term_count'] == len(source['basis'])
        assert row['rank'] == source['design']['rank']
        assert row['whole_probe_cv_status'] == source['cross_validation']['status']
        expected = (source['cross_validation'].get('errors') or {}).get('relative_rmse')
        assert row['whole_probe_cv_relative_delta_velocity_rmse'] == pytest.approx(expected, rel=1e-5)
        assert len(row['largest_terms']) <= 6
        assert all(set(item) == {'term', 'ax', 'ay'} for item in row['largest_terms'])
    assert rows[2]['linear_cv_divided_by_this_cv'] > 10
    assert 'law_id' not in summary
    json.dumps(summary, allow_nan=False)


def test_summary_does_not_present_geometric_screen_as_power_law_fit_quality():
    from shore_agent.diagnostics import summarize
    full = diagnose(radial_probes(), TASK)
    full['radial_diagnostic']['log_magnitude_rmse'] = .2144
    summary = summarize(full)['radial_power_summary']
    assert summary['geometry_and_design_screen_satisfied'] is True
    assert 'NOT a goodness-of-fit check' in summary['screen_scope']
    assert summary['log_magnitude_rmse'] == .2144
    assert summary['exp_log_rmse_multiplicative_factor'] == pytest.approx(math.exp(.2144), rel=1e-5)
    assert summary['acceleration_magnitude_radius_power'] == pytest.approx(2)
    assert summary['vector_factor_power'] == pytest.approx(1)
    assert 'accepted' not in summary and 'passed' not in summary


def test_summary_preserves_unavailable_cv_and_radial_diagnostics_without_invented_values():
    from shore_agent.diagnostics import summarize
    data = observed('one', [0., .1], [[1., 0.], [1., 0.]], [[0., 0.], [0., 0.]])
    full = diagnose([data], TASK)
    summary = summarize(full)
    for row in summary['spatial_model_comparison']:
        assert row['whole_probe_cv_status'] == 'unavailable'
        assert row['whole_probe_cv_relative_delta_velocity_rmse'] is None
        assert row['linear_cv_divided_by_this_cv'] is None
        assert row['largest_terms'] == []
    radial = summary['radial_power_summary']
    assert radial['empirical_fit_status'] == 'unavailable'
    assert radial['log_magnitude_rmse'] is None
    assert radial['exp_log_rmse_multiplicative_factor'] is None
    assert radial['vector_factor_power'] is None
    json.dumps(summary, allow_nan=False)


def curved_radial_probes(curvature=-.17, *, confounded=False, perturb=False):
    probes = []
    for radius in np.geomspace(.5, 5., 6):
        for mass, charge in ((.7, .8), (.7, 1.7), (1.3, .8), (1.3, 1.7)):
            if confounded:
                mass, charge = math.exp(math.log(radius)**2), 1.
            z = math.log(radius)
            log_magnitude = -.6-.4*z+curvature*z*z-.7*math.log(mass)+1.3*math.log(charge)
            if perturb:
                log_magnitude += .003*math.sin(3*z)
            magnitude = math.exp(log_magnitude)
            t = np.array([0., .1, .25])
            probes.append(observed(f'p{len(probes):03}', t, np.array([[radius, 0.]]*3),
                np.column_stack([-magnitude*t, np.zeros(3)]), {'mass': mass, 'charge': charge}))
    return probes


def test_radial_curvature_comparison_recovers_local_power_range_with_whole_probe_cv():
    from shore_agent.diagnostics import diagnose_radial_curvature
    probes = curved_radial_probes()
    before = copy.deepcopy(probes)
    result = diagnose_radial_curvature(probes, TASK)
    assert result['status'] == 'descriptive_comparison'
    linear, quadratic = result['models']
    assert [m['log_radius_degree'] for m in result['models']] == [1, 2]
    assert quadratic['quadratic_log_radius_coefficient'] == pytest.approx(-.17, abs=1e-12)
    expected = sorted([-.4-2*.17*math.log(r) for r in (.5, 5.)])
    np.testing.assert_allclose(quadratic['local_acceleration_magnitude_power_range'], expected, atol=1e-12)
    np.testing.assert_allclose(quadratic['local_vector_factor_power_range'], np.array(expected)-1, atol=1e-12)
    assert linear['cross_validation']['log_magnitude_rmse'] > .05
    assert quadratic['cross_validation']['log_magnitude_rmse'] < 1e-12
    assert result['quadratic_cv_reduction_fraction'] == pytest.approx(1.)
    assert result['cv_ratio_linear_over_quadratic'] is None
    assert result['cv_ratio_reason'] == 'quadratic_cv_residual_at_numerical_precision'
    for model in result['models']:
        ids = [pid for fold in model['cross_validation']['folds'] for pid in fold['held_out_probe_ids']]
        assert sorted(ids) == sorted(p['probe_id'] for p in probes)
        assert len(set(ids)) == len(ids)
    assert probes == before
    json.dumps(result, allow_nan=False)


def test_curvature_cv_ratio_reports_improvement_without_choosing_a_force_law():
    from shore_agent.diagnostics import diagnose_radial_curvature
    result = diagnose_radial_curvature(curved_radial_probes(perturb=True), TASK)
    assert result['cv_ratio_linear_over_quadratic'] > 10
    assert 0 < result['quadratic_cv_reduction_fraction'] < 1
    assert 'law_id' not in result and 'chosen_model' not in result and 'passed' not in result


def test_exact_power_law_does_not_claim_curvature_from_roundoff_cv_ratios():
    from shore_agent.diagnostics import diagnose_radial_curvature
    result = diagnose_radial_curvature(curved_radial_probes(curvature=0.), TASK)
    assert abs(result['models'][1]['quadratic_log_radius_coefficient']) < 1e-12
    assert result['cv_ratio_linear_over_quadratic'] is None
    assert result['quadratic_cv_reduction_fraction'] is None


def test_curvature_confounded_with_property_is_not_reported_as_unique():
    from shore_agent.diagnostics import diagnose_radial_curvature
    result = diagnose_radial_curvature(curved_radial_probes(confounded=True), TASK)
    assert result['status'] == 'descriptive_comparison'
    quadratic = result['models'][1]
    assert quadratic['design']['full_column_rank'] is False
    assert quadratic['diagnostic_coefficients'] is None
    assert 'mass' in quadratic['unidentified_property_controls']
    assert quadratic['local_acceleration_magnitude_power_range'] is None
    assert quadratic['cross_validation']['status'] == 'unavailable'
    assert result['cv_ratio_linear_over_quadratic'] is None
    assert 'charge' in result['unidentified_property_controls']


@pytest.mark.parametrize('mode', ['noise', 'missing_noise', 'transverse', 'narrow_span'])
def test_curvature_respects_observation_and_radial_coverage_limits(mode):
    from shore_agent.diagnostics import diagnose_radial_curvature
    probes, task = curved_radial_probes(), copy.deepcopy(TASK)
    if mode == 'noise':
        task['position_noise_sigma'] = .01
    elif mode == 'missing_noise':
        task.pop('position_noise_sigma')
    elif mode == 'transverse':
        for p in probes:
            p['v_obs'] = [[v[0], v[0]] for v in p['v_obs']]
    else:
        for p in probes:
            p['r_obs'] = [[1+.0001*r[0], r[1]] for r in p['r_obs']]
    result = diagnose_radial_curvature(probes, task)
    assert result['status'] == 'unavailable' and result['models'] == []
    assert result['cv_ratio_linear_over_quadratic'] is None
    json.dumps(result, allow_nan=False)


def test_curvature_is_opt_in_and_summary_preserves_full_evidence():
    from shore_agent.diagnostics import diagnose_radial_curvature, summarize
    probes = curved_radial_probes()
    full = diagnose(probes, TASK)
    assert 'radial_curvature' not in full and 'radial_curvature_summary' not in summarize(full)
    full['radial_curvature'] = diagnose_radial_curvature(probes, TASK)
    before = copy.deepcopy(full)
    small = summarize(full)
    assert full == before
    assert small['radial_curvature_summary']['status'] == 'descriptive_comparison'
    assert len(small['radial_curvature_summary']['models']) == 2
    json.dumps(small, allow_nan=False)


def polynomial_probes(beta, degree, times, seed=802, force_extra=None):
    """Independent high-accuracy synthetic trajectories with generic polynomial axes."""
    powers = [(i, power-i) for power in range(degree+1) for i in range(power, -1, -1)]
    rng = np.random.default_rng(seed)
    probes = []
    for i in range(8):
        initial = np.r_[rng.uniform(-1.5, 1.5, 2), rng.uniform(-.4, .4, 2)]
        def rhs(time, z):
            acceleration = np.array([z[0]**a*z[1]**b for a, b in powers]) @ beta
            if force_extra is not None:
                acceleration = acceleration + force_extra(time, z)
            return np.r_[z[2:], acceleration]
        solution = solve_ivp(rhs, (0., times[-1]), initial, t_eval=times,
                             rtol=2e-12, atol=2e-13, max_step=.02)
        assert solution.success
        probes.append(observed(f'p{i}', times, solution.y[:2].T, solution.y[2:].T))
    return probes


@pytest.mark.parametrize('degree', [1, 2, 3])
def test_hermite_simpson_recovers_fourth_order_coefficient_convergence(degree):
    powers = [(i, power-i) for power in range(degree+1) for i in range(power, -1, -1)]
    rng = np.random.default_rng(800+degree)
    beta = rng.uniform(-.06, .06, (len(powers), 2))
    beta[powers.index((1, 0)), 0] = -.6
    beta[powers.index((0, 1)), 1] = -.9
    errors = {method: [] for method in ('trapezoid', 'hermite_simpson')}
    for n_intervals in (4, 8):
        probes = polynomial_probes(beta, degree, np.linspace(0, 1.6, n_intervals+1))
        for method in errors:
            model = diagnose(probes, TASK, quadrature=method)['space_regression']['models'][degree-1]
            fitted = np.array([[term['ax'], term['ay']] for term in model['diagnostic_coefficients']])
            errors[method].append(np.linalg.norm(fitted-beta)/np.linalg.norm(beta))
    assert 3 < errors['trapezoid'][0]/errors['trapezoid'][1] < 5
    assert 12 < errors['hermite_simpson'][0]/errors['hermite_simpson'][1] < 20
    assert errors['hermite_simpson'][0] < .01*errors['trapezoid'][0]


def test_hermite_simpson_independent_axes_nonuniform_grid_and_whole_probe_cv():
    beta = np.array([[.07, -.03], [-.6, .17], [.21, -.9]])
    times = np.array([0., .03, .11, .2, .23, .31, .4, .5, .58, .63, .71, .8])
    probes = polynomial_probes(beta, 1, times)
    before = copy.deepcopy(probes)
    result = diagnose(probes, TASK, quadrature='hermite_simpson')
    model = result['space_regression']['models'][0]
    fitted = np.array([[term['ax'], term['ay']] for term in model['diagnostic_coefficients']])
    np.testing.assert_allclose(fitted, beta, rtol=5e-7, atol=2e-8)
    assert model['cross_validation']['status'] == 'available'
    assert model['cross_validation']['split_unit'] == 'whole_probe_trajectory'
    held_out = [pid for fold in model['cross_validation']['folds'] for pid in fold['held_out_probe_ids']]
    assert sorted(held_out) == [probe['probe_id'] for probe in probes]
    assert len(held_out) == len(set(held_out))
    assert probes == before
    assert 'law_id' not in result and 'passed' not in result
    json.dumps(result, allow_nan=False)


def test_hermite_simpson_near_zero_cv_does_not_resolve_severe_sampling_aliasing():
    frequency = 8.
    times = np.arange(5)*.8  # Nearly one entire oscillation between observations.
    rng = np.random.default_rng(19)
    probes = []
    for i in range(7):
        r0, v0 = rng.uniform(-1, 1, (2, 2))
        r = np.cos(frequency*times)[:, None]*r0 + np.sin(frequency*times)[:, None]*v0/frequency
        v = -frequency*np.sin(frequency*times)[:, None]*r0 + np.cos(frequency*times)[:, None]*v0
        probes.append(observed(f'p{i}', times, r, v))
    full = diagnose(probes, TASK, quadrature='hermite_simpson')
    model = full['space_regression']['models'][0]
    assert model['cross_validation']['errors']['relative_rmse'] < 1e-10
    # A perfect reconstruction CV still yields a very wrong force coefficient.
    fitted = coefficients(model)['x'][0]
    assert abs(fitted+frequency**2)/frequency**2 > .9
    assert any('aliasing or wrong coefficients' in note for note in full['space_regression']['limitations'])
    from shore_agent.diagnostics import summarize
    assert any('wrong coefficients' in note for note in summarize(full)['comparison_notes'])


def test_hermite_simpson_does_not_repair_an_omitted_velocity_dependency():
    beta = np.array([[0., 0.], [-.6, 0.], [0., -.9]])
    probes = polynomial_probes(beta, 1, np.linspace(0, 1.6, 17), force_extra=lambda t, z: -.5*z[2:])
    result = diagnose(probes, TASK, quadrature='hermite_simpson')
    assert result['space_regression']['models'][0]['cross_validation']['errors']['relative_rmse'] > .1


@pytest.mark.parametrize('field', ['position_noise_sigma', 'velocity_noise_sigma'])
@pytest.mark.parametrize('value', [None, .001, -1., True])
def test_hermite_simpson_requires_explicitly_noise_free_position_and_velocity(field, value):
    task = copy.deepcopy(TASK)
    if value is None:
        task.pop(field)
    else:
        task[field] = value
    with pytest.raises(ValueError, match='both position_noise_sigma and velocity_noise_sigma explicitly equal to zero'):
        diagnose(radial_probes(), task, quadrature='hermite_simpson')
    # The pre-existing diagnostic is still usable under its original noise rules.
    diagnose(radial_probes(), task)


def test_default_quadrature_contract_and_opt_in_method_metadata_are_preserved():
    from shore_agent.diagnostics import summarize
    probes = trajectories(lambda r: -.6*r)
    default = diagnose(probes, TASK)
    explicit = diagnose(probes, TASK, quadrature='trapezoid')
    assert default == explicit
    assert 'quadrature' not in default['space_regression']
    assert default['space_regression']['method'] == 'Delta-v integral regression; trapezoidal integration on acquired nonuniform time grids'
    assert 'spatial_quadrature' not in summarize(default)
    opt_in = diagnose(probes, TASK, quadrature='hermite_simpson')
    assert opt_in['radial_diagnostic'] == default['radial_diagnostic']
    metadata = opt_in['space_regression']['quadrature']
    assert metadata['name'] == 'hermite_simpson'
    assert 'explicitly equal zero' in metadata['assumptions']
    assert 'held-out endpoint velocities' in metadata['cv_scope']
    small = summarize(opt_in)
    assert small['spatial_quadrature'] == metadata
    assert 'not independent prediction validation' in small['comparison_notes'][0]
    with pytest.raises(ValueError, match='quadrature must be'):
        diagnose(probes, TASK, quadrature='unknown')
