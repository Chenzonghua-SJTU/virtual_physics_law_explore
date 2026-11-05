"""Deterministic benchmark-driver mocks; none of these is an Agent discovery."""
import copy
import json
from pathlib import Path

import httpx
import numpy as np
import pytest

from benchmark_worlds import (BenchmarkError, EVALUATION, LocalService, ROLE_LIMITS,
                              SETTINGS, run_benchmark, summarize_snapshot)
from evaluate import evaluate_run
from shore_worlds import WORLD_IDS, LEGACY_PHYSICS_VERSION


def project(tmp_path):
    root = tmp_path / 'project'
    (root / 'shore_agent/prompts').mkdir(parents=True)
    for prompt in ('main.txt',):
        (root / 'shore_agent/prompts' / prompt).write_text('MOCK ONLY: protocol prompt', encoding='utf-8')
    config = {'environment': {'world_id': 'world_1', 'noise': False, 'seed': 42, 'wall_seconds': 3600},
              'model': {'base_url': 'https://api.deepseek.com', **ROLE_LIMITS, **{
                  k: v for k, v in SETTINGS.items() if k not in ('seed', 'noise')}},
              'agent': {'max_no_action': 3}, 'numerics': {'max_nfev': 80}}
    (root / 'config.example.json').write_text(json.dumps(config))
    return root, config


class FakeService:
    base_url = 'http://127.0.0.1:8765'

    def __init__(self, root, config, *, active=None):
        self.root, self.config = root, config
        self.active, self.started = active, []
        self.polls = {}

    def bootstrap(self):
        return {'active_run_id': self.active}

    def listing(self):
        return {'active_run_id': self.active}

    def start(self, world_id):
        self.started.append(world_id)
        run_id = 'mock-benchmark-' + world_id
        config = copy.deepcopy(self.config)
        config['environment']['world_id'] = world_id
        path = self.root / 'runs' / run_id
        path.mkdir(parents=True)
        (path / 'config.json').write_text(json.dumps(config))
        self.polls[run_id] = 0
        return run_id

    def snapshot(self, run_id):
        self.polls[run_id] += 1
        world_id = run_id.removeprefix('mock-benchmark-')
        return {'id': run_id, 'world_id': world_id, 'running': self.polls[run_id] < 2,
                'status': 'running' if self.polls[run_id] < 2 else 'incomplete',
                'result': {'reason': 'mock_budget_exhausted'},
                'budget': {'energy_remaining': 91, 'wall_seconds_remaining': 3500},
                'model_usage': {'calls': 4, 'total_tokens': 123, 'roles': {'main': {'calls': 4}}},
                'records': {'submissions': [], 'laws': []}, 'evaluation': None}


def test_driver_schedules_each_world_once_and_retains_all_failures(tmp_path):
    root, config = project(tmp_path)
    service = FakeService(root, config)
    output = tmp_path / 'benchmark'
    summary = run_benchmark(service, output, project_root=root, sleep=lambda _: None)
    assert service.started == list(WORLD_IDS)
    assert summary['status'] == 'completed_all_attempts'
    assert summary['locally_submitted_count'] == summary['independently_evaluated_count'] == 0
    assert [row['status'] for row in summary['worlds']] == ['incomplete'] * len(WORLD_IDS)
    assert all(row['independent_rmse'] is None and row['energy_used'] == 9 for row in summary['worlds'])
    manifest = json.loads((output / 'manifest.json').read_text())
    assert manifest['settings'] == SETTINGS and manifest['evaluation'] == EVALUATION
    assert manifest['agent_architecture'] == 'single_agent'
    assert len(manifest['tool_names']) == 8 and 'summarize_data' not in manifest['tool_names']
    assert manifest['automatic_reruns'] is manifest['automatic_budget_expansion'] is False
    assert all(len(row['configuration_sha256']) == 64 for row in manifest['worlds'])
    assert set(manifest['prompt_sha256']) == {'main.txt'}
    assert all(len(value) == 64 for value in manifest['prompt_sha256'].values())
    assert all(row['analyst_calls'] == 0 and row['main_calls'] == row['calls'] for row in summary['worlds'])
    assert 'mock_budget_exhausted' in (output / 'comparison.md').read_text()


def test_driver_refuses_active_session_without_starting_or_stopping(tmp_path):
    root, config = project(tmp_path)
    service = FakeService(root, config, active='user-owned-run')
    with pytest.raises(BenchmarkError, match='active_run_exists'):
        run_benchmark(service, tmp_path / 'benchmark', project_root=root)
    assert not service.started and service.active == 'user-owned-run'


def test_driver_transport_uncertainty_never_repeats_post(tmp_path):
    root, config = project(tmp_path)
    service = FakeService(root, config)

    def failed_start(world_id):
        service.started.append(world_id)
        raise BenchmarkError('local_http_transport_failed_no_retry')

    service.start = failed_start
    output = tmp_path / 'benchmark'
    with pytest.raises(BenchmarkError, match='no_retry'):
        run_benchmark(service, output, project_root=root)
    assert service.started == ['world_1']
    assert json.loads((output / 'summary.json').read_text())['status'] == 'interrupted_no_automatic_retry'


@pytest.mark.parametrize('group,key,value', [
    ('model', 'max_calls', 24), ('model', 'main_max_calls', 20),
    ('agent', 'max_turns', 30), ('agent', 'max_rounds', 30),
])
def test_driver_rejects_stale_call_or_round_caps_before_start(tmp_path, group, key, value):
    root, config = project(tmp_path)
    config[group][key] = value
    (root / 'config.example.json').write_text(json.dumps(config))
    service = FakeService(root, config)
    with pytest.raises(BenchmarkError, match='limits_must_be_unlimited'):
        run_benchmark(service, tmp_path / 'benchmark', project_root=root)
    assert not service.started


def test_http_client_uses_session_token_and_never_retries_or_saves_key(tmp_path):
    requests = []

    def handle(request):
        requests.append(request)
        if request.url.path == '/api/bootstrap':
            return httpx.Response(200, json={'token': 'synthetic-csrf-token', 'api_key_configured': False})
        if request.method == 'POST':
            assert request.headers['X-Session-Token'] == 'synthetic-csrf-token'
            body = json.loads(request.content)
            assert body.pop('api_key') == 'synthetic-never-real-key'
            assert body == dict(SETTINGS, world_id='world_2')
            return httpx.Response(503, text='sensitive response body')
        raise AssertionError('Unexpected request')

    service = LocalService('http://127.0.0.1:8765', 'synthetic-never-real-key', transport=httpx.MockTransport(handle))
    service.bootstrap()
    with pytest.raises(BenchmarkError, match='local_http_status_503'):
        service.start('world_2')
    assert len(requests) == 2
    service.close()
    assert service.api_key is None and service.token is None


@pytest.mark.parametrize('url', ['https://example.com', 'http://example.com', 'http://127.0.0.1:8765/path',
                                 'http://secret@localhost:8765', 'http://localhost:8765/?key=secret'])
def test_benchmark_credentials_only_sent_to_loopback(url):
    with pytest.raises(BenchmarkError, match='loopback'):
        LocalService(url, 'synthetic-key')


def test_summary_requires_real_local_acceptance_and_complete_evaluation():
    snapshot = {'id': 'mock-run', 'status': 'submitted', 'result': {'reason': 'accepted'},
                'records': {'submissions': [{'status': 'accepted', 'session_ended': True, 'law_id': 'law_a'}],
                            'laws': [{'law_id': 'law_a', 'law_spec': {'ax': '0', 'ay': '0'}, 'fitted_parameters': {}}]},
                'evaluation': {'world_id': 'world_3', 'seed': 1871, 'n_trajectories': 20,
                               'complete': True, 'overall': {'position_rmse': 17., 'velocity_rmse': 12.}}}
    row = summarize_snapshot(snapshot, 'world_3', {}, 2.5)
    assert row['accepted_submission'] and row['independent_evaluation_complete']
    assert row['independent_rmse']['position_rmse'] == 17
    with pytest.raises(BenchmarkError, match='physics_version_mismatch'):
        summarize_snapshot(snapshot, 'world_3', {'environment': {'physics_version': 'v2'}}, 2.5)
    snapshot['evaluation']['physics_version'] = 'v2'
    assert summarize_snapshot(snapshot, 'world_3', {'environment': {'physics_version': 'v2'}}, 2.5)['physics_version'] == 'v2'
    snapshot['evaluation']['complete'] = False
    assert summarize_snapshot(snapshot, 'world_3', {}, 2.5)['independent_rmse'] is None
    snapshot['status'] = 'incomplete'
    assert not summarize_snapshot(snapshot, 'world_3', {}, 2.5)['accepted_submission']
    snapshot['evaluation']['world_id'] = 'world_4'
    with pytest.raises(BenchmarkError, match='identity_mismatch'):
        summarize_snapshot(snapshot, 'world_3', {}, 2.5)


def accepted_fixture(root, world_id=None, mission_world=None):
    (root / 'records/submission').mkdir(parents=True)
    (root / 'records/law').mkdir()
    submission = {'submission_id': 'mock_s', 'law_id': 'mock_l', 'status': 'accepted', 'session_ended': True,
                  'claims': {'dynamics_order': 2, 'hidden_matter': False, 'time_dependence': False}}
    law = {'law_id': 'mock_l', 'law_spec': {'ax': '0', 'ay': '0'}, 'fitted_parameters': {}, 'known_bodies': []}
    (root / 'records/submission/mock_s.json').write_text(json.dumps(submission))
    (root / 'records/law/mock_l.json').write_text(json.dumps(law))
    if world_id is not None:
        environment = {'world_id': world_id}
        if world_id in ('world_6', 'world_7'):
            environment['physics_version'] = 'v4'
        (root / 'config.json').write_text(json.dumps({'environment': environment}))
    if mission_world is not None:
        task = {'world_id': mission_world}
        if mission_world in ('world_6', 'world_7'):
            task['physics_version'] = 'v4'
        (root / 'mission.json').write_text(json.dumps({'task': task}))


@pytest.mark.parametrize('world_id', WORLD_IDS)
def test_independent_evaluator_selects_requested_world(tmp_path, monkeypatch, world_id):
    import shore_sim.simulator as simulator
    accepted_fixture(tmp_path, world_id, world_id)
    original = simulator.truth_trajectory
    calls = []

    def spy(r0, v0, times, **kwargs):
        calls.append(kwargs)
        return original(r0, v0, times, **kwargs)

    monkeypatch.setattr(simulator, 'truth_trajectory', spy)
    before = (tmp_path / 'records/law/mock_l.json').read_bytes()
    result = evaluate_run(tmp_path, n_probes=2)
    assert result['world_id'] == world_id and len(calls) == 2
    assert all(call['world_id'] == world_id and set(call['properties']) == {'mass', 'charge'} for call in calls)
    version = 'v4' if world_id in ('world_6', 'world_7') else LEGACY_PHYSICS_VERSION
    assert result['physics_version'] == version
    assert result['truth_reference'] == simulator.truth_reference(world_id, physics_version=version)
    assert result['complete'] and np.isfinite(result['overall']['position_rmse'])
    assert (tmp_path / 'records/law/mock_l.json').read_bytes() == before


def test_evaluator_refuses_identity_mismatch_before_oracle(tmp_path, monkeypatch):
    import shore_sim.simulator as simulator
    accepted_fixture(tmp_path, 'world_2', 'world_3')
    monkeypatch.setattr(simulator, 'truth_trajectory', lambda *a, **k: pytest.fail('Oracle must not run'))
    with pytest.raises(ValueError, match='identity mismatch'):
        evaluate_run(tmp_path, n_probes=1)


def test_legacy_archives_default_to_world_one(tmp_path):
    accepted_fixture(tmp_path)
    result = evaluate_run(tmp_path, n_probes=1)
    assert result['world_id'] == 'world_1'


def test_evaluator_reports_truth_failure_without_inventing_score(tmp_path, monkeypatch):
    import shore_sim.simulator as simulator
    accepted_fixture(tmp_path, 'world_4', 'world_4')

    def fail(*args, **kwargs):
        raise ValueError('oracle convergence failed')

    monkeypatch.setattr(simulator, 'truth_trajectory', fail)
    result = evaluate_run(tmp_path, n_probes=1)
    assert not result['complete'] and result['overall'] is None
    assert result['failures'][0]['stage'] == 'truth_reference'
