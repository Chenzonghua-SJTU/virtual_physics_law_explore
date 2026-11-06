"""Archive-only audit fixtures: no model, simulator, or evaluator is invoked."""
import json

import pytest

from deployment.audit_e4 import NO_NOISE_REFERENCE, WORLDS, audit, digest


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def update(path, **changes):
    value = json.loads(path.read_text())
    value.update(changes)
    write(path, value)


def jsonl(path, rows):
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')


def batch_fixture(root, ruleset='e5', scores=None):
    group, noisy = ruleset.upper(), ruleset == 'e4'
    batch = root / 'experiments' / group / 'synthetic-batch'
    source = root / 'synthetic-source.txt'
    source.write_text('Read-only archive fixture; no scientific answers.')
    mapping = {world: f'{ruleset}-synthetic-{world}' for world in WORLDS}
    write(batch / 'manifest.json', {'experiment_id': 'synthetic-batch', 'experiment_group': group,
                                  'ruleset': ruleset, 'runs': mapping,
                                  'source_sha256': {source.name: digest(source)}})
    scores = scores or [95.] * 6
    for world, score in zip(WORLDS, scores):
        directory = root / 'runs' / mapping[world]
        write(directory / 'config.json', {'environment': {
            'world_set': 'v15', 'world_id': world, 'ruleset': ruleset,
            'energy_budget': 10, 'wall_seconds': 300, 'noise': noisy},
            'model': {'ruleset': ruleset, 'model': 'synthetic', 'thinking': False,
                      'max_tokens_per_call': 4096}})
        write(directory / 'mission.json', {'task': {'world_id': world,
            'position_noise_sigma': .05 if noisy else 0., 'velocity_noise_sigma': .0003 if noisy else 0.,
            'limits': {'initial_energy': 10, 'wall_seconds': 300}}})
        write(directory / 'web.json', {'status': 'submitted',
            'created_at': '2026-11-07T00:00:00+00:00', 'worker_started_at': '2026-11-07T00:00:01+00:00',
            'exploration_deadline_at': '2026-11-07T00:05:01+00:00',
            'exploration_finished_at': '2026-11-07T00:01:41+00:00',
            'evaluation_started_at': '2026-11-07T00:01:42+00:00',
            'exploration_wall_seconds': 100., 'evaluation_wall_seconds': 2.,
            'wall_seconds_including_evaluation': 103.})
        claims = {'dynamics_order': 2, 'hidden_matter': False, 'time_dependence': False}
        selected = {'submission_id': 'submission_1', 'law_id': 'law_1', 'claims': claims,
                    'physical_explanation': 'Synthetic archive test.', 'status': 'accepted',
                    'session_ended': True, 'submission_deadline_met': True,
                    'pair_validated_at': '2026-11-07T00:01:40+00:00',
                    'pair_validated_elapsed_seconds': 99.}
        usage = {'calls': 1, 'prompt_tokens': 100, 'completion_tokens': 200, 'total_tokens': 300,
                 'elapsed_seconds': 80.}
        write(directory / 'result.json', {'status': 'submitted', 'submission': selected,
                                         'model_usage': usage, 'budget': {'energy_remaining': 0}})
        write(directory / 'records' / 'submission' / 'submission_1.json', selected)
        write(directory / 'records' / 'probe' / 'probe_1.json', {
            'initial_conditions': {'t0': 0., 'r0': [1., 2.], 'v0': [0., 1.]}, 'times': [0.],
            'r_obs': [[1.01 if noisy else 1., 2.]], 'v_obs': [[.0001 if noisy else 0., 1.]]})
        artifacts = directory / 'submissions' / 'submission_1'
        write(artifacts / 'claims.json', claims)
        write(artifacts / 'law.json', {'law_id': 'law_1'})
        (artifacts / 'law.py').write_text('# Never executed by archive auditor.\n')
        (artifacts / 'physical_explanation.txt').write_text(selected['physical_explanation'])
        arguments = {key: selected[key] for key in ('law_id', 'claims', 'physical_explanation')}
        jsonl(directory / 'events.jsonl', [
            {'event': 'tool_started', 'name': 'submit', 'tool_call_id': 'call-1', 'arguments': arguments},
            {'event': 'tool_finished', 'tool_call_id': 'call-1'}])
        jsonl(directory / 'tools.jsonl', [{'tool': 'submit', 'elapsed_seconds': 1., 'result': {'ok': True}}])
        reasoning = {'chat_template_kwargs': {'enable_thinking': False}}
        jsonl(directory / 'model_events.jsonl', [
            {'event': 'configuration', 'thinking': False, 'deployment': 'local', 'max_tokens_per_call': 4096},
            {'event': 'request_started', 'call_number': 1, 'started_at': '2026-11-07T00:00:02+00:00',
             'max_tokens': 4096, 'reasoning_parameters': reasoning},
            {'event': 'request', 'call_number': 1, 'max_tokens': 4096, 'reasoning_parameters': reasoning,
             'elapsed_seconds': 80., 'usage': {key: usage[key] for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')}}])
        count = 32 if world == 'world_6' else 24
        write(directory / 'evaluation.json', {'submission_id': 'submission_1', 'law_id': 'law_1',
            'world_id': world, 'world_set': 'v15', 'ruleset': ruleset, 'complete': True,
            'n_trajectories': count, 'n_successful': count, 'failures': [],
            'truth_reference': NO_NOISE_REFERENCE,
            'score': {'status': 'scored', 'total': score, 'energy_budget': 10}})
    return batch, [root / 'runs' / mapping[world] for world in WORLDS]


@pytest.mark.parametrize('ruleset', ['e4', 'e5'])
def test_profile_preserves_noise_semantics_and_reports_success_separately(tmp_path, ruleset):
    batch, directories = batch_fixture(tmp_path, ruleset)
    original = {path: path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}
    result = audit(tmp_path, batch)
    assert result['errors'] == []
    assert result['experiment_group'] == ruleset.upper()
    assert result['submitted_worlds'] == result['evaluated_worlds'] == 6
    assert result['worlds_at_or_above_90'] == 6 and result['five_world_target_met'] is True
    assert result['aggregate']['average_output_tokens_per_call'] == 200
    assert result['aggregate']['total_seconds_including_evaluation']['sum'] == 618
    assert all(row['evaluation']['checks']['no_noise_truth_reference'] for row in result['worlds'])
    assert {path: path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()} == original


def test_six_submissions_are_not_six_high_scores_and_no_rounding(tmp_path):
    batch, _ = batch_fixture(tmp_path, scores=[95, 93, 92, 90, 89.999999, 20])
    result = audit(tmp_path, batch)
    assert result['errors'] == [] and result['submitted_worlds'] == 6
    assert result['worlds_at_or_above_90'] == 4
    assert result['five_world_target_met'] is False


@pytest.mark.parametrize('ruleset', ['e4', 'e5'])
def test_evaluation_noise_is_forbidden_regardless_of_exploration_noise(tmp_path, ruleset):
    batch, directories = batch_fixture(tmp_path, ruleset)
    update(directories[0] / 'evaluation.json', truth_reference='noisy observations')
    result = audit(tmp_path, batch)
    assert 'world_1:evaluation:no_noise_truth_reference' in result['errors']
    assert result['worlds_at_or_above_90'] == 5
    assert result['five_world_target_met'] is False


def test_e5_requires_noiseless_observations_not_just_a_config_flag(tmp_path):
    batch, directories = batch_fixture(tmp_path)
    update(directories[0] / 'records' / 'probe' / 'probe_1.json', v_obs=[[.003, 1.]])
    result = audit(tmp_path, batch)
    assert 'world_1:noiseless_t0_readout_differs_from_launch:velocity' in result['errors']
    assert result['five_world_target_met'] is False


def test_high_scores_do_not_hide_late_submission_or_excess_output(tmp_path):
    batch, directories = batch_fixture(tmp_path)
    update(directories[0] / 'records' / 'submission' / 'submission_1.json', pair_validated_elapsed_seconds=301.)
    path = directories[1] / 'model_events.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[-1]['usage'].update(completion_tokens=4097, total_tokens=4197)
    jsonl(path, rows)
    result = audit(tmp_path, batch)
    assert 'world_1:accepted_pair_not_verified_before_deadline' in result['errors']
    assert 'world_2:call_1:reported_output_above_4096' in result['errors']
    assert result['aggregate']['calls_above_4096'] == 1
    assert result['five_world_target_met'] is False


def test_manifest_cannot_relabel_e4_as_e5(tmp_path):
    batch, _ = batch_fixture(tmp_path, 'e4')
    update(batch / 'manifest.json', experiment_group='E5')
    result = audit(tmp_path, batch)
    assert result['experiment_group'] == 'E4'
    assert 'manifest_experiment_group_ruleset_mismatch' in result['errors']


def test_unknown_profile_is_reported_without_applying_e4_defaults(tmp_path):
    batch, _ = batch_fixture(tmp_path)
    update(batch / 'manifest.json', ruleset='unknown')
    result = audit(tmp_path, batch)
    assert 'unsupported_manifest_ruleset' in result['errors']
    assert result['experiment_group'] is None
    assert result['worlds'] == [] and result['five_world_target_met'] is False
