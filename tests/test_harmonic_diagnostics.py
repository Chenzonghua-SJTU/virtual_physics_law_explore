"""Synthetic harmonic identification, alias and resource-limit contracts."""
import copy
import json
import math

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from shore_agent.diagnostics import _prepare
from shore_agent.harmonic_diagnostics import BASIS, _design, diagnose_harmonic, summarize_harmonic


TASK = {'allowed_properties': ['mass'], 'property_controls': {'mass': {'default': 1.}},
        'position_noise_sigma': 0., 'velocity_noise_sigma': 0.}


def synthetic(seed=57, harmonic=True, coarse_last=False):
    rng = np.random.default_rng(seed)
    omega = float(rng.uniform(.4, 1.))
    matrices = [-.18*np.eye(2)+rng.uniform(-.025, .025, (2, 2)),
                rng.uniform(-.035, .035, (2, 2)), rng.uniform(-.035, .035, (2, 2))]
    offset = rng.uniform(-.01, .01, 2)
    if not harmonic:
        matrices[1:] = [np.zeros((2, 2)), np.zeros((2, 2))]
    probes = []
    for i in range(8):
        initial = np.r_[rng.uniform(-2, 2, 2), rng.uniform(-.3, .3, 2)]
        start = i % 3 * .7
        times = np.linspace(start, start+4., 21 if coarse_last and i == 7 else 41)
        def rhs(t, z):
            matrix = matrices[0]+matrices[1]*np.sin(omega*t)+matrices[2]*np.cos(omega*t)
            return np.r_[z[2:], matrix@z[:2]+offset]
        solution = solve_ivp(rhs, (times[0], times[-1]), initial, t_eval=times,
                             rtol=2e-12, atol=2e-13, max_step=.02)
        assert solution.success
        probes.append({'probe_id': f'p{i}', 'times': times.tolist(),
                       'r_obs': solution.y[:2].T.tolist(), 'v_obs': solution.y[2:].T.tolist(),
                       'initial_conditions': {'properties': {'mass': 1.}}})
    beta = np.vstack([offset, matrices[0].T, np.zeros(2), matrices[1].T, np.zeros(2), matrices[2].T])
    return probes, omega, beta


@pytest.fixture(scope='module')
def recovered():
    probes, omega, beta = synthetic(coarse_last=True)
    before = copy.deepcopy(probes)
    result = diagnose_harmonic(probes, TASK)
    assert probes == before
    return probes, omega, beta, result


def test_recovers_random_frequency_and_independent_axis_coefficients(recovered):
    probes, omega, beta, result = recovered
    assert result['status'] == 'descriptive_comparison'
    model = result['harmonic_model']
    assert model['basis'] == BASIS
    assert model['omega'] == pytest.approx(omega, rel=3e-6, abs=2e-7)
    fitted = np.array([[term['ax'], term['ay']] for term in model['diagnostic_coefficients']])
    np.testing.assert_allclose(fitted, beta, rtol=2e-5, atol=1e-7)
    assert model['design']['rank'] == 9
    assert model['frequency_identification']['status'] == 'locally_resolved_within_searched_family'
    assert model['cross_validation']['errors']['relative_rmse'] < 3e-6
    assert result['linear_cv_divided_by_harmonic_cv'] > 1000
    json.dumps(result, allow_nan=False)
    assert 'law_id' not in result and 'passed' not in result and 'selected_law' not in result


def test_cv_refits_frequency_and_search_range_from_each_training_fold(recovered):
    probes, omega, _, result = recovered
    cv = result['harmonic_model']['cross_validation']
    assert cv['split_unit'] == 'whole_probe_trajectory'
    held_ids = [pid for fold in cv['folds'] for pid in fold['held_out_probe_ids']]
    assert sorted(held_ids) == [probe['probe_id'] for probe in probes]
    assert len(held_ids) == len(set(held_ids))
    upper_bounds = []
    for fold in cv['folds']:
        training = [p for p in probes if p['probe_id'] not in fold['held_out_probe_ids']]
        expected_upper = math.pi/max(float(np.max(np.diff(p['times']))) for p in training)
        upper_bounds.append(fold['frequency_search']['frequency_upper'])
        assert fold['frequency_search']['frequency_upper'] == expected_upper
        assert fold['selected_omega'] == pytest.approx(omega, rel=1e-5)
        assert fold['training_rank'] == 9
    assert max(upper_bounds) > 1.9*min(upper_bounds)
    assert cv['frequency_identification_in_all_folds']


def test_profile_ranges_and_property_limits_are_disclosed(recovered):
    result = recovered[-1]
    identification = result['harmonic_model']['frequency_identification']
    interval = identification['local_profile_interval']
    assert interval[0] <= result['harmonic_model']['omega'] <= interval[1]
    assert interval[1] > interval[0]
    assert 'not a confidence interval' in identification['profile_tolerance_rule']
    assert 'narrow aliases' in identification['scope']
    assert result['unvaried_controls'] == ['mass']
    assert any('not proven absent' in text for text in result['limitations'])
    assert any('Eighteen independent' in text for text in result['limitations'])
    assert any('not independent rollout validation' in text for text in result['limitations'])


def test_autonomous_counterexample_does_not_identify_an_arbitrary_frequency():
    probes, _, _ = synthetic(harmonic=False)
    result = diagnose_harmonic(probes, TASK)
    assert result['status'] == 'descriptive_comparison'
    assert result['harmonic_model']['frequency_identification']['status'] == 'unresolved'
    reasons = result['harmonic_model']['frequency_identification']['reasons']
    assert 'frequency_effect_too_small_after_refitting_linear_coefficients' in reasons
    assert 'broad_local_frequency_profile' in reasons
    assert result['linear_cv_divided_by_harmonic_cv'] is None


def test_uniform_grid_alias_remains_indistinguishable_to_endpoint_midpoint_quadrature():
    # A high frequency outside the searched sampling band can yield exactly the
    # same dictionary. This is why local frequency identification is not global.
    probes, _, _ = synthetic()
    rows, _ = _prepare(probes[:1], TASK)
    row = rows[0]
    step = row['t'][1]-row['t'][0]
    first, _ = _design(rows, .73)
    alias, _ = _design(rows, .73+4*math.pi/step)
    np.testing.assert_allclose(first[0], alias[0], rtol=1e-10, atol=2e-13)


def test_rank_deficiency_never_returns_unique_frequency_coefficients():
    probe = {'probe_id': 'p', 'times': [0., .1], 'r_obs': [[1., 0.], [.99, 0.]],
             'v_obs': [[0., 0.], [-.1, 0.]], 'initial_conditions': {'properties': {'mass': 1.}}}
    result = diagnose_harmonic([probe], TASK)
    assert result['status'] == 'unavailable'
    assert result['harmonic_model'] is None
    assert result['reason'] == 'no_full_rank_stable_frequency_design'
    assert result['autonomous_linear_reference']['diagnostic_coefficients'] is None


def test_time_budget_exhaustion_cannot_publish_partial_cv(recovered):
    result = diagnose_harmonic(recovered[0], TASK, max_seconds=1e-12)
    assert result['status'] == 'budget_exhausted'
    assert result['linear_cv_divided_by_harmonic_cv'] is None
    assert result['harmonic_model'] is None or result['harmonic_model']['cross_validation']['status'] == 'unavailable'
    assert result['computation']['wall_budget_seconds'] == 1e-12
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('key', ['position_noise_sigma', 'velocity_noise_sigma'])
@pytest.mark.parametrize('value', [None, .001, True])
def test_noise_and_unknown_metadata_are_rejected(key, value):
    task = copy.deepcopy(TASK)
    if value is None: task.pop(key)
    else: task[key] = value
    with pytest.raises(ValueError, match='explicitly equal to zero'):
        diagnose_harmonic([], task)


@pytest.mark.parametrize('budget', [0, -1., 11., True, float('inf')])
def test_invalid_resource_budgets_are_rejected(budget):
    with pytest.raises(ValueError, match='max_seconds'):
        diagnose_harmonic([], TASK, max_seconds=budget)


def test_task_world_labels_have_no_effect_on_calculation(recovered):
    probes = recovered[0]
    task = dict(TASK, world_id='unused_random_label', hidden_formula='must never be read')
    repeated = diagnose_harmonic(probes, task)
    assert repeated['status'] == 'descriptive_comparison'
    expected = copy.deepcopy(recovered[-1])
    repeated.pop('computation'); expected.pop('computation')
    assert repeated == expected


def test_summary_preserves_all_nine_pairs_without_frequency_scan(recovered):
    full = recovered[-1]
    before = copy.deepcopy(full)
    small = summarize_harmonic(full)
    terms = small['harmonic_model']['coefficients_by_term']
    assert list(terms) == BASIS and len(terms) == 9
    assert all(set(item) == {'ax', 'ay', 'delta_velocity_contribution_rms'} for item in terms.values())
    assert 'profile' not in small['harmonic_model']['frequency_search']
    assert 'profile' in full['harmonic_model']['frequency_search']
    assert len(small['harmonic_model']['cross_validation']['folds']) == 5
    assert small['harmonic_model']['frequency_identification']['global_frequency_uniqueness_established'] is False
    assert full == before
    assert len(json.dumps(small)) < len(json.dumps(full))/2
    json.dumps(small, allow_nan=False)


@pytest.mark.parametrize('acceleration', [[0., 0.], [.2, -.13]])
def test_constant_acceleration_and_zero_increments_are_finite(acceleration):
    rng = np.random.default_rng(46)
    a = np.array(acceleration)
    times = np.linspace(0, 2, 21)
    probes = []
    for i in range(6):
        r0, v0 = rng.uniform(-1, 1, (2, 2))
        r = r0+times[:, None]*v0+.5*times[:, None]**2*a
        v = v0+times[:, None]*a
        probes.append({'probe_id': f'p{i}', 'times': times.tolist(), 'r_obs': r.tolist(),
                       'v_obs': v.tolist(), 'initial_conditions': {'properties': {'mass': 1.}}})
    result = diagnose_harmonic(probes, TASK)
    json.dumps(result, allow_nan=False)
    json.dumps(summarize_harmonic(result), allow_nan=False)
    assert result['linear_cv_divided_by_harmonic_cv'] is None
    if not np.any(a):
        assert result['status'] == 'unavailable'
        assert result['reason'] == 'zero_observed_velocity_increment'
    else:
        assert result['status'] == 'descriptive_comparison'
        assert result['harmonic_model']['frequency_identification']['status'] == 'unresolved'
        cv = result['harmonic_model']['cross_validation']
        assert cv['status'] == 'available' and cv['frequency_identification_in_all_folds'] is False


def test_budget_expiry_after_model_fit_withholds_partial_cv(monkeypatch, recovered):
    import shore_agent.harmonic_diagnostics as module
    original = module._cross_validate
    def expire_at_harmonic_cv(rows, deadline, harmonic):
        if harmonic:
            raise module._TimeLimit
        return original(rows, deadline, harmonic)
    monkeypatch.setattr(module, '_cross_validate', expire_at_harmonic_cv)
    result = module.diagnose_harmonic(recovered[0], TASK)
    assert result['status'] == 'budget_exhausted' and result['harmonic_model'] is not None
    assert result['harmonic_model']['cross_validation']['errors'] is None
    assert result['harmonic_model']['cross_validation']['status'] == 'unavailable'
    assert result['linear_cv_divided_by_harmonic_cv'] is None
    assert summarize_harmonic(result)['status'] == 'budget_exhausted'


def test_search_grid_cap_is_not_reported_as_frequency_identification(monkeypatch, recovered):
    import shore_agent.harmonic_diagnostics as module
    monkeypatch.setattr(module, 'MAX_GRID_POINTS', 16)
    result = module.diagnose_harmonic(recovered[0], TASK)
    assert result['status'] == 'descriptive_comparison'
    identification = result['harmonic_model']['frequency_identification']
    assert identification['status'] == 'unresolved'
    assert 'frequency_grid_capped_search_may_miss_narrow_minima' in identification['reasons']


def test_unrepresentable_frequency_scale_is_rejected():
    probe = {'probe_id': 'p', 'times': [0., 1e-30], 'r_obs': [[1., 0.], [.99, 0.]],
             'v_obs': [[0., 0.], [-.1, 0.]], 'initial_conditions': {'properties': {'mass': 1.}}}
    with pytest.raises(ValueError, match='time scale exceeds'):
        diagnose_harmonic([probe], TASK)
