"""Post-session score projections; no models or private truth in the web layer."""
import copy
import hashlib
import json

import pytest

from shore_agent.web_jobs import RunManager, _evaluation_projection, _write
from shore_scoring import problem_score


@pytest.fixture
def scored_run(tmp_path):
    manager = RunManager(tmp_path)
    directory = manager.runs_dir / 'score-example'
    directory.mkdir()
    (directory / 'records/submission').mkdir(parents=True)
    submission = {'submission_id': 's1', 'law_id': 'law_1', 'status': 'accepted', 'session_ended': True}
    configuration = {'environment': {'world_id': 'world_1', 'physics_version': 'v4'}}
    _write(directory / 'config.json', configuration)
    _write(directory / 'result.json', {'status': 'submitted', 'submission': submission})
    _write(directory / 'records/submission/s1.json', submission)
    p, law, c = 80 / 2, 15, 4.5
    score = {'status': 'scored', 'total': p + law + c, 'maximum': 100,
             'prediction': p, 'law': law, 'conservation': c, 'energy_used': 10,
             'position_mse': .1, 'reference_variance': 1, 'normalized_error': .1,
             'claim_checks': [], 'reason': None, 'formula_version': 'shore_pdf_1101',
             'local_only': True, 'official_score': False}
    evaluation = {'world_id': 'world_1', 'physics_version': 'v4', 'submission_id': 's1', 'law_id': 'law_1',
                  'n_trajectories': 20, 'n_successful': 20, 'complete': True, 'failures': [],
                  'overall': {'position_rmse': .1 ** .5}, 'score': score}
    _write(directory / 'evaluation.json', evaluation)
    yield manager, directory, configuration, evaluation
    manager.close()


def test_score_visible_in_snapshot_history_and_recycle_bin_without_rewriting_evidence(scored_run):
    manager, directory, _, evaluation = scored_run
    original = {p.relative_to(directory): p.read_bytes() for p in directory.rglob('*') if p.is_file()}
    detail = manager.snapshot(directory.name)
    row = manager.list_runs()['runs'][0]
    for public in (detail, row):
        assert public['status'] == 'submitted'  # Lifecycle remains compatible with benchmark tools.
        assert public['evaluation_state'] == 'scored'
        assert public['evaluation_score'] == evaluation['score']
    assert {p.relative_to(directory): p.read_bytes() for p in directory.rglob('*') if p.is_file()} == original
    manager.delete(directory.name)
    deleted = manager.list_runs()['deleted_runs'][0]
    assert deleted['evaluation_state'] == 'scored'
    assert deleted['evaluation_score'] == evaluation['score']
    manager.restore(directory.name)
    assert manager.snapshot(directory.name)['evaluation_score'] == evaluation['score']


def test_historical_score_sidecar_requires_exact_original_evaluation_hash(scored_run):
    manager, directory, _, evaluation = scored_run
    score = evaluation.pop('score')
    _write(directory / 'evaluation.json', evaluation)
    original = (directory / 'evaluation.json').read_bytes()
    _write(directory / 'evaluation_score.json', {
        'evaluation_sha256': hashlib.sha256(original).hexdigest(), 'score': score})
    assert manager.snapshot(directory.name)['evaluation_state'] == 'scored'
    assert (directory / 'evaluation.json').read_bytes() == original
    (directory / 'evaluation.json').write_bytes(original + b'\n')
    snapshot = manager.snapshot(directory.name)
    assert snapshot['evaluation_state'] == 'unavailable'
    assert snapshot['evaluation_score'] is None
    assert snapshot['evaluation_error'] == 'stale_score_record'


@pytest.mark.parametrize('field,value', [('world_id', 'world_2'), ('physics_version', 'v3'),
                                        ('law_id', 'another'), ('submission_id', 'another')])
def test_score_for_other_evaluation_identity_is_not_displayed(scored_run, field, value):
    manager, directory, _, evaluation = scored_run
    evaluation[field] = value
    _write(directory / 'evaluation.json', evaluation)
    snapshot = manager.snapshot(directory.name)
    assert snapshot['evaluation_state'] == 'error'
    assert snapshot['evaluation_score'] is None
    assert snapshot['evaluation_error'] == 'evaluation_identity_mismatch'


@pytest.mark.parametrize('value', [None, True, -1, 101, '99', float('nan'), float('inf')])
def test_invalid_scores_never_render_as_numbers(scored_run, value):
    _, directory, config, evaluation = scored_run
    evaluation['score']['total'] = value
    actual = _evaluation_projection(directory, 'submitted', {}, config, evaluation=evaluation)
    assert actual['evaluation_state'] == 'unavailable'
    assert actual['evaluation_score'] is None


def test_incomplete_candidate_predictions_receive_only_document_permitted_points(scored_run):
    manager, directory, _, evaluation = scored_run
    evaluation.update(complete=False, n_successful=19,
                      failures=[{'stage': 'candidate_rollout', 'probe_id': 'hidden_20'}])
    _write(directory / 'evaluation.json', evaluation)
    assert manager.snapshot(directory.name)['evaluation_state'] == 'error'
    claims = {'dynamics_order': 2, 'hidden_matter': False, 'time_dependence': False}
    evaluation['score'] = problem_score(None, None, claims, claims, 10, 20, candidate_failed=True)
    _write(directory / 'evaluation.json', evaluation)
    snapshot = manager.snapshot(directory.name)
    assert snapshot['evaluation_state'] == 'scored'
    assert snapshot['evaluation_score']['total'] == 15
    evaluation['failures'][0]['stage'] = 'truth_reference'
    _write(directory / 'evaluation.json', evaluation)
    assert manager.snapshot(directory.name)['evaluation_state'] == 'error'


def test_missing_score_does_not_use_rmse_or_successful_subset_as_score(scored_run):
    manager, directory, _, evaluation = scored_run
    evaluation.pop('score')
    evaluation['successful_subset_overall'] = {'position_rmse': 0}
    _write(directory / 'evaluation.json', evaluation)
    result = manager.snapshot(directory.name)
    assert result['evaluation_state'] == 'unavailable'
    assert result['evaluation_score'] is None


def test_unavailable_score_keeps_available_components_without_inventing_total(scored_run):
    manager, directory, _, evaluation = scored_run
    evaluation['score'].update(status='unavailable', conservation=None, total=None, reason='missing_energy')
    _write(directory / 'evaluation.json', evaluation)
    snapshot = manager.snapshot(directory.name)
    assert snapshot['evaluation_state'] == 'unavailable'
    assert snapshot['evaluation_score']['total'] is None
    assert snapshot['evaluation_score']['law'] == 15


@pytest.mark.parametrize('status,metadata,running,expected', [
    ('submitted', {}, False, 'pending'), ('evaluating', {}, True, 'running'),
    ('submitted', {'evaluation_status': 'failed'}, False, 'error'),
    ('submitted', {'evaluation_interrupted': True}, False, 'error')])
def test_pending_running_and_failed_evaluation_are_not_scores(scored_run, status, metadata, running, expected):
    _, directory, configuration, _ = scored_run
    (directory / 'evaluation.json').unlink()
    outcome = _evaluation_projection(directory, status, metadata, configuration, running=running)
    assert outcome['evaluation_state'] == expected
    assert outcome['evaluation_score'] is None


def test_no_submission_does_not_get_score(tmp_path):
    assert _evaluation_projection(tmp_path, 'incomplete', {}, {})['evaluation_state'] == 'not_applicable'


def test_less_than_twenty_probes_does_not_get_document_score(scored_run):
    manager, directory, _, evaluation = scored_run
    evaluation.update(n_trajectories=3, n_successful=3)
    _write(directory / 'evaluation.json', evaluation)
    assert manager.snapshot(directory.name)['evaluation_state'] == 'unavailable'


@pytest.mark.parametrize('failures', [[{'stage': 'truth_reference'}], [{'stage': 'unknown'}], 'malformed'])
def test_contradictory_complete_flags_do_not_hide_evaluation_failures(scored_run, failures):
    manager, directory, _, evaluation = scored_run
    evaluation['failures'] = failures
    _write(directory / 'evaluation.json', evaluation)
    assert manager.snapshot(directory.name)['evaluation_state'] == 'error'


def test_adding_score_sidecar_does_not_change_history_date(scored_run):
    manager, directory, _, _ = scored_run
    before = manager.snapshot(directory.name)['created_at']
    _write(directory / 'evaluation_score.json', {'new': 'post-session artifact'})
    assert manager.snapshot(directory.name)['created_at'] == before
