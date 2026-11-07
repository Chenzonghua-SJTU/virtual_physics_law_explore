"""Synthetic harmonic compression and ordinary DSL verification, without worlds."""
import ast
import copy
import json
import math

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from shore_agent.expressions import Expression
from shore_agent.harmonic_candidates import TERMS, propose_harmonic_candidate
from shore_agent.harmonic_diagnostics import diagnose_harmonic
from shore_agent.numerics import rollout


TASK = {'allowed_properties': ['mass'], 'property_controls': {'mass': {'default': 1.}},
        'position_noise_sigma': 0., 'velocity_noise_sigma': 0.}


def source(values=None):
    values = values or {('ax', 'x'): -.2, ('ay', 'y'): -.3,
                        ('ax', 'y*sin(omega*t)'): .04, ('ay', 'x*cos(omega*t)'): -.07}
    identification = {'status': 'locally_resolved_within_searched_family', 'reasons': [],
                      'local_profile_interval': [.69, .71], 'global_frequency_uniqueness_established': False}
    return {'status': 'descriptive_comparison', 'harmonic_model': {
        'omega': .7, 'basis': list(TERMS),
        'design': {'full_column_rank': True, 'coefficient_identifiability': 'full_rank_design'},
        'frequency_identification': identification,
        'frequency_search': {'frequency_lower': .01, 'frequency_upper': 2., 'grid_capped': False},
        'cross_validation': {'status': 'available', 'split_unit': 'whole_probe_trajectory',
            'errors': {'relative_rmse': 1e-8}, 'frequency_identification_in_all_folds': True,
            'folds': [{'usable': True, 'selected_omega': .7, 'held_out_probe_ids': [f'p{i}'],
                       'frequency_identification': copy.deepcopy(identification)} for i in range(3)]},
        'diagnostic_coefficients': [{'term': term, 'ax': values.get(('ax', term), 0.),
            'ay': values.get(('ay', term), 0.),
            'delta_velocity_contribution_rms': math.hypot(values.get(('ax', term), 0.), values.get(('ay', term), 0.))}
            for term in TERMS]}}


def evaluated(candidate, t, r):
    expression = Expression(candidate['law_spec'], candidate['parameter_spec'], allowed_properties=['mass'])
    return expression.acceleration(t, r, [.1, -.3], [], {'mass': 1.},
                                   {p['name']: p['initial'] for p in candidate['parameter_spec']})


def basis(t, r, omega):
    spatial = np.array([1., *r])
    return np.r_[spatial, np.sin(omega*t)*spatial, np.cos(omega*t)*spatial]


def test_independent_parameters_preserve_signs_and_include_free_frequency():
    diagnostic = source()
    candidate = propose_harmonic_candidate(diagnostic, TASK)['candidate']
    assert candidate['kind'] == 'independent_affine_harmonic'
    assert len(candidate['parameter_spec']) == 5
    assert candidate['parameter_spec'][-1] == {'name': 'c4', 'initial': .7, 'lower': .01, 'upper': 2.}
    beta = np.array([[r['ax'], r['ay']] for r in diagnostic['harmonic_model']['diagnostic_coefficients']])
    for t, r in [(-1., [2., -.4]), (2.3, [-.3, .9])]:
        np.testing.assert_allclose(evaluated(candidate, t, r), basis(t, r, .7)@beta)
    for formula in candidate['law_spec'].values():
        assert not [n for n in ast.walk(ast.parse(formula)) if isinstance(n, ast.Constant)]
    expression = Expression(candidate['law_spec'], candidate['parameter_spec'])
    assert expression.used_parameters == {p['name'] for p in candidate['parameter_spec']}


def test_opposite_sign_sharing_never_merges_different_dimensions():
    diagnostic = source({('ax', '1'): 1., ('ay', 'sin(omega*t)'): -1.,
                         ('ax', 'x'): 1., ('ay', 'y'): -1., ('ax', 'x*cos(omega*t)'): 2.})
    candidate = propose_harmonic_candidate(diagnostic, TASK)['candidate']
    assert candidate['kind'] == 'signed_shared_affine_harmonic'
    groups = candidate['evidence']['coefficient_groups']
    assert len(groups) == 3 and len(candidate['parameter_spec']) == 4
    assert {g['coefficient_dimensions'] for g in groups} == {'length/time^2', '1/time^2'}
    offset_group = next(g for g in groups if any(t['term'] == '1' for t in g['members']))
    position_group = next(g for g in groups if any(t['term'] == 'x' for t in g['members']))
    assert offset_group['parameter'] != position_group['parameter']
    assert all(len({int(t['term'] in ('x', 'y') or t['term'].startswith(('x*', 'y*')))
                    for t in g['members']}) == 1 for g in groups)
    for t, r in [(.3, [2., -.4]), (2.3, [-.3, .9])]:
        np.testing.assert_allclose(evaluated(candidate, t, r),
            [1+r[0]+2*r[0]*np.cos(.7*t), -np.sin(.7*t)-r[1]])
    assert any('not proven symmetry' in text for text in candidate['warnings'])


def test_coefficient_groups_are_complete_link_not_transitive_chains():
    candidate = propose_harmonic_candidate(source({
        ('ax', 'x'): 1., ('ay', 'y'): -1.04, ('ax', 'x*sin(omega*t)'): 1.08,
        ('ay', 'y*sin(omega*t)'): 2., ('ax', 'x*cos(omega*t)'): 3.,
    }), TASK)['candidate']
    assert candidate is not None and len(candidate['parameter_spec']) == 5
    for group in candidate['evidence']['coefficient_groups']:
        values = [abs(t['coefficient']) for t in group['members']]
        assert all(abs(a-b) <= .05*max(a, b) for a in values for b in values)
    shared = next(g for g in candidate['evidence']['coefficient_groups'] if len(g['members']) == 2)
    assert sorted(abs(t['coefficient']) for t in shared['members']) == [1., 1.04]
    assert candidate['parameter_spec'][0]['initial'] == pytest.approx(1.02)


def test_pruned_candidate_never_inherits_parent_cv_and_exposes_omitted_terms():
    diagnostic = source({('ax', 'x'): -.2, ('ay', 'y'): -.3,
                         ('ax', 'y*sin(omega*t)'): .04, ('ay', 'x*cos(omega*t)'): 1e-7})
    diagnostic['harmonic_model']['cross_validation']['errors']['relative_rmse'] = 0.
    candidate = propose_harmonic_candidate(diagnostic, TASK)['candidate']
    evidence = candidate['evidence']
    assert len(candidate['parameter_spec']) == 4
    assert any(t['term'] == 'x*cos(omega*t)' and t['coefficient'] == 1e-7 for t in evidence['pruned_axis_terms'])
    assert evidence['source_whole_probe_cv_relative_rmse'] == 0.
    assert evidence['source_errors_are_not_candidate_errors'] is True
    assert evidence['candidate_cross_validation']['status'] == 'unavailable'
    assert 'errors' not in candidate and 'cross_validation' not in candidate
    assert any('outside those observations' in text for text in candidate['warnings'])
    assert any('Aliases' in text for text in candidate['warnings'])
    assert 'law_id' not in json.dumps(candidate)


@pytest.mark.parametrize('change', [
    lambda d: d.update(status='budget_exhausted'),
    lambda d: d['harmonic_model']['design'].update(full_column_rank=False),
    lambda d: d['harmonic_model']['frequency_identification'].update(status='unresolved'),
    lambda d: d['harmonic_model']['frequency_identification'].update(reasons=['separated_near_best_frequencies_or_broad_profile']),
    lambda d: d['harmonic_model']['frequency_search'].update(grid_capped=True),
    lambda d: d['harmonic_model']['cross_validation'].update(status='unavailable'),
    lambda d: d['harmonic_model']['cross_validation'].update(frequency_identification_in_all_folds=False),
    lambda d: d['harmonic_model']['cross_validation'].update(split_unit='random_rows'),
    lambda d: d['harmonic_model']['cross_validation'].update(folds=[]),
    lambda d: d['harmonic_model']['cross_validation']['folds'][0].update(usable=False),
    lambda d: d['harmonic_model']['cross_validation']['folds'][0]['frequency_identification'].update(status='unresolved'),
    lambda d: d['harmonic_model']['cross_validation']['folds'][0].update(selected_omega=float('nan')),
    lambda d: d['harmonic_model']['cross_validation']['errors'].update(relative_rmse=float('nan')),
    lambda d: d['harmonic_model']['frequency_search'].update(frequency_lower=1.),
    lambda d: d['harmonic_model'].update(omega=-.7),
])
def test_unidentified_aliased_partial_or_nonfinite_evidence_cannot_offer_candidate(change):
    diagnostic = source(); change(diagnostic)
    result = propose_harmonic_candidate(diagnostic, TASK)
    assert result['candidate'] is None and result['reason']


@pytest.mark.parametrize('value', [None, [], 'bad'])
@pytest.mark.parametrize('field', ['harmonic_model', 'design', 'cross_validation', 'frequency_identification', 'frequency_search'])
def test_malformed_mappings_return_unavailable(field, value):
    diagnostic = source()
    if field == 'harmonic_model': diagnostic[field] = value
    else: diagnostic['harmonic_model'][field] = value
    assert propose_harmonic_candidate(diagnostic, TASK)['candidate'] is None


def test_too_many_distinct_amplitudes_and_no_harmonic_content_are_rejected():
    values = {('ax', term): float(i+1) for i, term in enumerate(TERMS[:5])}
    result = propose_harmonic_candidate(source(values), TASK)
    assert result['reason'] == 'more_than_four_distinct_amplitudes_plus_free_frequency'
    assert propose_harmonic_candidate(source({('ax', 'x'): 1.}), TASK)['reason'] == 'no_retained_harmonic_contribution'


def test_malformed_coefficients_and_extreme_finite_numbers_are_bounded():
    for mutation in ('duplicate', 'unhashable', 'nonfinite', 'overflow', 'zero_mismatch'):
        diagnostic = source(); coefficients = diagnostic['harmonic_model']['diagnostic_coefficients']
        if mutation == 'duplicate': coefficients[0]['term'] = coefficients[1]['term']
        elif mutation == 'unhashable': coefficients[0]['term'] = []
        elif mutation == 'nonfinite': coefficients[0]['ax'] = float('nan')
        elif mutation == 'overflow': coefficients[0].update(ax=1.7e308, ay=1.7e308)
        else: coefficients[0]['delta_velocity_contribution_rms'] = 1.
        assert propose_harmonic_candidate(diagnostic, TASK)['candidate'] is None
    huge = source({('ax', 'x'): 1e308, ('ay', 'y'): -1e308,
                   ('ax', 'x*sin(omega*t)'): 1e308, ('ay', 'y*sin(omega*t)'): 1e308,
                   ('ax', 'x*cos(omega*t)'): 1e308})
    assert propose_harmonic_candidate(huge, TASK)['reason'] == 'candidate_failed_ordinary_dsl_validation'


def test_subnormal_contributions_do_not_retain_zero_terms_or_divide_by_zero():
    tiny = float.fromhex('0x0.0000000000001p-1022')
    diagnostic = source({('ax', 'x'): tiny, ('ay', 'y'): -tiny,
                         ('ax', 'x*sin(omega*t)'): tiny, ('ay', 'y*sin(omega*t)'): tiny,
                         ('ax', 'x*cos(omega*t)'): tiny})
    candidate = propose_harmonic_candidate(diagnostic, TASK)['candidate']
    assert candidate is not None
    assert len(candidate['parameter_spec']) == 2 and candidate['parameter_spec'][0]['initial'] == tiny
    assert all(t['coefficient'] != 0 for group in candidate['evidence']['coefficient_groups'] for t in group['members'])
    json.dumps(candidate, allow_nan=False)


def test_inputs_are_not_mutated_or_aliased_and_world_labels_are_unused():
    diagnostic, task = source(), copy.deepcopy(TASK)
    before = copy.deepcopy(diagnostic)
    candidate = propose_harmonic_candidate(diagnostic, task)['candidate']
    assert diagnostic == before and task == TASK
    assert propose_harmonic_candidate(diagnostic, dict(task, world_id='unused', hidden_formula='unread'))['candidate'] == candidate
    candidate['evidence']['source_frequency_identification']['reasons'].append('local edit')
    assert diagnostic == before
    assert propose_harmonic_candidate(diagnostic, None)['candidate'] is None


def synthetic_system(seed, shared):
    rng = np.random.default_rng(seed)
    omega = float(rng.uniform(.65, 1.05)); beta = np.zeros((9, 2))
    a, b, h, offset = rng.uniform(.15, .22), rng.uniform(.045, .065), rng.uniform(.02, .033), rng.uniform(.008, .014)
    if shared:
        beta[1, 0], beta[2, 1] = -a, -a
        beta[2, 0], beta[1, 1] = b, -b
        beta[4, 0], beta[5, 1], beta[8, 0], beta[7, 1] = h, -h, h, h
        beta[3, 0], beta[6, 1] = offset, -offset
    else:
        beta[1, 0], beta[2, 1], beta[5, 0], beta[7, 1] = -a, -1.4*a, b, -h

    def trajectory(identifier, start, r0, v0):
        times = np.linspace(start, start+4.8, 49)
        def rhs(t, z):
            return np.r_[z[2:], basis(t, z[:2], omega)@beta]
        solution = solve_ivp(rhs, (times[0], times[-1]), np.r_[r0, v0], t_eval=times,
                             rtol=2e-12, atol=2e-13, max_step=.02)
        assert solution.success
        return {'probe_id': identifier, 'times': times.tolist(),
                'r_obs': solution.y[:2].T.tolist(), 'v_obs': solution.y[2:].T.tolist(),
                'initial_conditions': {'r0': list(r0), 'v0': list(v0), 't0': start, 'properties': {'mass': 1.}}}
    probes = [trajectory(f'train{i}', .6*(i % 3), rng.uniform(-2, 2, 2), rng.uniform(-.3, .3, 2)) for i in range(8)]
    held = trajectory('fresh-independent', .37, rng.uniform(-2, 2, 2), rng.uniform(-.3, .3, 2))
    return probes, held, omega, beta


@pytest.mark.parametrize('seed,shared', [(81, False), (137, True)])
def test_random_diagnosis_to_candidate_matches_independent_dsl_states_and_trajectory(seed, shared):
    probes, held, omega, beta = synthetic_system(seed, shared)
    diagnostic = diagnose_harmonic(probes, TASK, max_seconds=10.)
    assert diagnostic['status'] == 'descriptive_comparison'
    result = propose_harmonic_candidate(diagnostic, TASK)
    assert result['candidate'] is not None, result['reason']
    candidate = result['candidate']
    assert candidate['kind'] == ('signed_shared_affine_harmonic' if shared else 'independent_affine_harmonic')
    assert len(candidate['parameter_spec']) == 5
    assert candidate['parameter_spec'][-1]['initial'] == pytest.approx(omega, rel=2e-4)
    rng = np.random.default_rng(seed+1)
    for _ in range(20):
        t, r = rng.uniform(-1., 8.), rng.uniform(-3., 3., 2)
        np.testing.assert_allclose(evaluated(candidate, t, r), basis(t, r, omega)@beta, rtol=1e-4, atol=2e-6)
    assert held['probe_id'] not in diagnostic['probe_ids']
    frozen = {p['name']: p['initial'] for p in candidate['parameter_spec']}
    predicted = rollout(candidate['law_spec'], frozen, held, [])
    np.testing.assert_allclose(predicted['r_pred'], held['r_obs'], rtol=1e-4, atol=3e-6)
    np.testing.assert_allclose(predicted['v_pred'], held['v_obs'], rtol=1e-4, atol=3e-6)
    assert candidate['evidence']['candidate_cross_validation']['status'] == 'unavailable'
    json.dumps(candidate, allow_nan=False)
