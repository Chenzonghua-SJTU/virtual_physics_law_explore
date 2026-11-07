"""Synthetic observation-to-DSL contracts, without contest worlds or answers."""
import ast
import copy
import json
import math

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from shore_agent.candidate_hints import propose_observation_candidates
from shore_agent.diagnostics import diagnose
from shore_agent.expressions import Expression


TASK = {'allowed_properties': ['mass', 'charge'], 'position_noise_sigma': 0.,
        'velocity_noise_sigma': 0.,
        'property_controls': {'mass': {'default': 1.}, 'charge': {'default': 1.}}}
TERMS = ['1', 'x', 'y', 'x^2', 'x*y', 'y^2', 'x^3', 'x^2*y', 'x*y^2', 'y^3']


def model(values, degree=3, cv=.01):
    terms = TERMS[:{1: 3, 2: 6, 3: 10}[degree]]
    return {'degree': degree, 'basis': terms,
            'diagnostic_coefficients': [{'term': term, 'ax': values.get(('ax', term), 0.),
                'ay': values.get(('ay', term), 0.),
                'delta_velocity_contribution_rms': math.hypot(values.get(('ax', term), 0.), values.get(('ay', term), 0.))}
                for term in terms],
            'design': {'full_column_rank': True, 'coefficient_identifiability': 'full_rank_design'},
            'training_errors': {'relative_rmse': cv/2},
            'cross_validation': {'status': 'available', 'errors': {'relative_rmse': cv}}}


def radial(power=1.4, powers=None, fixed=None):
    powers = {'mass': -.4, 'charge': 1.3} if powers is None else powers
    fixed = {} if fixed is None else fixed
    return {'status': 'empirical_fit', 'reference_point': [0., 0.],
            'usable_for_power_interpretation': True,
            'design': {'full_column_rank': True, 'coefficient_identifiability': 'full_rank_design'},
            'radial_direction': 'inward', 'acceleration_magnitude_radius_power': power,
            'intercept_log_magnitude': math.log(.23), 'positive_property_powers': powers,
            'conditional_on_fixed_property_values': fixed,
            'unidentified_property_controls': list(fixed), 'log_magnitude_rmse': .02,
            'radius_range': [.7, 4.]}


def hints(*models, radial_result=None, task=TASK):
    diagnostics = {'space_regression': {'models': list(models)}}
    if radial_result is not None:
        diagnostics['radial_diagnostic'] = radial_result
    return propose_observation_candidates(diagnostics, task)


def evaluate(candidate, r, properties=None):
    expression = Expression(candidate['law_spec'], candidate['parameter_spec'], allowed_properties=TASK['allowed_properties'])
    return expression.acceleration(0., r, [0., 0.], [], properties or {'mass': 1., 'charge': 1.},
                                   {p['name']: p['initial'] for p in candidate['parameter_spec']})


def test_independent_axes_keep_distinct_coefficients_and_named_offset():
    source = model({('ax', '1'): .12, ('ax', 'x'): -.7, ('ax', 'y'): .24,
                    ('ay', 'x'): -.31, ('ay', 'y'): -.45}, degree=1)
    result = hints(source)
    candidate = result['candidates'][0]
    assert candidate['kind'] == 'independent_polynomial'
    assert len(candidate['parameter_spec']) == 5
    np.testing.assert_allclose(evaluate(candidate, [2., -.5]), [.12-.7*2-.24*.5, -.31*2+.45*.5])
    assert candidate['evidence']['source_errors_are_not_candidate_errors']
    assert 'BEFORE pruning' in candidate['warnings'][0]
    assert 'law_id' not in json.dumps(result)


def test_axis_contribution_pruning_does_not_keep_numerical_cross_axis_artifact():
    source = model({('ax', 'x'): 1., ('ay', 'x'): 1e-8, ('ay', 'y'): -.8}, degree=1)
    candidate = hints(source)['candidates'][0]
    assert len(candidate['parameter_spec']) == 2
    dropped = candidate['evidence']['pruned_axis_terms']
    assert any(t['component'] == 'ay' and t['term'] == 'x' for t in dropped)
    np.testing.assert_allclose(evaluate(candidate, [.2, .7]), [.2, -.56])


def test_small_training_contribution_can_matter_outside_observations_and_is_disclosed():
    candidate = hints(model({('ax', 'x'): 1., ('ax', 'x^3'): .0005}, cv=0.))['candidates'][0]
    assert len(candidate['parameter_spec']) == 1
    assert any(t['term'] == 'x^3' and t['diagnostic_coefficient'] == .0005
               for t in candidate['evidence']['pruned_axis_terms'])
    assert evaluate(candidate, [100., 0.])[0] == 100.
    assert 100.+.0005*100.**3 == 600.  # Its parent's zero CV is not this hint's error.
    assert candidate['evidence']['source_whole_probe_cv_relative_rmse'] == 0.
    assert candidate['evidence']['source_errors_are_not_candidate_errors']
    assert any('outside sampled trajectories' in warning for warning in candidate['warnings'])


def test_six_terms_form_explicit_same_degree_approximate_equality_hypothesis():
    values = {('ax', 'x'): -.6, ('ay', 'y'): -.9,
              ('ax', 'x^3'): -.12, ('ay', 'y^3'): -.123,
              ('ax', 'x*y^2'): -.22, ('ay', 'x^2*y'): -.4}
    candidate = hints(model(values))['candidates'][0]
    assert candidate['kind'] == 'approximate_shared_polynomial'
    assert len(candidate['parameter_spec']) == 5
    groups = candidate['evidence']['coefficient_groups']
    shared = [g for g in groups if len(g['members']) > 1]
    assert len(shared) == 1 and len(shared[0]['members']) == 2
    assert shared[0]['max_relative_deviation_from_initial'] > 0
    for r in ([.3, -.8], [-.7, .6]):
        x, y = r
        np.testing.assert_allclose(evaluate(candidate, r),
            [-.6*x-.1215*x**3-.22*x*y*y, -.9*y-.1215*y**3-.4*x*x*y])
    assert any('not evidence of symmetry' in warning for warning in candidate['warnings'])


def test_independent_coefficients_are_not_shared_when_already_within_five():
    candidate = hints(model({('ax', 'x'): .6, ('ay', 'y'): .61}, degree=1))['candidates'][0]
    assert candidate['kind'] == 'independent_polynomial'
    assert len(candidate['parameter_spec']) == 2


@pytest.mark.parametrize('values', [
    {('ax', 'x'): .1, ('ay', 'y'): .2, ('ax', 'x^3'): .3, ('ay', 'y^3'): .4,
     ('ax', 'x*y^2'): .5, ('ay', 'x^2*y'): .6},
    # Similar values across different degrees cannot justify equality of units.
    {('ax', '1'): .2, ('ay', '1'): -.2, ('ax', 'x'): .2,
     ('ay', 'y'): -.2, ('ax', 'x^2'): .2, ('ay', 'y^2'): -.2},
])
def test_more_than_five_incompatible_strong_coefficients_yield_no_candidate(values):
    result = hints(model(values))
    assert result['candidates'] == []
    assert any('more_than_five_distinct' in entry['reason'] for entry in result['skipped_families'])


def test_complete_link_grouping_does_not_chain_together_distant_values():
    values = {('ax', 'x'): 1., ('ay', 'x'): 1.04, ('ax', 'y'): 1.08,
              ('ax', 'x^3'): .21, ('ay', 'y^3'): .32, ('ax', 'x*y^2'): .43}
    candidate = hints(model(values))['candidates'][0]
    assert len(candidate['parameter_spec']) == 5
    for group in candidate['evidence']['coefficient_groups']:
        coefficients = [t['diagnostic_coefficient'] for t in group['members']]
        assert max(coefficients)-min(coefficients) <= .05*max(abs(c) for c in coefficients)+1e-15


@pytest.mark.parametrize('change', ['rank', 'cv', 'cv_none', 'cv_errors_none', 'nan', 'missing_term', 'illegal_term'])
def test_inadequate_or_invalid_diagnostic_evidence_is_not_translated(change):
    source = model({('ax', 'x'): -.7, ('ay', 'y'): -.8}, degree=1)
    if change == 'rank':
        source['design']['coefficient_identifiability'] = 'not_unique_or_unstable'
    elif change == 'cv':
        source['cross_validation']['status'] = 'unavailable'
    elif change == 'cv_none':
        source['cross_validation'] = None
    elif change == 'cv_errors_none':
        source['cross_validation'] = {'status': 'unavailable', 'errors': None}
    elif change == 'nan':
        source['diagnostic_coefficients'][0]['ax'] = float('nan')
    elif change == 'missing_term':
        source['diagnostic_coefficients'].pop()
    else:
        source['diagnostic_coefficients'][0]['term'] = '__import__("os")'
    assert hints(source)['candidates'] == []


def test_radial_power_conversion_and_public_property_exponents():
    candidate = hints(radial_result=radial())['candidates'][0]
    assert candidate['kind'] == 'empirical_radial_power'
    assert len(candidate['parameter_spec']) == 4
    evidence = candidate['evidence']
    assert evidence['vector_factor_power'] == pytest.approx(.4)
    assert evidence['squared_radius_factor_power'] == pytest.approx(.2)
    for r in ([1., 0.], [2., -3.], [.4, .7]):
        properties = {'mass': .8, 'charge': 1.7}
        expected = -.23*np.asarray(r)*np.linalg.norm(r)**.4*.8**-.4*1.7**1.3
        np.testing.assert_allclose(evaluate(candidate, r, properties), expected)


def test_radial_positive_power_is_not_mistaken_for_inverse_power():
    candidate = hints(radial_result=radial(power=2.3))['candidates'][0]
    magnitude1 = np.linalg.norm(evaluate(candidate, [1., 0.]))
    magnitude2 = np.linalg.norm(evaluate(candidate, [2., 0.]))
    assert magnitude2/magnitude1 == pytest.approx(2.**2.3)


def test_constant_properties_remain_unknown_and_amplitude_conditional():
    candidate = hints(radial_result=radial(powers={}, fixed={'mass': [2.], 'charge': [.5]}))['candidates'][0]
    assert len(candidate['parameter_spec']) == 2
    assert candidate['evidence']['unknown_property_effects'] == ['charge', 'mass']
    assert candidate['evidence']['conditional_on_fixed_property_values'] == {'mass': [2.], 'charge': [.5]}
    assert any('UNKNOWN, not zero' in w for w in candidate['warnings'])


@pytest.mark.parametrize('change', ['nonradial', 'mixed', 'rank', 'confounded', 'wrong_center', 'overflow', 'underflow'])
def test_radial_counterexamples_do_not_yield_a_hint(change):
    source = radial()
    if change == 'nonradial': source['usable_for_power_interpretation'] = False
    elif change == 'mixed': source['radial_direction'] = 'mixed'
    elif change == 'rank': source['design']['full_column_rank'] = False
    elif change == 'confounded': source['positive_property_powers'].pop('mass')
    elif change == 'wrong_center': source['reference_point'] = [1., 0.]
    else: source['intercept_log_magnitude'] = -1000. if change == 'underflow' else 1000.
    assert hints(radial_result=source)['candidates'] == []


def test_curvature_is_disclosed_without_choosing_an_alternative_formula():
    diagnostic = {'radial_diagnostic': radial(), 'radial_curvature': {
        'status': 'descriptive_comparison', 'cv_ratio_linear_over_quadratic': 4.2}}
    candidate = propose_observation_candidates(diagnostic, TASK)['candidates'][0]
    assert candidate['kind'] == 'empirical_radial_power'
    assert candidate['evidence']['source_curvature_cv_ratio_linear_over_quadratic'] == 4.2
    assert any('single exponent cannot represent changing local slopes' in warning for warning in candidate['warnings'])


def test_more_than_three_identified_property_exponents_cannot_hide_parameters():
    names = ['property_a', 'property_b', 'property_c', 'property_d']
    source = radial(powers=dict(zip(names, [.1, .2, .3, .4])))
    assert hints(radial_result=source, task={'allowed_properties': names})['candidates'] == []


def test_report_does_not_alias_fixed_property_observations():
    source = radial(powers={}, fixed={'mass': [1.], 'charge': [2.]})
    result = hints(radial_result=source)
    result['candidates'][0]['evidence']['conditional_on_fixed_property_values']['mass'][0] = 9.
    result['candidates'][0]['evidence']['observed_radius_range'][0] = 9.
    assert source['conditional_on_fixed_property_values']['mass'] == [1.]
    assert source['radius_range'] == [.7, 4.]


def test_cap_dedup_dsl_numeric_literal_rules_and_input_independence():
    models = [model({('ax', 'x'): -.4, ('ay', 'y'): -.7}, degree=1, cv=.2),
              model({('ax', 'x'): -.4, ('ay', 'y'): -.7, ('ax', 'x*y'): .2}, degree=2, cv=.1),
              model({('ax', 'x'): -.4, ('ay', 'y'): -.7, ('ax', 'x^3'): .2}, degree=3, cv=.01)]
    diagnostics = {'space_regression': {'models': models}, 'radial_diagnostic': radial(), 'world_id': 'do_not_read'}
    task = copy.deepcopy(TASK)
    before = copy.deepcopy((diagnostics, task))
    result = propose_observation_candidates(diagnostics, task)
    assert len(result['candidates']) == 3
    for candidate in result['candidates']:
        assert len(candidate['parameter_spec']) <= 5
        Expression(candidate['law_spec'], candidate['parameter_spec'], task['allowed_properties'])
        for source in candidate['law_spec'].values():
            literals = [n.value for n in ast.walk(ast.parse(source, mode='eval')) if isinstance(n, ast.Constant) and not isinstance(n.value, str)]
            assert all(type(value) is int and value in (0, 1, 2, 3) for value in literals)
    json.dumps(result, allow_nan=False)
    assert (diagnostics, task) == before
    task['world_id'] = 'another_world'
    diagnostics['world_id'] = 'different_ignored_metadata'
    assert propose_observation_candidates(diagnostics, task) == result
    same = hints(*(model({('ax', 'x'): -.4, ('ay', 'y'): -.7}, degree=degree, cv=1e-12) for degree in (1, 2, 3)))
    assert len(same['candidates']) == 1
    assert same['candidates'][0]['evidence']['source_degree'] == 1


def test_synthetic_trajectories_through_real_diagnostics_to_formal_dsl():
    matrix = np.array([[-.61, .23], [-.17, -.42]])
    rng = np.random.default_rng(141)
    times = np.linspace(0, .5, 80)
    probes = []
    for i in range(7):
        initial = np.r_[rng.uniform(-2, 2, 2), rng.uniform(-.5, .5, 2)]
        solution = solve_ivp(lambda t, z: np.r_[z[2:], matrix @ z[:2]], (0, .5), initial,
                             t_eval=times, atol=1e-12, rtol=1e-11)
        probes.append({'probe_id': f'p{i}', 'times': times.tolist(), 'r_obs': solution.y[:2].T.tolist(),
                       'v_obs': solution.y[2:].T.tolist(),
                       'initial_conditions': {'r0': initial[:2].tolist(), 'v0': initial[2:].tolist(), 't0': 0., 'properties': {}}})
    result = propose_observation_candidates(diagnose(probes, TASK), TASK)
    candidate = next(c for c in result['candidates'] if c['kind'] == 'independent_polynomial')
    assert len(candidate['parameter_spec']) == 4
    for r in ([.2, -.3], [-1.7, .6]):
        np.testing.assert_allclose(evaluate(candidate, r), matrix @ r, rtol=2e-5, atol=2e-7)
