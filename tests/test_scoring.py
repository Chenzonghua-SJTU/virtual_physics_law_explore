"""PDF score tests use local deterministic fixtures, never model API requests."""
import copy
import json
import math

import numpy as np
import pytest

from evaluate import evaluate_run, score_existing_evaluation
from shore_scoring import problem_score
from shore_sim.worlds import truth_claims


CLAIMS = {'dynamics_order': 2, 'hidden_matter': False, 'time_dependence': False}


def score(mse=0., variance=1., energy=20., **kwargs):
    return problem_score(mse, variance, CLAIMS, CLAIMS, energy, 20, **kwargs)


@pytest.mark.parametrize('mse,variance,energy,prediction,conservation', [
    (0., 1., 20., 80., 4.), (.1, 1., 20., 40., 4.),
    (.100001, 1., 20., 80 / 2.00001, 0.),
    (1., 10., 100., 40., 0.), (1e-12, 0., 0., 80 / 11, 0.),
    (0., 1., 0., 80., 5.), (0., 1., 100., 80., 0.),
])
def test_pdf_formula_exact_components_and_conservation_gate(mse, variance, energy, prediction, conservation):
    result = score(mse, variance, energy)
    assert result['status'] == 'scored'
    assert result['prediction'] == pytest.approx(prediction)
    assert result['conservation'] == pytest.approx(conservation)
    assert result['law'] == 15
    assert result['total'] == pytest.approx(prediction + conservation + 15)
    assert result['maximum'] == 100 and result['official_score'] is False
    assert result['formula_version'] == 'shore_pdf_1101'


def test_three_declarations_are_independent_and_require_correct_types():
    declared = {'dynamics_order': 2, 'hidden_matter': 0, 'time_dependence': True}
    result = problem_score(0., 1., declared, CLAIMS, 20., 20)
    assert result['law'] == 5
    assert [item['points'] for item in result['claim_checks']] == [5, 0, 0]
    assert result['total'] == 89


def test_e4_energy_denominator_and_version_do_not_change_legacy_scores():
    old = score(energy=4)
    new = score(energy=4, energy_budget=10, formula_version='shore_e4_10energy')
    assert old['conservation'] == pytest.approx(4.8)
    assert old['formula_version'] == 'shore_pdf_1101'
    assert new['conservation'] == 3
    assert new['total'] == 98
    assert new['formula_version'] == 'shore_e4_10energy'
    assert score(energy=11, energy_budget=10)['reason'] == 'energy_usage_unavailable'


@pytest.mark.parametrize('energy', [None, -1, 101, True, math.inf, math.nan])
def test_missing_or_invalid_energy_never_invents_conservation_bonus(energy):
    result = score(energy=energy)
    assert result['status'] == 'unavailable' and result['reason'] == 'energy_usage_unavailable'
    assert result['prediction'] == 80 and result['law'] == 15
    assert result['total'] is None and result['conservation'] is None
    low_prediction = score(mse=1, energy=energy)
    assert low_prediction['status'] == 'scored' and low_prediction['conservation'] == 0


@pytest.mark.parametrize('mse,variance', [(True, 1), (-1, 1), (math.nan, 1), (1, math.inf), (1, -1)])
def test_invalid_statistics_are_not_turned_into_a_score(mse, variance):
    result = score(mse, variance)
    assert result['status'] == 'unavailable' and result['reason'] == 'invalid_position_statistics'
    assert result['total'] is None


def test_candidate_failure_zeroes_prediction_but_oracle_failure_is_unavailable():
    result = score(energy=None, candidate_failed=True)
    assert result['total'] == 15 and result['prediction'] == result['conservation'] == 0
    assert result['reason'] == 'candidate_prediction_invalid'
    oracle = score(candidate_failed=True, truth_failed=True)
    assert oracle['status'] == 'unavailable' and oracle['reason'] == 'truth_reference_failed'
    assert oracle['total'] is None


def test_fewer_than_twenty_tests_do_not_claim_pdf_score():
    result = problem_score(0, 1, CLAIMS, CLAIMS, 0, 19)
    assert result['status'] == 'unavailable' and result['reason'] == 'fewer_than_20_test_trajectories'


@pytest.mark.parametrize('world', [f'world_{i}' for i in range(1, 8)])
def test_private_truth_declarations_distinguish_moving_sources_and_explicit_time(world):
    assert truth_claims(world, 'v4') == {**CLAIMS, 'time_dependence': world == 'world_7'}


def archive(root, *, remaining=80):
    (root / 'records/submission').mkdir(parents=True)
    (root / 'records/law').mkdir()
    submission = {'submission_id': 's1', 'law_id': 'law_1', 'status': 'accepted',
                  'session_ended': True, 'claims': CLAIMS}
    law = {'law_id': 'law_1', 'law_spec': {'ax': '-k*x', 'ay': '-k*(y-c)'},
           'fitted_parameters': {'k': .3, 'c': 1.}, 'known_bodies': []}
    (root / 'records/submission/s1.json').write_text(json.dumps(submission))
    (root / 'records/law/law_1.json').write_text(json.dumps(law))
    (root / 'config.json').write_text(json.dumps({'environment': {'world_id': 'world_1', 'physics_version': 'v4'}}))
    if remaining is not None:
        (root / 'result.json').write_text(json.dumps({'status': 'submitted', 'submission': submission,
                                                     'budget': {'energy_remaining': remaining}}))
    return submission


def test_complete_evaluation_scores_actual_vector_error_and_global_reference_variance(tmp_path):
    from shore_sim.simulator import truth_trajectory
    archive(tmp_path)
    result = evaluate_run(tmp_path, n_probes=20)
    positions = []
    for initial in result['initial_conditions']:
        times = np.round(initial['t0'] + np.arange(initial['n_samples']) * initial['dt'], 10)
        positions.extend(truth_trajectory(initial['r0'], initial['v0'], times, t0=initial['t0'],
                                          world_id='world_1', physics_version='v4')[:, :2])
    positions = np.asarray(positions)
    expected = np.mean(np.sum((positions - positions.mean(axis=0)) ** 2, axis=1))
    assert result['score']['status'] == 'scored'
    assert result['score']['reference_variance'] == pytest.approx(expected)
    assert result['score']['position_mse'] == pytest.approx(result['overall']['position_mse'], abs=1e-25)
    assert result['score']['total'] == pytest.approx(99., abs=1e-8)
    assert result['score']['energy_source'] == 'result.json:budget.energy_remaining'


def test_test_set_is_unchanged_when_agent_observed_an_identical_initial_state(tmp_path):
    archive(tmp_path)
    before = evaluate_run(tmp_path, n_probes=3)
    folder = tmp_path / 'records/probe'
    folder.mkdir()
    initial = before['initial_conditions'][0]
    (folder / 'collision.json').write_text(json.dumps({'initial_conditions': initial}))
    after = evaluate_run(tmp_path, n_probes=3)
    assert before['initial_conditions'] == after['initial_conditions']
    assert before['score']['status'] == after['score']['status'] == 'unavailable'


def test_candidate_timeout_keeps_declaration_points_without_subset_score(tmp_path, monkeypatch):
    archive(tmp_path, remaining=None)

    def fail(*args, **kwargs):
        raise ValueError('candidate timed out')

    monkeypatch.setattr('evaluate.rollout', fail)
    result = evaluate_run(tmp_path, n_probes=20)
    assert not result['complete'] and result['overall'] is None
    assert result['score']['status'] == 'scored' and result['score']['total'] == 15
    assert result['score']['prediction'] == result['score']['conservation'] == 0


def test_reference_failure_does_not_assign_candidate_zero(tmp_path, monkeypatch):
    archive(tmp_path)

    def fail(*args, **kwargs):
        raise ValueError('reference failed')

    monkeypatch.setattr('shore_sim.simulator.truth_trajectory', fail)
    result = evaluate_run(tmp_path, n_probes=20)
    assert result['score']['status'] == 'unavailable'
    assert result['score']['reason'] == 'truth_reference_failed'


def test_budget_fallback_uses_matching_successful_submit_then_final_session_event(tmp_path):
    submission = archive(tmp_path, remaining=None)
    good = {'tool': 'submit', 'result': {'ok': True, 'data': submission, 'budget': {'energy_remaining': 70}}}
    other = copy.deepcopy(good)
    other['result']['data']['submission_id'] = 'someone_else'
    other['result']['budget']['energy_remaining'] = 99
    (tmp_path / 'tools.jsonl').write_text(json.dumps(good) + '\n' + json.dumps(other) + '\n{partial')
    result = evaluate_run(tmp_path, n_probes=20)
    assert result['score']['energy_used'] == 30 and result['score']['conservation'] == 3.5
    (tmp_path / 'tools.jsonl').unlink()
    (tmp_path / 'events.jsonl').write_text(json.dumps({'event': 'session_finished', 'status': 'submitted',
        'submission': submission, 'budget': {'energy_remaining': 60}}) + '\n')
    result = evaluate_run(tmp_path, n_probes=20)
    assert result['score']['energy_used'] == 40 and result['score']['conservation'] == 3


def test_historical_score_reuses_mse_and_reconstructs_only_truth_with_cache(tmp_path, monkeypatch):
    import shore_sim.simulator as simulator
    archive(tmp_path)
    evaluation = evaluate_run(tmp_path, n_probes=20)
    old = copy.deepcopy(evaluation)
    old.pop('score')
    for initial in old['initial_conditions']:
        initial.pop('n_samples')  # Legacy files store sample counts in per_probe.
    saved = copy.deepcopy(old)
    files = {p: p.read_bytes() for p in tmp_path.rglob('*.json')}
    original = simulator.truth_trajectory
    calls = []

    def reference(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(simulator, 'truth_trajectory', reference)
    monkeypatch.setattr('evaluate.rollout', lambda *a, **k: pytest.fail('Must not rerun candidate'))
    cache = {}
    score1 = score_existing_evaluation(tmp_path, old, cache)
    score2 = score_existing_evaluation(tmp_path, old, cache)
    assert score1 == score2 and len(calls) == 20 and len(cache) == 1
    assert score1['total'] == pytest.approx(evaluation['score']['total'])
    assert score1['reference_variance'] == pytest.approx(evaluation['score']['reference_variance'])
    assert old == saved and {p: p.read_bytes() for p in tmp_path.rglob('*.json')} == files


@pytest.mark.parametrize('mutation,reason', [
    ({'law_id': 'other'}, 'evaluation_identity_mismatch'),
    ({'world_id': 'world_7'}, 'evaluation_identity_mismatch'),
    ({'physics_version': 'v3'}, 'evaluation_identity_mismatch'),
    ({'complete': False}, 'incomplete_evaluation'),
    ({'n_successful': 19}, 'incomplete_evaluation'),
    ({'initial_conditions': []}, 'archived_test_samples_unavailable'),
    ({'overall': None, 'successful_subset_overall': {'position_mse': 0}}, 'invalid_position_statistics'),
])
def test_historical_score_refuses_mismatches_missing_samples_and_subset_metrics(tmp_path, monkeypatch, mutation, reason):
    archive(tmp_path)
    evaluation = evaluate_run(tmp_path, n_probes=20)
    evaluation.update(mutation)
    monkeypatch.setattr('shore_sim.simulator.truth_trajectory', lambda *a, **k: pytest.fail('No oracle access'))
    result = score_existing_evaluation(tmp_path, evaluation)
    assert result['status'] == 'unavailable' and result['reason'] == reason


def test_legacy_missing_version_fields_remain_scoreable(tmp_path):
    archive(tmp_path)
    config = json.loads((tmp_path / 'config.json').read_text())
    config['environment'].pop('physics_version')
    (tmp_path / 'config.json').write_text(json.dumps(config))
    evaluation = evaluate_run(tmp_path, n_probes=20)
    evaluation.pop('world_id')
    evaluation.pop('physics_version')
    assert score_existing_evaluation(tmp_path, evaluation)['status'] == 'scored'
