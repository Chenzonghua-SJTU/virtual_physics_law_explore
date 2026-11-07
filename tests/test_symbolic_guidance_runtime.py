"""Budget and evidence review with public synthetic records; no actual tools or searches."""
import copy

import pytest

from shore_agent.symbolic_guidance import build_review


def probe(position=(1., 1.), velocity=(.1, .2), *, t0=0., mass=1., charge=1.):
    return {'initial_conditions': {'r0': list(position), 'v0': list(velocity), 't0': t0,
                                   'properties': {'mass': mass, 'charge': charge}},
            'times': [t0, t0+.1, t0+.2],
            'r_obs': [[position[i]+t*velocity[i] for i in range(2)] for t in (0, .1, .2)],
            'v_obs': [list(velocity)]*3}


def records():
    return {'probe': {'baseline': probe(), 'negative': probe((-1., -2.), (-.2, .1)),
                      'other': probe((2., -1.), (0., .3)), 'mass_contrast': probe(mass=2.),
                      'charge_contrast': probe(charge=.5), 'delayed': probe(t0=7.)},
            'law': {}, 'validation': {}, 'symbolic_search': {}}


def budget(seconds=180., energy=4):
    return {'wall_seconds_remaining': seconds, 'energy_remaining': energy, 'session_ended': False}


def test_review_exposes_existing_contrasts_without_changing_selected_data():
    data = records()
    before = copy.deepcopy(data)
    ids = ['baseline', 'negative', 'other']
    review = build_review(data, budget(), {'allowed_properties': ['mass', 'charge']},
                          train_probe_ids=ids)
    assert review['recommended_search_seconds'] == 47
    assert review['new_training_probe_capacity_preserving_two_energy'] == 2
    assert review['unselected_acquired_property_contrasts'] == {
        'mass': ['mass_contrast'], 'charge': ['charge_contrast']}
    assert review['reviewed_probe_ids'] == ids
    assert review['acquired_probe_ids_retained'] == list(data['probe'])
    assert review['advisory_only'] and not review['tool_executed']
    assert data == before
    assert 'selected_law_large_relative_validation_residual' not in review['reasons']


def test_delayed_control_requires_same_position_velocity_and_all_properties():
    data = records()
    data['probe']['changed_property_at_later_time'] = probe(t0=10., mass=2.)
    review = build_review(data, budget(), train_probe_ids=['baseline', 'delayed',
                                                        'changed_property_at_later_time'])
    controls = review['coverage']['same_complete_initial_state_time_controls']
    assert controls == [{'probe_ids': ['baseline', 'delayed'], 'launch_time_difference': 7.}]
    assert 'no_same_complete_initial_state_delayed_launch_control' not in review['reasons']
    review = build_review(data, budget(), train_probe_ids=['baseline', 'changed_property_at_later_time'])
    assert 'no_same_complete_initial_state_delayed_launch_control' in review['reasons']


def test_only_open_properties_are_reported_and_covered_variation_is_preserved():
    data = records()
    review = build_review(data, budget(), {'allowed_properties': ['mass']},
                          train_probe_ids=['baseline', 'mass_contrast', 'delayed'])
    assert review['coverage']['selected_property_values'] == {'mass': [1., 2.]}
    assert 'open_properties_not_varied_in_training' not in review['reasons']
    assert 'charge' not in review['unselected_acquired_property_contrasts']


@pytest.mark.parametrize('options', [{'already_reviewed': True}, {'symbolic_enabled': False}])
def test_one_shot_and_disabled_modes_do_not_create_repeated_advice(options):
    assert build_review(records(), budget(), **options) is None


@pytest.mark.parametrize('seconds', [0., 20., 35.])
def test_final_submission_reserve_is_not_interrupted(seconds):
    assert build_review(records(), budget(seconds)) is None


def test_review_does_not_spend_last_energy_or_recommend_unaffordable_search():
    data = records()
    data['symbolic_search']['search_failed'] = {'status': 'unavailable', 'candidates': []}
    review = build_review(data, budget(60, 1))
    assert review['recommended_search_seconds'] is None
    assert review['new_training_probe_capacity_preserving_two_energy'] == 0
    assert 'latest_search_has_no_usable_candidates' in review['reasons']
    assert review['acquired_probe_ids_retained'] == list(data['probe'])
    assert any('不建议新增训练探针' in text for text in review['instructions'])
    assert any('不会因一次搜索失败失效' in text for text in review['instructions'])
    # Searching already acquired data does not require new probe energy.
    assert build_review(data, budget(180, 0))['recommended_search_seconds'] == 47


def test_usable_timeout_and_axis_only_results_are_not_failure_feedback():
    data = records()
    data['symbolic_search']['search'] = {'status': 'timeout', 'candidates': [],
                                        'axis_candidates': {'ax': [{'source': 'x'}], 'ay': []}}
    review = build_review(data, budget())
    assert review is None  # Covered controls plus usable output need no failure reminder.


def test_nonconvergence_and_relative_validation_error_trigger_auditable_review():
    data = records()
    data['law']['chosen'] = {'fit_status': 'not_converged',
                             'train_probe_ids': ['baseline', 'negative', 'other']}
    data['validation']['check'] = {'law_id': 'chosen', 'test_probe_ids': ['delayed'],
        'errors': {'per_probe': [{'probe_id': 'delayed', 'position_rmse': .03}]}}
    data['validation']['unrelated'] = {'law_id': 'another',
        'errors': {'per_probe': [{'probe_id': 'delayed', 'position_rmse': 1000.}]}}
    review = build_review(data, budget(), {'position_noise_sigma': 0.}, law_id='chosen')
    assert 'selected_fit_not_converged' in review['reasons']
    assert 'selected_law_large_relative_validation_residual' in review['reasons']
    assert len(review['validation_evidence']) == 1
    evidence = review['validation_evidence'][0]
    assert evidence['validation_id'] == 'check' and evidence['probe_id'] == 'delayed'
    assert evidence['relative_to_observed_change'] > .2
    assert 'not an official threshold' in evidence['interpretation']
    assert review['reviewed_probe_ids'] == data['law']['chosen']['train_probe_ids']


def test_observation_noise_and_tiny_errors_are_not_mislabeled_as_large_residual():
    data = records()
    data['law']['chosen'] = {'fit_status': 'converged', 'train_probe_ids': ['baseline']}
    data['validation']['check'] = {'law_id': 'chosen',
        'errors': {'per_probe': [{'probe_id': 'delayed', 'position_rmse': .03}]}}
    noisy = build_review(data, budget(), {'position_noise_sigma': .01}, law_id='chosen')
    assert 'selected_law_large_relative_validation_residual' not in noisy['reasons']
    data['validation']['check']['errors']['per_probe'][0]['position_rmse'] = 1e-10
    exact = build_review(data, budget(), {'position_noise_sigma': 0.}, law_id='chosen')
    assert 'selected_law_large_relative_validation_residual' not in exact['reasons']


def test_absent_or_incomplete_observations_do_not_invent_evidence():
    assert build_review({'probe': {}}, budget()) is None
    assert build_review({'probe': {'incomplete': {'times': [0, 1], 'v_obs': [[0, 0]]}}}, budget()) is None
    assert build_review(records(), {**budget(), 'session_ended': True}) is None


def test_public_evidence_review_is_invariant_to_world_identifiers():
    public={'allowed_properties':['mass','charge'],'reference_length':2.}
    expected=build_review(records(),budget(),public)
    for label in ['world_1','world_6','unseen_opaque_identifier']:
        metadata=dict(public,world_id=label,world_name=label)
        assert build_review(records(),budget(),metadata)==expected
