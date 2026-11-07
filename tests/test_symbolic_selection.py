"""Accuracy/complexity tradeoffs without using any development-world labels."""
import copy

from shore_agent.symbolic_selection import rank_candidates, structural_complexity


def candidate(formula, mse):
    return {'law_spec': {'ax': formula, 'ay': '-a*y'},
            'parameter_spec': [{'name': 'a', 'initial': .2}],
            'normalized_acceleration_search_loss': mse,
            'residuals': {'trajectory_training': {'overall': {'position_mse': mse}}}}


def test_nearly_equal_error_prefers_simple_but_material_gain_preserves_complex_law():
    simple = candidate('-a*x', .0101)
    complex_law = candidate('-a*x + a*sin(x*x)*cos(y)', .01)
    assert rank_candidates([complex_law, simple], [{}])[0] is simple
    simple['residuals']['trajectory_training']['overall']['position_mse'] = .1
    assert rank_candidates([simple, complex_law], [{}])[0] is complex_law


def test_public_noise_tolerance_changes_only_nearby_accuracy_choice():
    probes = [{'r_obs': [[1, 0]] * 100, 'observation_noise': {'position_sigma': .05}}]
    simple = candidate('-a*x', .0054)
    complex_law = candidate('-a*x+a*sin(x*y)', .005)
    assert rank_candidates([complex_law, simple], probes)[0] is simple
    clean = copy.deepcopy(probes)
    clean[0]['observation_noise']['position_sigma'] = 0
    assert rank_candidates([complex_law, simple], clean)[0] is complex_law


def test_exp_and_trig_have_equal_cost_and_can_win_with_accuracy():
    exp = candidate('-a*exp(x)', .01)
    sin = candidate('-a*sin(x)', .01)
    assert structural_complexity(exp) == structural_complexity(sin)
    assert rank_candidates([candidate('-a*x', .1), exp], [{}])[0] is exp


def test_known_domain_failure_is_not_rewarded_for_low_error_or_simplicity():
    bad = candidate('-a*x', 0)
    bad['residuals']['observed_velocity_integral'] = {'domain_error_probe_ids': ['p1']}
    good = candidate('-a*x+a*sin(y)', .01)
    assert rank_candidates([bad, good], [{}])[0] is good


def test_unfinished_observed_path_check_does_not_win_by_small_subset_error():
    partial = candidate('-a*x', 0)
    partial['residuals']['observed_velocity_integral'] = {'complete': False}
    checked = candidate('-a*x+a*sin(y)', .01)
    checked['residuals']['observed_velocity_integral'] = {'complete': True}
    assert rank_candidates([partial, checked], [{}])[0] is checked


def test_acceleration_loss_is_not_compared_numerically_with_position_mse():
    unrefitted = candidate('-a*x', 1e-20)
    del unrefitted['residuals']['trajectory_training']
    refitted = candidate('-a*x+a*sin(y)', .01)
    result = rank_candidates([unrefitted, refitted], [{}])
    assert result[0] is refitted
    assert result[1]['selection_diagnostics']['metric'] == 'normalized_acceleration_loss'


def test_nonfinite_error_cannot_displace_a_finite_candidate():
    bad = candidate('-a*x', float('nan'))
    good = candidate('-a*exp(x)', .01)
    result = rank_candidates([bad, good], [{}])
    assert result[0] is good and result[1]['selection_diagnostics']['error'] is None
