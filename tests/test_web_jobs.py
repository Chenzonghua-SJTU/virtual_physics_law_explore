"""Web lifecycle/security checks. No paid API calls or claimed discoveries."""
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest

from shore_agent import web_jobs, web_worker
from shore_agent.web_jobs import RunManager, ValidationError, ConflictError, _write
from shore_worlds import DEFAULT_WORLD_ID, WORLD_IDS, world_name

PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture
def manager(tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'config.example.json').write_text((PROJECT / 'config.example.json').read_text())
    value = RunManager(project)
    yield value
    value.close()


class Input:
    def __init__(self):
        self.text = ''
        self.closed = False

    def write(self, value):
        self.text += value

    def flush(self):
        pass

    def close(self):
        self.closed = True


class Process:
    pid = 987654321  # Always mocked killpg; never signal an unrelated process.

    def __init__(self):
        self.stdin = Input()
        self.returncode = None

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0
        return 0


@pytest.fixture
def launch(monkeypatch):
    calls = []
    signals = []

    def popen(argv, **kwargs):
        process = Process()
        calls.append((argv, kwargs, process))
        return process

    monkeypatch.setattr(web_jobs.subprocess, 'Popen', popen)
    monkeypatch.setattr('shore_agent.code_execution.sandbox_info', lambda *_: {'available': False, 'reason': 'test environment'})
    monkeypatch.setattr(web_jobs.os, 'killpg', lambda pid, sig: signals.append((pid, sig)))
    return calls, signals


def test_launch_is_isolated_key_only_in_stdin_and_safe_config(manager, launch, monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'server-env-key')
    run_id = manager.start({'api_key': 'sk-testcredential12345', 'max_calls': 2, 'noise': True, 'seed': 7})
    argv, options, process = launch[0][0]
    assert options['start_new_session'] is True
    assert 'DEEPSEEK_API_KEY' not in options['env']
    assert options['stdout'] == subprocess.DEVNULL
    assert options['stderr'] == subprocess.DEVNULL
    assert 'sk-testcredential12345' not in str(argv)
    assert json.loads(process.stdin.text) == {'api_key': 'sk-testcredential12345'}
    assert process.stdin.closed
    directory = manager.runs_dir / run_id
    config = json.loads((directory / 'config.json').read_text())
    assert config['model']['max_calls'] is None
    assert config['model']['main_max_calls'] is None
    assert 'max_turns' not in config.get('agent', {})
    assert 'max_rounds' not in config.get('agent', {})
    assert manager.snapshot(run_id)['limits']['max_calls'] is None
    assert not any(key.startswith('analyst_') for key in config['model'])
    assert config['environment']['noise'] is True
    assert config['environment']['world_id'] == DEFAULT_WORLD_ID
    assert manager.snapshot(run_id)['world_id'] == DEFAULT_WORLD_ID
    assert manager.snapshot(run_id)['world_name'] == '世界 01'
    assert all('sk-testcredential12345' not in file.read_text() for file in directory.iterdir())
    assert os.environ['DEEPSEEK_API_KEY'] == 'server-env-key'
    assert manager.list_runs()['active_run_id'] == run_id
    with pytest.raises(RuntimeError, match='run_already_active'):
        manager.start({'api_key': 'different'})
    manager.stop(run_id)
    assert manager.snapshot(run_id)['status'] == 'stopped'
    assert manager.snapshot(run_id)['result']['submission'] is None
    assert launch[1] == [(process.pid, signal.SIGTERM), (process.pid, signal.SIGKILL)]
    second = manager.start({})
    assert second != run_id
    assert json.loads(launch[0][1][2].stdin.text)['api_key'] == 'server-env-key'


@pytest.mark.parametrize('legacy_limit', [None, 1, 24, 61, 0, 2.5])
def test_new_web_configuration_ignores_retired_count_and_turn_caps(manager, legacy_limit):
    path = manager.project_root / 'config.example.json'
    old_config = json.loads(path.read_text())
    old_config['model'].update(max_calls=3, main_max_calls=2)
    old_config.setdefault('agent', {}).update(max_turns=4, max_rounds=5)
    _write(path, old_config)
    original = path.read_bytes()
    config, _ = manager._config({'api_key': 'test-key', 'max_calls': legacy_limit})
    assert config['model']['max_calls'] is None
    assert config['model']['main_max_calls'] is None
    assert 'max_turns' not in config['agent'] and 'max_rounds' not in config['agent']
    assert config['model']['max_total_tokens'] == old_config['model']['max_total_tokens']
    assert config['environment']['wall_seconds'] == old_config['environment']['wall_seconds']
    assert path.read_bytes() == original


def test_archived_call_limit_and_failure_remain_visible_without_rewriting(manager):
    directory = manager.runs_dir / 'old-call-limit'
    directory.mkdir()
    _write(directory / 'config.json', {'model': {'max_calls': 24, 'main_max_calls': 24}})
    _write(directory / 'result.json', {'status': 'incomplete', 'reason': 'model_call_budget_exhausted',
                                      'model_usage': {'calls': 24}})
    originals = {path.name: path.read_bytes() for path in directory.iterdir()}
    snapshot = manager.snapshot(directory.name)
    assert snapshot['limits']['max_calls'] == 24
    assert snapshot['model_usage']['calls'] == 24
    assert snapshot['result']['reason'] == 'model_call_budget_exhausted'
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == originals


@pytest.mark.parametrize('ruleset', ['e4', 'e5'])
def test_e4_backend_bootstrap_and_payload_cannot_expand_rules(manager, ruleset):
    override = manager.project_root / 'e4.json'
    source = json.loads((PROJECT / 'config.e4.example.json').read_text())
    source['environment']['ruleset'] = ruleset
    _write(override, source)
    manager.config_path = override
    settings = manager.client_configuration()
    assert settings['defaults']['ruleset'] == ruleset
    assert settings['defaults']['energy_budget'] == 10
    assert settings['defaults']['wall_seconds'] == 300
    assert settings['max_output_tokens_cap'] == 4096
    assert all(item['max_output_tokens'] == 4096 for item in settings['models'])
    for payload, code in [({'max_tokens_per_call': 65536}, 'invalid_output_budget'),
                          ({'thinking': True}, ruleset + '_requires_no_thinking'),
                          ({'noise': ruleset != 'e4'}, 'e4_requires_noise' if ruleset == 'e4' else 'e5_requires_no_noise'),
                          ({'world_set': 'legacy'}, ruleset + '_requires_v15')]:
        with pytest.raises(ValidationError, match=code):
            manager._config(payload)
    config, key = manager._config({'max_tokens_per_call': 2048})
    assert config['environment']['energy_budget'] == 10
    assert config['model']['max_tokens_per_call'] == 2048
    assert config['model']['thinking'] is False and not key


@pytest.mark.parametrize('ruleset', ['e4', 'e5'])
def test_history_keeps_its_own_energy_limit_under_e4_server(manager, ruleset):
    override = manager.project_root / 'e4.json'
    source = json.loads((PROJECT / 'config.e4.example.json').read_text())
    source['environment']['ruleset'] = ruleset
    _write(override, source)
    manager.config_path = override
    for name, ruleset, energy in [('old', 'e3', 100), ('new', 'e4', 10), ('clean', 'e5', 10)]:
        directory = manager.runs_dir / name
        directory.mkdir()
        environment = {'world_set': 'v15', 'physics_version': 'shore_v15'}
        if ruleset in ('e4', 'e5'):
            environment['ruleset'] = ruleset
        _write(directory / 'config.json', {'environment': environment})
        _write(directory / 'mission.json', {'task': {'limits': {'initial_energy': energy}}})
        _write(directory / 'result.json', {'status': 'incomplete', 'budget': {'energy_remaining': energy - 2}})
        before = {p.name: p.read_bytes() for p in directory.iterdir()}
        snapshot = manager.snapshot(name)
        assert (snapshot['ruleset'], snapshot['energy_budget']) == (ruleset, energy)
        assert {p.name: p.read_bytes() for p in directory.iterdir()} == before


@pytest.mark.parametrize('ruleset', ['e3', 'e4', 'e5'])
def test_reusing_strict_template_does_not_leak_e5_flags_into_older_profiles(manager, ruleset):
    from shore_agent.agent import Agent
    from shore_agent.model import DeepSeekClient
    from shore_agent.runtime import ToolRuntime

    source = json.loads((PROJECT / 'deployment/config.e5.strict.json').read_text())
    source['numerics'].update(diagnostics_candidates=True, diagnostics_quadrature='hermite_simpson',
                              diagnostics_harmonic=True, diagnostics_on_fit=True)
    # Exercise a trusted profile change while the remaining strict template is
    # inherited. Browser payloads still cannot change the server's ruleset.
    source['environment']['ruleset'] = ruleset
    if ruleset == 'e3':
        source['environment'].update(energy_budget=100, wall_seconds=3600)
        source['model'].update(thinking=True, max_tokens_per_call=8192)
    path = manager.project_root / 'strict-profile.json'
    _write(path, source)
    original = path.read_bytes()
    manager.config_path = path
    config, key = manager._config({'world_set': 'v15'})
    assert not key and path.read_bytes() == original
    assert config['numerics']['max_nfev'] == 80
    assert config['model']['sampling_seed'] == 42
    assert config['model']['base_url'] == source['model']['base_url']
    assert config['agent']['guidance_profile'] == 'e3'
    run_dir = manager.runs_dir / ('construct-' + ruleset)
    client = DeepSeekClient(config['model'], run_dir, remaining_seconds=lambda: 300)
    try:
        environment = type('NoRequestEnvironment', (), {'ruleset': ruleset})()
        runtime = ToolRuntime(environment, run_dir, config=config['numerics'])
        agent = Agent(client, runtime, run_dir, config['agent'])
        assert client.strict_tools is (ruleset == 'e5')
        assert agent.strict_tool_recovery is (ruleset == 'e5')
        assert agent.budget_aware_tools is (ruleset == 'e5')
        assert runtime.diagnostics_enabled is (ruleset == 'e5')
        if ruleset != 'e5':
            assert 'strict_tools' not in config['model']
            assert not ({'strict_tool_recovery', 'budget_aware_tools', 'repeated_tool_failure_feedback'} & set(config['agent']))
            assert not ({'diagnostics_enabled', 'diagnostics_compact', 'diagnostics_curvature',
                         'diagnostics_candidates', 'diagnostics_quadrature', 'diagnostics_harmonic',
                         'diagnostics_on_fit'} & set(config['numerics']))
            assert 'diagnose_dynamics' not in [s['function']['name'] for s in runtime.schemas]
        if ruleset == 'e3':
            assert config['model'].get('ruleset', 'e3') == 'e3'
            assert client.max_tokens_per_call == 8192 and client.thinking is True
            assert config['environment']['energy_budget'] == 100 and config['environment']['wall_seconds'] == 3600
        else:
            assert config['model']['ruleset'] == ruleset
            assert client.max_tokens_per_call == 4096 and client.thinking is False
            assert config['environment']['noise'] is (ruleset == 'e4')
    finally:
        client.close()
    assert path.read_bytes() == original


def test_strict_web_default_preserves_history_and_does_not_add_profile_payload_switch(manager):
    path = manager.project_root / 'strict-profile.json'
    _write(path, json.loads((PROJECT / 'deployment/config.e5.strict.json').read_text()))
    manager.config_path = path
    for payload in ({'ruleset': 'e3'}, {'strict_tools': False}):
        with pytest.raises(ValidationError, match='invalid_run_configuration'):
            manager._config(payload)
    with pytest.raises(ValidationError, match='e5_requires_v15'):
        manager._config({'world_set': 'legacy'})
    for ruleset, energy in [('e3', 100), ('e4', 10)]:
        directory = manager.runs_dir / ('historical-' + ruleset)
        directory.mkdir()
        _write(directory / 'config.json', {'environment': {'ruleset': ruleset, 'world_set': 'v15',
                                                          'physics_version': 'shore_v15'},
                                          'model': {'model': 'historical-model'}})
        _write(directory / 'mission.json', {'task': {'limits': {'initial_energy': energy}}})
        _write(directory / 'result.json', {'status': 'incomplete', 'budget': {'energy_remaining': energy - 2}})
        before = {p.name: p.read_bytes() for p in directory.iterdir()}
        snapshot = manager.snapshot(directory.name)
        assert snapshot['ruleset'] == ruleset and snapshot['energy_budget'] == energy
        assert {p.name: p.read_bytes() for p in directory.iterdir()} == before


def test_stream_progress_projects_only_counters_and_advances_wait_time(manager, launch):
    run_id = manager.start({'api_key': 'test-only'})
    directory = manager.runs_dir / run_id
    now = datetime.now(timezone.utc)
    _write(directory / 'model_progress.json', {
        'schema_version': 1, 'status': 'running', 'phase': 'thinking', 'call_number': 1,
        'started_at': (now - timedelta(seconds=30)).isoformat(),
        'updated_at': (now - timedelta(seconds=2)).isoformat(),
        'last_received_at': (now - timedelta(seconds=3)).isoformat(),
        'elapsed_seconds': 28, 'received_characters': 420, 'received_chunks': 12,
        'reasoning_characters': 420, 'content_characters': -1, 'tool_call_characters': True,
        'reasoning_content': 'private model text', 'unexpected_text': 'private arbitrary field',
        'model': 'private model field', 'error': 'private error text'})
    progress = manager.snapshot(run_id)['model_progress']
    assert progress['active'] is True and progress['phase'] == 'thinking'
    assert 30 <= progress['elapsed_seconds'] < 40
    assert 3 <= progress['seconds_since_last_received'] < 10
    assert progress['received_characters'] == 420
    assert progress['received_chunks'] == 12
    assert 'content_characters' not in progress and 'tool_call_characters' not in progress
    assert 'private' not in json.dumps(progress)
    assert 'model' not in progress and 'error' not in progress
    manager.stop(run_id)
    assert manager.snapshot(run_id)['model_progress']['active'] is False


def test_progress_does_not_follow_symlink_or_publish_unrecognized_phase(manager, tmp_path):
    directory = manager.runs_dir / 'progress-history'
    directory.mkdir()
    _write(directory / 'result.json', {'status': 'incomplete'})
    _write(directory / 'model_progress.json', {'schema_version': 1, 'status': 'running', 'phase': 'private text'})
    assert manager.snapshot(directory.name)['model_progress'] is None
    (directory / 'model_progress.json').unlink()
    target = tmp_path / 'outside-progress.json'
    _write(target, {'schema_version': 1, 'status': 'running', 'phase': 'thinking'})
    (directory / 'model_progress.json').symlink_to(target)
    assert manager.snapshot(directory.name)['model_progress'] is None


def test_external_runner_is_visible_but_cannot_be_stopped_or_deleted(manager, monkeypatch):
    directory = manager.runs_dir / 'external-baseline'
    directory.mkdir()
    _write(directory / 'web.json', {'status': 'running', 'runner_owned': True, 'worker_pid': 12345})
    signals = []
    monkeypatch.setattr(web_jobs.os, 'kill', lambda pid, sig: signals.append((pid, sig)))
    monkeypatch.setattr(web_jobs.subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(
        a[0], 0, stdout=f'python -m shore_agent.web_worker --run-dir {directory}', stderr=''))
    snapshot = manager.snapshot(directory.name)
    assert snapshot['status'] == 'running' and snapshot['running'] is True
    assert snapshot['managed_externally'] is True and snapshot['can_stop'] is False
    listing = manager.list_runs()
    assert listing['active_run_id'] is None and listing['runs'][0]['running'] is True
    with pytest.raises(ConflictError, match='run_managed_externally'):
        manager.stop(directory.name)
    with pytest.raises(ConflictError, match='run_is_active'):
        manager.delete(directory.name)
    assert all(pid == 12345 and sig == 0 for pid, sig in signals)
    assert directory.is_dir()
    monkeypatch.setattr(web_jobs.subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(
        a[0], 0, stdout='python -m another_process --run-dir /tmp/unrelated', stderr=''))
    assert manager.snapshot(directory.name)['status'] == 'interrupted'
    assert manager.snapshot(directory.name)['running'] is False


@pytest.mark.parametrize('payload,code', [
    ({'base_url': 'https://example.com'}, 'invalid_run_configuration'),
    ({'run_dir': '/tmp'}, 'invalid_run_configuration'),
    ({'command': 'anything'}, 'invalid_run_configuration'),
    ({'model': 'unsupported'}, 'invalid_model'),
    ({'model': 'deepseek-pro'}, 'invalid_model'),
    ({'reasoning_effort': 'medium'}, 'invalid_reasoning_effort'),
    ({'reasoning_effort': 'invalid'}, 'invalid_reasoning_effort'),
    ({'reasoning_effort': None}, 'invalid_reasoning_effort'),
    ({'reasoning_effort': []}, 'invalid_reasoning_effort'),
    ({'reasoning_protocol': 'chat_template'}, 'invalid_run_configuration'),
    ({'api_key_required': False}, 'invalid_run_configuration'),
    ({'noise': 1}, 'invalid_run_configuration'),
    ({'thinking': 'yes'}, 'invalid_run_configuration'),
    ({'world_id': None}, 'invalid_world_id'),
    ({'world_id': True}, 'invalid_world_id'),
    ({'world_id': 1}, 'invalid_world_id'),
    ({'world_id': []}, 'invalid_world_id'),
    ({'world_id': {}}, 'invalid_world_id'),
    ({'world_id': 'world_0'}, 'invalid_world_id'),
    ({'world_id': 'world_8'}, 'invalid_world_id'),
    ({'world_id': 'world_1 '}, 'invalid_world_id'),
    ({'world_id': '../world_1'}, 'invalid_world_id'),
    ({'seed': True}, 'invalid_seed'),
    ({'seed': -1}, 'invalid_seed'),
    ({'seed': 2**31}, 'invalid_seed'),
    ({'max_total_tokens': float('inf')}, 'invalid_budget'),
    ({'max_total_tokens': 999}, 'invalid_budget'),
    ({'max_total_tokens': 10000001}, 'invalid_budget'),
        ({'max_tokens_per_call': True}, 'invalid_output_budget'),
    ({'max_tokens_per_call': 63}, 'invalid_output_budget'),
    ({'max_tokens_per_call': 393217}, 'invalid_output_budget'),
    ({'max_tokens_per_call': 65536.5}, 'invalid_output_budget'),
    ({'api_key': 'key\nheader'}, 'invalid_api_key'),
    ({'api_key': 123}, 'invalid_api_key'),
    ({'api_key': 'x' * 513}, 'invalid_api_key'),
])
def test_strict_bounded_payload(manager, monkeypatch, payload, code):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-only')
    with pytest.raises(ValidationError) as exc:
        manager.start(payload)
    assert exc.value.code == code
    assert not list(manager.runs_dir.iterdir())


def test_missing_key_rejected_without_creating_run(manager, monkeypatch):
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    with pytest.raises(ValidationError, match='missing_api_key'):
        manager.start({})
    assert not list(manager.runs_dir.iterdir())


@pytest.mark.parametrize('world_id', WORLD_IDS)
def test_selected_world_survives_launch_history_delete_and_restore(manager, launch, world_id):
    baseline = json.loads((manager.project_root / 'config.example.json').read_text())
    run_id = manager.start({'api_key': 'mock-only-world-selection', 'world_id': world_id})
    directory = manager.runs_dir / run_id
    configuration = json.loads((directory / 'config.json').read_text())
    baseline['environment']['world_id'] = world_id
    assert configuration == baseline  # Selecting a world changes no other experiment setting.
    metadata = json.loads((directory / 'web.json').read_text())
    assert metadata['world_id'] == world_id
    assert metadata['world_name'] == world_name(world_id)
    snapshot = manager.snapshot(run_id)
    listing = manager.list_runs()['runs'][0]
    for projection in (snapshot, listing):
        assert projection['world_id'] == world_id
        assert projection['world_name'] == world_name(world_id)
    manager.stop(run_id)
    original = tree_bytes(directory)
    manager.delete(run_id)
    deleted = manager.list_runs()['deleted_runs'][0]
    assert deleted['world_id'] == world_id
    assert deleted['world_name'] == world_name(world_id)
    manager.restore(run_id)
    assert tree_bytes(directory) == original
    assert manager.snapshot(run_id)['world_id'] == world_id
    assert manager.list_runs()['runs'][0]['world_name'] == world_name(world_id)


def test_archive_world_projection_uses_actual_configuration_and_neutral_names(manager):
    directory = historical_run(manager, 'world-archive')
    _write(directory / 'config.json', {'environment': {'world_id': 'world_4'}})
    manager._update_metadata(directory, world_id='world_2', world_name='Do not expose this old description',
                             evaluation_status='completed', finished_at='2026-11-02T01:00:00+00:00')
    snapshot = manager.snapshot(directory.name)
    assert snapshot['world_id'] == 'world_4'
    assert snapshot['world_name'] == '世界 04'
    assert snapshot['evaluation_status'] == 'completed'
    assert snapshot['finished_at'] == '2026-11-02T01:00:00+00:00'
    manager.delete(directory.name)
    deleted = manager.list_runs()['deleted_runs'][0]
    assert deleted['world_id'] == 'world_4'
    assert deleted['world_name'] == '世界 04'


def test_legacy_archive_defaults_to_world_one_even_in_older_trash(manager):
    directory = historical_run(manager, 'legacy-world')
    assert manager.snapshot(directory.name)['world_id'] == DEFAULT_WORLD_ID
    assert manager.list_runs()['runs'][0]['world_name'] == '世界 01'
    manager.delete(directory.name)
    bookkeeping = manager.runs_dir / '.trash' / '.metadata' / (directory.name + '.json')
    data = json.loads(bookkeeping.read_text())
    data.pop('world_id'); data.pop('world_name')
    _write(bookkeeping, data)
    deleted = manager.list_runs()['deleted_runs'][0]
    assert deleted['world_id'] == DEFAULT_WORLD_ID
    assert deleted['world_name'] == '世界 01'
    manager.restore(directory.name)
    assert manager.snapshot(directory.name)['world_id'] == DEFAULT_WORLD_ID


@pytest.mark.parametrize('world_id', WORLD_IDS[:6])
def test_v15_selection_preserves_agent_config_and_archive_identity(manager, launch, world_id):
    baseline = json.loads((manager.project_root / 'config.example.json').read_text())
    run_id = manager.start({'api_key': 'mock-only', 'world_set': 'v15', 'world_id': world_id})
    directory = manager.runs_dir / run_id
    config = json.loads((directory / 'config.json').read_text())
    for section in ('model', 'agent', 'numerics', 'code_execution'):
        assert config[section] == baseline[section]
    assert config['environment']['world_set'] == 'v15'
    assert config['environment']['physics_version'] == 'shore_v15'
    assert config['environment']['wall_seconds'] == baseline['environment']['wall_seconds']
    assert manager.snapshot(run_id)['world_set'] == 'v15'
    assert manager.list_runs()['runs'][0]['world_set'] == 'v15'
    manager.stop(run_id)
    manager.delete(run_id)
    assert manager.list_runs()['deleted_runs'][0]['world_set'] == 'v15'
    manager.restore(run_id)
    assert manager.snapshot(run_id)['world_set'] == 'v15'


@pytest.mark.parametrize('payload,code', [
    ({'world_set': 'v15', 'world_id': 'world_7'}, 'invalid_world_id'),
    ({'world_set': 'unknown'}, 'invalid_world_set'),
    ({'world_set': None}, 'invalid_world_set'),
])
def test_invalid_world_set_selection_is_rejected_before_launch(manager, launch, payload, code):
    with pytest.raises(ValidationError, match=code):
        manager.start(dict(payload, api_key='mock-only'))
    assert launch[0] == []
    assert list(manager.runs_dir.iterdir()) == []


def test_legacy_archives_keep_legacy_identity_with_new_frontend_default(manager):
    directory = historical_run(manager, 'old-identity')
    assert manager.client_configuration()['defaults']['world_set'] == 'v15'
    assert manager.snapshot(directory.name)['world_set'] == 'legacy'


def test_stop_after_acceptance_preserves_real_submission(manager, launch):
    run_id = manager.start({'api_key': 'test-key'})
    directory = manager.runs_dir / run_id
    folder = directory / 'records' / 'submission'
    folder.mkdir(parents=True)
    accepted = {'submission_id': 's1', 'law_id': 'l1', 'status': 'accepted', 'session_ended': True}
    _write(folder / 's1.json', accepted)
    snapshot = manager.stop(run_id)
    assert snapshot['status'] == 'submitted'
    assert snapshot['result']['submission'] == accepted
    assert snapshot['result']['reason'] == 'accepted_before_stop'
    assert snapshot['evaluation'] is None
    assert not snapshot['running']
    assert manager.stop(run_id)['result'] == snapshot['result']


def test_stopping_finished_result_is_noop_and_close_stops_only_owned(manager, launch):
    existing = manager.runs_dir / 'existing'
    existing.mkdir()
    _write(existing / 'result.json', {'status': 'incomplete', 'reason': 'old'})
    assert manager.stop('existing')['result']['reason'] == 'old'
    assert launch[1] == []
    run_id = manager.start({'api_key': 'test-key'})
    manager.close()
    assert manager.snapshot(run_id)['status'] == 'stopped'
    assert manager.snapshot('existing')['result']['reason'] == 'old'
    with pytest.raises(RuntimeError, match='manager_closed'):
        manager.start({'api_key': 'test-key'})


def test_completed_worker_and_abnormal_exit_are_reaped(manager, launch):
    run_id = manager.start({'api_key': 'test-key'})
    directory = manager.runs_dir / run_id
    _write(directory / 'result.json', {'status': 'incomplete', 'reason': 'model_call_budget_exhausted'})
    launch[0][0][2].returncode = 0
    assert manager.snapshot(run_id)['status'] == 'incomplete'
    assert not manager.list_runs()['active_run_id']
    next_id = manager.start({'api_key': 'test-key'})
    launch[0][1][2].returncode = -9
    assert manager.snapshot(next_id)['status'] == 'error'
    assert not manager.list_runs()['active_run_id']


def test_snapshot_projects_public_scientific_data_only(manager):
    directory = manager.runs_dir / 'history'
    directory.mkdir()
    _write(directory / 'result.json', {'status': 'submitted', 'budget': {'energy_remaining': 96}})
    _write(directory / 'mission.json', {'task': {'visible_bodies': [{'body_id': 'b1', 'position': [1, 2]}]}})
    (directory / 'events.jsonl').write_text('\n'.join(json.dumps(item) for item in [
        {'event': 'research_progress', 'content': 'Public explanation sk-secretvalue123', 'reasoning_content': 'hidden thinking'},
        {'event': 'tool_started', 'name': 'fit_law_and_rollout', 'arguments': {'api_key': 'different-secret', 'law_spec': {'ax': 'k*x', 'ay': 'k*y'}}},
        {'event': 'tool_finished', 'name': 'fit_law_and_rollout', 'result': {'ok': True, 'data': {'law_id': 'l1'}, 'budget': {'energy_remaining': 99}}},
    ]) + '\n{"partial":')
    (directory / 'model_events.jsonl').write_text(json.dumps({'event': 'request', 'role': 'main', 'budget_usage': {'calls': 3, 'total_tokens': 100}}))
    (directory / 'model_messages.jsonl').write_text('NEVER EXPOSE RAW HISTORY')
    (directory / 'messages.json').write_text('NEVER EXPOSE REASONING')
    folder = directory / 'records' / 'law'
    folder.mkdir(parents=True)
    _write(folder / 'l1.json', {'law_id': 'l1', 'law_spec': {'ax': 'k*x'}, 'reasoning_content': 'private', 'headers': {'Authorization': 'Bearer something'}})
    snapshot = manager.snapshot('history')
    encoded = json.dumps(snapshot)
    assert all(secret not in encoded for secret in ['secretvalue123', 'different-secret', 'hidden thinking', 'NEVER EXPOSE', 'reasoning_content', 'Authorization'])
    assert snapshot['mode'] == 'autonomous_discovery'
    assert snapshot['budget']['energy_remaining'] == 96
    assert snapshot['model_usage']['calls'] == 3
    assert snapshot['bodies'][0]['position'] == [1, 2]
    assert snapshot['body_position_source'] == 'legacy_public_coordinates'
    assert snapshot['body_position_estimate'] is None
    assert [event['seq'] for event in snapshot['events']] == [1, 2, 3]
    assert snapshot['records']['laws'][0]['law_spec'] == {'ax': 'k*x'}


def test_snapshot_uses_acquired_positions_and_preserves_law_snapshot(manager):
    directory = manager.runs_dir / 'observed-bodies'
    folder = directory / 'records' / 'body_observation'
    folder.mkdir(parents=True)
    first = {'observation_id': 'body_0001', 'body_ids': ['b1'], 'times': [0, 1],
             'positions_obs': [[[2, 4]], [[4, 6]]]}
    second = {'observation_id': 'body_0002', 'body_ids': ['b1'], 'times': [2],
              'positions_obs': [[[9, 11]]]}
    # An old accurate coordinate must not override acquired noisy measurements.
    _write(directory / 'mission.json', {'task': {'position_noise_sigma': 0.1,
            'visible_bodies': [{'body_id': 'b1', 'position': [999, 999]}]},
            'first_light': {'body_observation': first}})
    _write(folder / 'body_0001.json', first)
    _write(folder / 'body_0002.json', second)
    law_folder = directory / 'records' / 'law'
    law_folder.mkdir()
    frozen = {'version': 'body_estimate_1', 'observation_ids': ['body_0001'],
              'bodies': [{'body_id': 'b1', 'position': [3, 5]}]}
    _write(law_folder / 'law_1.json', {'law_id': 'law_1', 'body_position_estimate': frozen,
                                    'known_bodies': frozen['bodies']})
    snapshot = manager.snapshot(directory.name)
    assert snapshot['body_position_source'] == 'observed_estimate'
    assert snapshot['bodies'][0]['position'] == [5, 7]
    assert snapshot['bodies'][0]['sample_count'] == 3  # first-light counted once
    assert snapshot['body_position_estimate']['observation_ids'] == ['body_0001', 'body_0002']
    assert snapshot['body_position_estimate']['version'] == 'body_estimate_2'
    assert snapshot['records']['laws'][0]['body_position_estimate'] == frozen
    assert snapshot['records']['laws'][0]['known_bodies'][0]['position'] == [3, 5]
    assert '[999, 999]' not in json.dumps(snapshot)


@pytest.mark.parametrize('persist_first_light', [False, True])
def test_time_series_snapshot_keeps_epochs_and_deduplicates_free_first_light(manager, persist_first_light):
    directory = manager.runs_dir / 'moving-observations'
    folder = directory / 'records' / 'body_observation'
    folder.mkdir(parents=True)
    first = {'observation_id': 'body_0001', 'body_ids': ['b1'], 'times': [0, 1],
             'positions_obs': [[[2.1, 4.1]], [[4, 6]]]}
    second = {'observation_id': 'body_0002', 'body_ids': ['b1'], 'times': [1, 3],
              'positions_obs': [[[6, 8]], [[9, 11]]]}
    _write(directory / 'mission.json', {'task': {
        'body_observation_protocol': 'time_series', 'physics_version': 'v4',
        'position_noise_sigma': .1,
        'body_initial_states': [{'body_id': 'b1', 'position': [2, 4], 'velocity': [0, 0]}]},
        'first_light': {'body_observation': first}})
    if persist_first_light:
        _write(folder / 'body_0001.json', first)
    _write(folder / 'body_0002.json', second)
    frozen = {'kind': 'observed_body_trajectories', 'version': 'body_trajectory_1',
              'times': [0, 1], 'positions': [[[2, 4]], [[4, 6]]], 'body_ids': ['b1'],
              'time_range': [0, 1], 'observation_ids': ['body_0001']}
    (directory / 'records' / 'law').mkdir()
    _write(directory / 'records' / 'law' / 'law_1.json', {'law_id': 'law_1', 'body_context': frozen,
            'body_position_estimate': frozen, 'body_input_protocol': 'instantaneous_visible_state'})
    validation_context = dict(frozen, version='body_trajectory_2', time_range=[0, 3])
    (directory / 'records' / 'validation').mkdir()
    _write(directory / 'records' / 'validation' / 'validation_1.json', {
        'validation_id': 'validation_1', 'law_id': 'law_1', 'body_context': validation_context})
    before = {path: path.read_bytes() for path in directory.rglob('*.json')}
    snapshot = manager.snapshot(directory.name)
    assert snapshot['body_observation_protocol'] == 'time_series'
    assert snapshot['body_position_source'] == 'observed_trajectories'
    estimate = snapshot['body_position_estimate']
    assert estimate['kind'] == 'observed_body_trajectories'
    assert estimate['times'] == [0, 1, 3]
    assert estimate['positions'] == [[[2, 4]], [[5, 7]], [[9, 11]]]
    assert estimate['sample_counts'] == [[0], [2], [1]]
    assert estimate['observation_ids'] == ['body_0001', 'body_0002']
    assert estimate['time_range'] == [0, 3]
    assert snapshot['bodies'] == [{'body_id': 'b1', 'position': [9, 11], 'position_time': 3}]
    assert len(snapshot['records']['body_observations']) == 2
    assert snapshot['records']['laws'][0]['body_context'] == frozen
    assert snapshot['records']['validations'][0]['body_context'] == validation_context
    assert {path: path.read_bytes() for path in directory.rglob('*.json')} == before


def test_time_series_snapshot_can_show_public_initial_position_without_future_extrapolation(manager):
    directory = manager.runs_dir / 'initial-state-only'
    directory.mkdir()
    _write(directory / 'mission.json', {'task': {'body_observation_protocol': 'time_series',
        'body_initial_states': [{'body_id': 'b1', 'position': [2, 4], 'velocity': [100, 100]}]}})
    snapshot = manager.snapshot(directory.name)
    assert snapshot['body_position_estimate']['times'] == [0]
    assert snapshot['body_position_estimate']['time_range'] == [0, 0]
    assert snapshot['bodies'] == [{'body_id': 'b1', 'position': [2, 4], 'position_time': 0}]
    assert snapshot['body_position_estimate']['observation_ids'] == []


def test_time_series_snapshot_does_not_replace_invalid_observations_with_legacy_coordinates(manager):
    directory = manager.runs_dir / 'malformed-moving-observations'
    directory.mkdir()
    _write(directory / 'mission.json', {'task': {'body_observation_protocol': 'time_series',
        'visible_bodies': [{'body_id': 'b1', 'position': [999, 999]}]},
        'first_light': {'body_observation': {'observation_id': 'body_0001', 'body_ids': ['b1'],
                                           'times': [0, 1], 'positions_obs': []}}})
    snapshot = manager.snapshot(directory.name)
    assert snapshot['body_position_source'] == 'invalid_observations'
    assert snapshot['bodies'] == [] and snapshot['body_position_estimate'] is None
    assert '[999, 999]' not in json.dumps(snapshot)


@pytest.mark.parametrize('valid', [True, False])
def test_snapshot_first_light_fallback_never_reveals_truth_on_invalid_observations(manager, valid):
    directory = manager.runs_dir / 'first-light-only'
    directory.mkdir()
    observation = {'observation_id': 'body_0001', 'body_ids': ['b1'], 'times': [0],
                   'positions_obs': [[[2, 4]]] if valid else []}
    _write(directory / 'mission.json', {'task': {'visible_bodies': [{'body_id': 'b1', 'position': [999, 999]}]},
                                     'first_light': {'body_observation': observation}})
    snapshot = manager.snapshot(directory.name)
    assert snapshot['records']['body_observations'] == [observation]
    assert snapshot['body_position_source'] == ('observed_estimate' if valid else 'invalid_observations')
    assert (snapshot['bodies'][0]['position'] == [2, 4]) if valid else snapshot['bodies'] == []
    assert '[999, 999]' not in json.dumps(snapshot)


def test_historical_modes_never_misrepresent_manual_or_analyst(manager):
    for name, result, expected in [
        ('offline-example', {'status': 'submitted'}, 'manual_engineering_smoke'),
        ('manual', {'status': 'submitted', 'mode': 'manual_engineering_smoke', 'autonomous_discovery': False}, 'manual_engineering_smoke'),
        ('diagnostic', {'status': 'analyst_checked', 'mode': 'standalone_analyst_diagnostic'}, 'standalone_analyst_diagnostic'),
        ('unknown', {'status': 'incomplete'}, 'historical_unverified'),
    ]:
        directory = manager.runs_dir / name
        directory.mkdir()
        _write(directory / 'result.json', result)
        assert manager.snapshot(name)['mode'] == expected


def test_whitelist_refuses_traversal_and_symlinks(manager, tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    _write(outside / 'result.json', {'status': 'submitted', 'reason': 'outside_secret'})
    (manager.runs_dir / 'linked').symlink_to(outside, target_is_directory=True)
    for name in ('../outside', '/tmp', '..', 'linked', 'missing'):
        with pytest.raises(FileNotFoundError):
            manager.snapshot(name)
    directory = manager.runs_dir / 'safe'
    directory.mkdir()
    (directory / 'result.json').symlink_to(outside / 'result.json')
    assert manager.snapshot('safe')['result'] is None
    (directory / 'records').symlink_to(outside, target_is_directory=True)
    assert manager.snapshot('safe')['records']['laws'] == []


def test_real_worker_without_key_never_calls_provider(tmp_path):
    directory = tmp_path / 'worker'
    directory.mkdir()
    env = dict(os.environ)
    env.pop('DEEPSEEK_API_KEY', None)
    env['PYTHONPATH'] = str(PROJECT)
    completed = subprocess.run([sys.executable, '-m', 'shore_agent.web_worker', '--run-dir', str(directory)],
                               input='{"api_key":""}\n', text=True, cwd=PROJECT, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
    assert completed.returncode == 2
    result = json.loads((directory / 'result.json').read_text())
    assert result == {'status': 'incomplete', 'reason': 'missing_api_key', 'submission': None}
    assert not (directory / 'model_events.jsonl').exists()
    assert not completed.stdout and not completed.stderr


def test_real_cancellation_kills_worker_group_and_keeps_no_submission(manager, monkeypatch):
    original = subprocess.Popen
    child_pid_file = manager.project_root / 'child.pid'
    script = ('import subprocess,sys,time,signal; from pathlib import Path; '
              'signal.signal(signal.SIGTERM, signal.SIG_IGN); '
              'p=subprocess.Popen([sys.executable,"-c","import time,signal;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)"]); '
              f'Path({str(child_pid_file)!r}).write_text(str(p.pid)); time.sleep(60)')

    def substitute(argv, **kwargs):
        return original([sys.executable, '-c', script], **kwargs)

    monkeypatch.setattr(web_jobs.subprocess, 'Popen', substitute)
    run_id = manager.start({'api_key': 'unused-test-key'})
    process = manager._owned[run_id]
    deadline = time.monotonic() + 5
    while not child_pid_file.exists() and time.monotonic() < deadline:
        time.sleep(.02)
    assert child_pid_file.exists()
    child_pid = int(child_pid_file.read_text())
    snapshot = manager.stop(run_id)
    assert process.poll() is not None
    assert snapshot['status'] == 'stopped'
    assert snapshot['result']['submission'] is None
    # An orphan may briefly remain a zombie, but must never still execute.
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(.02)
    else:
        pytest.fail('Simulator descendant survived group cancellation')


def test_worker_evaluation_runs_after_agent_and_environment_close(tmp_path, monkeypatch):
    from shore_agent import agent, environment, model, runtime
    directory = tmp_path / 'evaluation-order'
    directory.mkdir()
    config = json.loads((PROJECT / 'config.example.json').read_text())
    _write(directory / 'config.json', config)
    monkeypatch.setattr(sys, 'stdin', io.StringIO('{"api_key":"sk-privateworkerkey123"}\n'))
    phases = []

    class FakeEnvironment:
        def __init__(self, config, **kwargs):
            pass

        def request(self, method, **kwargs):
            return {'ok': True, 'data': {'task': {'body_ids': ['b1'], 'position_noise_sigma': 0,
                                              'static_visible_bodies': True},
                    'first_light': {'body_observation': {'observation_id': 'o1', 'body_ids': ['b1'],
                    'times': [0], 'positions_obs': [[[1, 2]]]}, 'probes': []}}, 'budget': {}}

        def close(self):
            phases.append('environment_closed')

    class FakeClient:
        def __init__(self, *args, **kwargs):
            assert os.environ['DEEPSEEK_API_KEY'] == 'sk-privateworkerkey123'

        def close(self):
            phases.append('client_closed')

    class FakeAgent:
        def __init__(self, *args, **kwargs):
            pass

        def run(self):
            phases.append('agent_finished')
            folder = directory / 'records' / 'submission'
            folder.mkdir(parents=True)
            _write(folder / 's1.json', {'status': 'accepted', 'session_ended': True, 'law_id': 'l1'})
            result = {'status': 'submitted', 'submission': {'law_id': 'l1'}}
            _write(directory / 'result.json', result)
            return result

    def evaluate(argv, **kwargs):
        assert phases == ['agent_finished', 'client_closed', 'environment_closed']
        assert 'DEEPSEEK_API_KEY' not in os.environ
        assert argv[1].endswith('evaluate.py')
        phases.append('evaluated')
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(environment, 'Environment', FakeEnvironment)
    monkeypatch.setattr(model, 'DeepSeekClient', FakeClient)
    monkeypatch.setattr(agent, 'Agent', FakeAgent)
    monkeypatch.setattr(web_worker.subprocess, 'run', evaluate)
    assert web_worker.run(directory) == 0, phases
    assert phases[-1] == 'evaluated'
    assert all('sk-privateworkerkey123' not in path.read_text() for path in directory.rglob('*.json'))
    assert json.loads((directory / 'web.json').read_text())['status'] == 'submitted'


def test_worker_failure_redacts_exception_and_never_calls_evaluator(tmp_path, monkeypatch):
    directory = tmp_path / 'failure'
    directory.mkdir()
    monkeypatch.setattr(sys, 'stdin', io.StringIO('{"api_key":"sk-privateworkerkey123"}\n'))
    # Invalid config induces a local exception; no provider initialization occurs.
    _write(directory / 'config.json', {'secret': 'sk-privateworkerkey123'})
    assert web_worker.run(directory) == 1
    result = json.loads((directory / 'result.json').read_text())
    assert result['reason'] == 'worker_failed'
    assert 'sk-' not in json.dumps(result)
    assert 'DEEPSEEK_API_KEY' not in os.environ


def test_running_wall_budget_decreases_during_model_call(manager, launch):
    from datetime import datetime, timedelta, timezone
    run_id = manager.start({'api_key': 'test-key'})
    directory = manager.runs_dir / run_id
    started = (datetime.now(timezone.utc) - timedelta(seconds=25)).isoformat()
    manager._update_metadata(directory, session_started_at=started,
                             initial_budget={'energy_remaining': 100, 'observations_remaining': 20,
                                             'wall_seconds_remaining': 3600, 'session_ended': False})
    snapshot = manager.snapshot(run_id)
    assert snapshot['budget']['energy_remaining'] == 100
    assert snapshot['budget']['observations_remaining'] == 20
    assert 3570 < snapshot['budget']['wall_seconds_remaining'] < 3576



def historical_run(manager, run_id='saved-experiment'):
    directory = manager.runs_dir / run_id
    directory.mkdir()
    _write(directory / 'result.json', {'status': 'submitted', 'mode': 'manual_engineering_smoke',
                                      'submission': {'law_id': 'law_example'}})
    _write(directory / 'web.json', {'status': 'submitted', 'mode': 'manual_engineering_smoke',
                                   'created_at': '2026-10-30T12:00:00+00:00'})
    records = directory / 'records' / 'law'
    records.mkdir(parents=True)
    _write(records / 'law_example.json', {'law_id': 'law_example', 'law_spec': {'ax': '-k*x', 'ay': '-k*y'}})
    (directory / 'opaque.bin').write_bytes(bytes(range(256)))
    (directory / 'messages.json').write_text('private history must be preserved, never listed')
    return directory


def tree_bytes(directory):
    return {str(path.relative_to(directory)): path.read_bytes()
            for path in directory.rglob('*') if path.is_file()}


def test_delete_and_restore_preserve_full_data_and_listing(manager):
    directory = historical_run(manager)
    original = tree_bytes(directory)
    assert manager.list_runs()['deleted_runs'] == []
    assert not (manager.runs_dir / '.trash').exists()  # Listing stays read-only.
    assert manager.delete(directory.name) == {'deleted_run_id': directory.name}
    assert not directory.exists()
    deleted_directory = manager.runs_dir / '.trash' / directory.name
    assert tree_bytes(deleted_directory) == original
    listing = manager.list_runs()
    assert listing['runs'] == []
    assert listing['active_run_id'] is None
    assert len(listing['deleted_runs']) == 1
    deleted = listing['deleted_runs'][0]
    assert deleted['id'] == directory.name
    assert deleted['created_at'] == '2026-10-30T12:00:00+00:00'
    assert deleted['deleted_at']
    assert deleted['mode'] == 'manual_engineering_smoke'
    assert deleted['status'] == 'submitted'
    assert 'private history' not in json.dumps(listing)
    with pytest.raises(FileNotFoundError):
        manager.snapshot(directory.name)
    assert manager.restore(directory.name) == {'restored_run_id': directory.name}
    assert tree_bytes(directory) == original
    assert not deleted_directory.exists()
    listing = manager.list_runs()
    assert listing['deleted_runs'] == []
    assert listing['runs'][0]['id'] == directory.name
    assert listing['runs'][0]['created_at'] == '2026-10-30T12:00:00+00:00'
    # The same session remains deletable again after restoration.
    manager.delete(directory.name)
    assert len(manager.list_runs()['deleted_runs']) == 1


def test_deleted_runs_persist_across_manager_restart(manager):
    directory = historical_run(manager)
    manager.delete(directory.name)
    second_manager = RunManager(manager.project_root)
    try:
        assert second_manager.list_runs()['deleted_runs'][0]['id'] == directory.name
        second_manager.restore(directory.name)
        assert manager.snapshot(directory.name)['status'] == 'submitted'
    finally:
        second_manager.close()


def test_delete_active_run_is_a_coded_conflict_and_does_not_stop_it(manager, launch):
    run_id = manager.start({'api_key': 'mock-only-no-api-call'})
    with pytest.raises(ConflictError) as exc:
        manager.delete(run_id)
    assert isinstance(exc.value, RuntimeError)
    assert exc.value.code == 'run_is_active'
    assert manager.snapshot(run_id)['running'] is True
    assert launch[1] == []
    assert not (manager.runs_dir / '.trash').exists()


@pytest.mark.parametrize('method', ['delete', 'restore'])
@pytest.mark.parametrize('run_id', ['../outside', '/tmp', '.', '.trash', 'missing', 'a/b'])
def test_delete_restore_unknown_or_invalid_paths(manager, method, run_id):
    with pytest.raises(FileNotFoundError):
        getattr(manager, method)(run_id)
    assert not (manager.runs_dir / '.trash').exists()


def test_delete_does_not_overwrite_existing_trash_directory(manager):
    directory = historical_run(manager)
    destination = manager.runs_dir / '.trash' / directory.name
    destination.mkdir(parents=True)
    (destination / 'keep.txt').write_text('old data')
    original = tree_bytes(directory)
    with pytest.raises(ConflictError) as exc:
        manager.delete(directory.name)
    assert exc.value.code == 'run_already_exists'
    assert tree_bytes(directory) == original
    assert (destination / 'keep.txt').read_text() == 'old data'


@pytest.mark.parametrize('destination_kind', ['empty_directory', 'file', 'dangling_symlink'])
def test_restore_never_overwrites_existing_destination(manager, destination_kind):
    directory = historical_run(manager)
    original = tree_bytes(directory)
    manager.delete(directory.name)
    if destination_kind == 'empty_directory':
        directory.mkdir()
    elif destination_kind == 'file':
        directory.write_text('keep this file')
    else:
        directory.symlink_to(manager.project_root / 'missing-target')
    with pytest.raises(ConflictError) as exc:
        manager.restore(directory.name)
    assert exc.value.code == 'run_already_exists'
    assert tree_bytes(manager.runs_dir / '.trash' / directory.name) == original
    assert len(manager.list_runs()['deleted_runs']) == 1
    assert os.path.lexists(directory)


def test_exclusive_rename_prevents_destination_created_after_check(tmp_path, monkeypatch):
    source, destination = tmp_path / 'source', tmp_path / 'destination'
    source.mkdir()
    destination.mkdir()
    source_inode, destination_inode = source.stat().st_ino, destination.stat().st_ino
    # Simulate the destination appearing between the initial check and rename.
    original_exists = os.path.lexists
    monkeypatch.setattr(web_jobs.os.path, 'lexists', lambda path: False if Path(path) == destination else original_exists(path))
    with pytest.raises(ConflictError, match='run_already_exists'):
        web_jobs._move_directory_no_replace(source, destination)
    assert source.stat().st_ino == source_inode
    assert destination.stat().st_ino == destination_inode


def test_symlink_trash_is_never_followed(manager, tmp_path):
    directory = historical_run(manager)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (manager.runs_dir / '.trash').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ConflictError, match='unsafe_trash_directory'):
        manager.delete(directory.name)
    with pytest.raises(ConflictError, match='unsafe_trash_directory'):
        manager.restore(directory.name)
    assert not list(outside.iterdir())
    assert directory.is_dir()
    assert manager.list_runs()['deleted_runs'] == []


def test_symlink_metadata_directory_is_never_followed(manager, tmp_path):
    directory = historical_run(manager)
    outside = tmp_path / 'outside'
    outside.mkdir()
    trash = manager.runs_dir / '.trash'
    trash.mkdir()
    (trash / '.metadata').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ConflictError, match='unsafe_trash_directory'):
        manager.delete(directory.name)
    assert not list(outside.iterdir())
    assert directory.is_dir()


def test_symlink_source_runs_are_not_moved_or_listed(manager, tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'precious.txt').write_text('keep')
    (manager.runs_dir / 'linked').symlink_to(outside, target_is_directory=True)
    with pytest.raises(FileNotFoundError):
        manager.delete('linked')
    trash = manager.runs_dir / '.trash'
    trash.mkdir()
    (trash / 'linked').symlink_to(outside, target_is_directory=True)
    with pytest.raises(FileNotFoundError):
        manager.restore('linked')
    assert manager.list_runs()['deleted_runs'] == []
    assert (outside / 'precious.txt').read_text() == 'keep'


def test_delete_move_failure_retains_original_and_removes_only_new_metadata(manager, monkeypatch):
    directory = historical_run(manager)
    original = tree_bytes(directory)
    def fail(*args):
        raise OSError('mock move failure')
    monkeypatch.setattr(web_jobs, '_move_directory_no_replace', fail)
    with pytest.raises(OSError):
        manager.delete(directory.name)
    assert tree_bytes(directory) == original
    assert manager.list_runs()['deleted_runs'] == []
    assert not (manager.runs_dir / '.trash' / '.metadata' / (directory.name + '.json')).exists()


def test_delete_refuses_unrecognized_folder(manager):
    unrelated = manager.runs_dir / 'unrelated-folder'
    unrelated.mkdir()
    (unrelated / 'valuable.txt').write_text('not a scientific session')
    with pytest.raises(FileNotFoundError):
        manager.delete(unrelated.name)
    assert (unrelated / 'valuable.txt').read_text() == 'not a scientific session'
    assert not (manager.runs_dir / '.trash').exists()


def test_delete_does_not_overwrite_existing_trash_metadata(manager):
    directory = historical_run(manager)
    metadata_directory = manager.runs_dir / '.trash' / '.metadata'
    metadata_directory.mkdir(parents=True)
    metadata_path = metadata_directory / (directory.name + '.json')
    metadata_path.write_text('preserve stale bookkeeping for review')
    with pytest.raises(ConflictError, match='run_already_exists'):
        manager.delete(directory.name)
    assert directory.is_dir()
    assert metadata_path.read_text() == 'preserve stale bookkeeping for review'


def test_move_preserves_internal_symlink_without_accessing_target(manager, tmp_path):
    directory = historical_run(manager)
    outside = tmp_path / 'external-secret'
    outside.write_text('keep outside untouched')
    (directory / 'linked-artifact').symlink_to(outside)
    manager.delete(directory.name)
    moved = manager.runs_dir / '.trash' / directory.name / 'linked-artifact'
    assert moved.is_symlink()
    assert os.readlink(moved) == str(outside)
    manager.restore(directory.name)
    assert (directory / 'linked-artifact').is_symlink()
    assert outside.read_text() == 'keep outside untouched'

@pytest.mark.parametrize('total_budget', [2000000, 5000000, 10000000])
def test_large_budget_persisted_in_config_and_snapshot(manager, launch, total_budget):
    run_id = manager.start({'api_key': 'mock-only', 'max_total_tokens': total_budget,
                            'max_tokens_per_call': 65536})
    config = json.loads((manager.runs_dir / run_id / 'config.json').read_text())['model']
    assert config['max_total_tokens'] == total_budget
    assert config['max_tokens_per_call'] == 65536
    assert config['timeout_seconds'] == 600
    limits = manager.snapshot(run_id)['limits']
    assert limits['max_tokens_per_call'] == 65536
    assert limits['max_total_tokens'] == total_budget


@pytest.mark.parametrize('effort', ['low', 'high', 'max'])
def test_selected_effort_is_persisted_and_exportable(manager, launch, effort):
    run_id = manager.start({'api_key': 'mock-only', 'reasoning_effort': effort})
    configuration = json.loads((manager.runs_dir / run_id / 'config.json').read_text())
    assert configuration['model']['reasoning_effort'] == effort
    assert configuration['model']['max_total_tokens'] == 5000000
    settings = manager.snapshot(run_id)['model_settings']
    assert settings['reasoning_effort'] == effort
    assert settings['thinking'] is True
    assert settings['model'] == 'deepseek-flash'
    assert settings['reasoning_protocol'] == 'deepseek'


def test_server_config_controls_bootstrap_endpoint_model_and_auth(manager, tmp_path, monkeypatch, launch):
    path = tmp_path / 'local.json'
    _write(path, {'model': {'base_url': 'http://127.0.0.1:8000/v1', 'model': 'served-v4-flash',
                           'deployment': 'local', 'reasoning_protocol': 'chat_template',
                           'api_key_env': 'SHORE_TEST_LOCAL_KEY', 'api_key_required': False,
                           'reasoning_effort': 'max', 'max_total_tokens': 7000000},
                  'environment': {'seed': 77, 'world_id': 'world_5'}})
    manager.config_path = path
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'unrelated-cloud-key')
    monkeypatch.delenv('SHORE_TEST_LOCAL_KEY', raising=False)
    public = manager.client_configuration()
    assert public['models'] == [{'id': 'served-v4-flash', 'name': 'served-v4-flash'}]
    assert public['defaults']['model'] == 'served-v4-flash'
    assert public['defaults']['reasoning_effort'] == 'max'
    assert public['defaults']['max_total_tokens'] == 7000000
    assert public['defaults']['world_id'] == 'world_5'
    assert public['defaults']['seed'] == 77
    assert public['api_key_required'] is False
    assert public['api_key_configured'] is False
    assert 'base_url' not in json.dumps(public)
    for payload, code in [({'model': 'deepseek-flash'}, 'invalid_model'),
                          ({'base_url': 'https://example.com'}, 'invalid_run_configuration'),
                          ({'reasoning_protocol': 'deepseek'}, 'invalid_run_configuration')]:
        with pytest.raises(ValidationError, match=code):
            manager._config(payload)
    run_id = manager.start({'reasoning_effort': 'high'})
    config = json.loads((manager.runs_dir / run_id / 'config.json').read_text())
    assert config['model']['base_url'] == 'http://127.0.0.1:8000/v1'
    assert config['model']['reasoning_protocol'] == 'chat_template'
    assert config['model']['model'] == 'served-v4-flash'
    assert config['model']['reasoning_effort'] == 'high'
    assert config['environment']['world_id'] == 'world_5'
    assert json.loads(launch[0][0][2].stdin.text) == {'api_key': ''}
    assert 'DEEPSEEK_API_KEY' not in launch[0][0][1]['env']


def test_custom_server_key_environment_stays_out_of_config_and_child_environment(manager, tmp_path, monkeypatch, launch):
    path = tmp_path / 'authenticated.json'
    _write(path, {'model': {'api_key_env': 'SHORE_TEST_AUTH_KEY', 'reasoning_effort': 'high'}})
    manager.config_path = path
    secret = 'synthetic-local-auth-value'
    monkeypatch.setenv('SHORE_TEST_AUTH_KEY', secret)
    assert manager.client_configuration()['api_key_configured'] is True
    run_id = manager.start({})
    options, process = launch[0][0][1:]
    assert 'SHORE_TEST_AUTH_KEY' not in options['env']
    assert json.loads(process.stdin.text) == {'api_key': secret}
    assert all(secret not in file.read_text() for file in (manager.runs_dir / run_id).iterdir())


@pytest.mark.parametrize('model', web_jobs.QWEN_MODELS)
def test_qwen_models_use_one_provider_without_changing_agent_settings(manager, tmp_path, monkeypatch, model):
    path = tmp_path / 'qwen.json'
    path.write_text((PROJECT / 'config.qwen.example.json').read_text())
    manager.config_path = path
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'synthetic-qwen-key')
    public = manager.client_configuration()
    assert [item['id'] for item in public['models']] == list(web_jobs.QWEN_MODELS)
    assert public['defaults']['model'] == 'qwen3.8-27b'
    assert public['reasoning_effort_supported'] is False
    assert public['api_key_configured'] is True
    assert public['api_key_env'] == 'DASHSCOPE_API_KEY'
    config, key = manager._config({'model': model, 'world_set': 'v15'})
    assert config['model']['model'] == model
    assert config['model']['reasoning_protocol'] == 'qwen'
    assert config['model']['base_url'] == 'https://dashscope.aliyuncs.com/compatible-mode/v1'
    assert key == 'synthetic-qwen-key'
    baseline = json.loads((PROJECT / 'config.example.json').read_text())
    for section in ('agent', 'numerics', 'code_execution'):
        assert config[section] == baseline[section]
    with pytest.raises(ValidationError, match='invalid_output_budget'):
        manager._config({'model': model, 'max_tokens_per_call': web_jobs.QWEN_OUTPUT_LIMITS[model] + 1})
    with pytest.raises(ValidationError, match='invalid_model'):
        manager._config({'model': 'deepseek-flash'})


def test_public_projection_redacts_entire_workspace_key():
    synthetic = 'sk-ws-TEST.SYNTHETIC.payload_with-dots'
    assert web_jobs._public({'message': 'Credential ' + synthetic}) == {'message': 'Credential [redacted]'}


def test_legacy_missing_effort_is_unknown_not_current_default(manager):
    directory = manager.runs_dir / 'legacy-effort'
    directory.mkdir()
    _write(directory / 'config.json', {'model': {'max_total_tokens': 2000000}})
    original = (directory / 'config.json').read_bytes()
    snapshot = manager.snapshot(directory.name)
    assert snapshot['model_settings']['reasoning_effort'] is None
    assert snapshot['model_settings']['thinking'] is None
    assert snapshot['limits']['max_total_tokens'] == 2000000
    assert (directory / 'config.json').read_bytes() == original


def test_local_qwen_routes_only_deployed_models(manager, tmp_path):
    config = json.loads((PROJECT / 'config.qwen.example.json').read_text())
    config['model'].update(deployment='local', base_url='http://127.0.0.1:8000/v1',
        api_key_env='UNCONFIGURED_LOCAL_KEY', api_key_required=False, local_model_endpoints={
            'qwen3.8-27b': 'http://127.0.0.1:8000/v1',
            'qwen3.5-122b-a10b': 'http://127.0.0.1:8002/v1'})
    path = tmp_path / 'local-qwen.json'
    path.write_text(json.dumps(config))
    manager.config_path = path
    options = manager.client_configuration()['models']
    assert next(x for x in options if x['id'] == 'qwen3.6-35b-a3b')['available'] is False
    effective, key = manager._config({'model': 'qwen3.5-122b-a10b'})
    assert effective['model']['base_url'] == 'http://127.0.0.1:8002/v1'
    assert not key
    with pytest.raises(ValidationError, match='invalid_model'):
        manager._config({'model': 'qwen3.6-35b-a3b'})
