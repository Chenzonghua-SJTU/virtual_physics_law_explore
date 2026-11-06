"""Orchestration tests use explicit fake workers, never real API requests."""
import copy
import io
import json
from pathlib import Path

import pytest

import benchmark_v15 as benchmark


def project_config(tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'config.example.json').write_bytes((benchmark.PROJECT / 'config.example.json').read_bytes())
    (project / 'config.local.web.json').write_bytes((benchmark.PROJECT / 'config.qwen.example.json').read_bytes())
    return project, benchmark.configuration(project)


def test_baseline_copies_current_config_without_old_domain_or_budget_expansion(tmp_path):
    project, config = project_config(tmp_path)
    assert config['environment'] == {
        'world_id': 'world_1', 'world_set': 'v15', 'physics_version': 'shore_v15',
        'noise': False, 'seed': 42, 'wall_seconds': 3600,
    }
    assert config['model']['model'] == 'qwen3.8-27b'
    assert config['model']['thinking'] is True
    original = benchmark.read_json(project / 'config.example.json')
    for key in ('max_total_tokens', 'max_retries'):
        assert config['model'][key] == original['model'][key]
    assert config['numerics'] == original['numerics']
    assert config['agent'] == original['agent']
    assert config['code_execution'] == original['code_execution']


def test_baseline_rejects_inline_credentials_before_writing(tmp_path):
    project, _config = project_config(tmp_path)
    override = benchmark.read_json(project / 'config.local.web.json')
    override['model']['api_key'] = 'synthetic-test-credential'
    (project / 'config.local.web.json').write_text(json.dumps(override))
    with pytest.raises(ValueError, match='credentials_must_not_be_in_configuration'):
        benchmark.configuration(project)
    assert not (project / 'runs').exists()


def test_prepare_six_new_immutable_run_configs_and_refuse_overwrite(tmp_path):
    project, config = project_config(tmp_path)
    original = copy.deepcopy(config)
    output = project / 'experiments' / 'v15-test'
    manifest, runs = benchmark.prepare(output, config, project=project)
    assert len(runs) == 6 and manifest['protocol']['attempts_per_world'] == 1
    assert manifest['workers'] == 3
    for world, directory in runs.items():
        saved = benchmark.read_json(directory / 'config.json')
        assert saved['environment']['world_id'] == world
        meta = benchmark.read_json(directory / 'web.json')
        assert meta['runner_owned'] is True and meta['worker_pid'] is None
        assert meta['status'] == 'queued' and meta['mode'] == 'autonomous_discovery'
        assert meta['benchmark_id'] == output.name
    assert config == original
    preserved = {path: path.read_bytes() for path in project.rglob('*.json')}
    with pytest.raises(ValueError, match='already_exists_no_overwrite'):
        benchmark.prepare(output, config, project=project)
    assert {path: path.read_bytes() for path in project.rglob('*.json')} == preserved


class CaptureInput(io.StringIO):
    def close(self):
        self.saved = self.getvalue()
        super().close()


def test_worker_credential_only_in_stdin_not_argv_env_metadata_or_config(tmp_path, monkeypatch):
    project, config = project_config(tmp_path)
    _manifest, runs = benchmark.prepare(project / 'experiments/test', config, project=project)
    captured = {}

    class FakeProcess:
        pid = 123456
        stdin = CaptureInput()

    def popen(args, **kwargs):
        captured.update(args=args, kwargs=kwargs)
        return FakeProcess()

    key = 'synthetic-test-credential'
    for name in ('DASHSCOPE_API_KEY', 'DEEPSEEK_API_KEY', 'OPENAI_API_KEY'):
        monkeypatch.setenv(name, key)
    directory = runs['world_1']
    process = benchmark.launch(directory, key, project, popen=popen)
    assert json.loads(process.stdin.saved) == {'api_key': key}
    assert key not in repr(captured)
    assert captured['args'][-2:] == ['--run-dir', str(directory.resolve())]
    assert captured['kwargs']['cwd'] == project.resolve()
    assert captured['kwargs']['start_new_session'] is True
    assert all(key not in path.read_text() for path in project.rglob('*.json'))
    meta = benchmark.read_json(directory / 'web.json')
    assert meta['worker_pid'] == process.pid and meta['status'] == 'running'


def test_six_failed_attempts_stay_in_summary_and_are_never_retried(tmp_path, monkeypatch):
    project, config = project_config(tmp_path)
    output = project / 'experiments/v15-failure-test'
    calls = []

    class FakeCompleted:
        pid = 123456
        returncode = 0

        def poll(self):
            return 0

        def wait(self):
            return 0

    def fake_launch(directory, api_key, _project):
        calls.append(directory.name)
        assert api_key == 'synthetic-test-credential'
        benchmark._write(directory / 'result.json', {
            'status': 'incomplete', 'reason': 'synthetic_model_failure', 'submission': None,
            'model_usage': {'calls': 1, 'total_tokens': 123},
            'budget': {'energy_remaining': 100, 'wall_seconds_remaining': 3500},
        })
        return FakeCompleted()

    monkeypatch.setattr(benchmark, 'launch', fake_launch)
    result = benchmark.run(output, config, 'synthetic-test-credential', workers=3, project=project)
    assert len(calls) == len(set(calls)) == 6
    assert result['status'] == 'completed'
    assert len(result['worlds']) == 6
    assert all(row['status'] == 'incomplete' and row['tokens'] == 123
               and row['energy_used'] == 0 and row['evaluation_score'] is None
               and row['independent_rmse'] is None for row in result['worlds'])
    assert benchmark.read_json(output / 'summary.json')['status'] == 'completed'
    assert benchmark.read_json(output / 'manifest.json')['status'] == 'completed'
    report = (output / 'report.md').read_text()
    assert 'synthetic_model_failure' in report
    assert 'synthetic-test-credential' not in report
    for run_id in calls:
        metadata = benchmark.read_json(project / 'runs' / run_id / 'web.json')
        assert metadata['worker_pid'] is None
        assert metadata['status'] == 'incomplete'


def test_mismatched_evaluation_is_not_reported_as_success(tmp_path):
    submission = {'submission_id': 's1', 'law_id': 'law1', 'status': 'accepted', 'session_ended': True}
    snapshot = {'status': 'submitted', 'world_id': 'world_1',
                'records': {'submissions': [submission]},
                'evaluation': {'world_set': 'v15', 'world_id': 'world_2', 'physics_version': 'shore_v15',
                               'law_id': 'law1', 'submission_id': 's1', 'complete': True,
                               'overall': {'position_rmse': 0}},
                'evaluation_score': {'total': 100}}
    row = benchmark.summarize(snapshot, Path(tmp_path))
    assert row['accepted_submission'] is True
    assert row['evaluation_complete'] is False
    assert row['evaluation_score'] is row['independent_rmse'] is None


def test_no_thinking_reaches_all_six_saved_configs_and_report(tmp_path):
    project, _config = project_config(tmp_path)
    config = benchmark.configuration(project, thinking=False)
    output = project / 'experiments/v15-no-thinking'
    manifest, runs = benchmark.prepare(output, config, project=project)
    assert manifest['configuration']['model']['thinking'] is False
    assert all(benchmark.read_json(directory / 'config.json')['model']['thinking'] is False
               for directory in runs.values())
    report = benchmark.markdown(dict(manifest, worlds=[]))
    assert 'thinking=false' in report and 'thinking=true' not in report
    assert 'Tokens 仅统计 API 已返回的 usage' in report
    assert '超时或失败请求可能没有返回用量' in report


def test_report_output_average_excludes_inputs_and_marks_missing_usage(tmp_path):
    _project, config = project_config(tmp_path)
    row = benchmark.summarize({'status': 'incomplete', 'world_id': 'world_1',
        'model_usage': {'calls': 2, 'prompt_tokens': 1000, 'completion_tokens': 300,
                        'total_tokens': 1300, 'conservative_reserved_tokens': 0}}, tmp_path)
    row['wall_seconds_including_evaluation'] = 112.5
    summary = {'experiment_id': 'test', 'status': 'completed', 'configuration': config, 'worlds': [row]}
    line = next(line for line in benchmark.markdown(summary).splitlines() if line.startswith('| world_1 |'))
    assert '| 2 | 1300 | 300 | 150 |' in line
    assert line.endswith('| 112.5 |')
    row['conservative_reserved_tokens'] = 100
    line = next(line for line in benchmark.markdown(summary).splitlines() if line.startswith('| world_1 |'))
    assert '| 2 | 1300 | 300 | — |' in line


@pytest.mark.parametrize('value', [None, 0, 1, 'false'])
def test_thinking_requires_an_actual_boolean(tmp_path, value):
    with pytest.raises(ValueError, match='thinking_must_be_boolean'):
        benchmark.configuration(tmp_path, thinking=value)


def test_e4_profile_and_queue_are_reserved_before_mission(tmp_path):
    project, _ = project_config(tmp_path)
    config = benchmark.configuration(project, ruleset='e4')
    assert config['environment']['ruleset'] == 'e4'
    assert config['environment']['wall_seconds'] == 300
    assert config['environment']['energy_budget'] == 10
    assert config['environment']['noise'] is True
    assert config['model']['thinking'] is False
    assert config['model']['max_tokens_per_call'] == 4096
    endpoints = ['http://127.0.0.1:8000/v1', 'http://127.0.0.1:8001/v1']
    manifest, runs = benchmark.prepare(project / 'experiments/E4/test-e4', config,
                                       workers=4, project=project, model_endpoints=endpoints)
    assert manifest['workers'] == 2
    assert manifest['protocol']['energy_budget'] == 10
    assert manifest['protocol']['wall_seconds_per_world'] == 300
    assert manifest['protocol']['official_sdk_compatible'] is False
    for directory in runs.values():
        metadata = benchmark.read_json(directory / 'web.json')
        assert metadata['status'] == 'queued' and metadata['experiment_group'] == 'E4'
        assert 'session_started_at' not in metadata
        assert not (directory / 'mission.json').exists()
    with pytest.raises(ValueError, match='distinct'):
        benchmark.prepare(project / 'experiments/bad', config, project=project,
                          model_endpoints=[endpoints[0], endpoints[0] + '/'])


def test_endpoint_pool_never_launches_two_active_worlds_on_one_service(tmp_path, monkeypatch):
    project, _ = project_config(tmp_path)
    config = benchmark.configuration(project, ruleset='e4')
    config['model'].update(deployment='local', api_key_required=False)
    endpoints = ['http://127.0.0.1:8000/v1', 'http://127.0.0.1:8001/v1']
    busy, launched = set(), []

    class FakeProcess:
        pid = 123456
        returncode = 0
        def __init__(self, endpoint):
            self.endpoint, self.polls = endpoint, 0
        def poll(self):
            self.polls += 1
            if self.polls == 1:
                return None
            busy.remove(self.endpoint)
            return 0
        def wait(self):
            return 0

    def fake_launch(directory, api_key, _project):
        effective = benchmark.read_json(directory / 'config.json')
        endpoint = effective['model']['base_url']
        assert endpoint not in busy
        assert len(list((_project / 'runs').glob('*/web.json'))) == 6
        busy.add(endpoint); launched.append((directory.name, endpoint))
        benchmark._write(directory / 'result.json', {'status': 'incomplete', 'reason': 'synthetic',
            'submission': None, 'model_usage': {'calls': 0, 'completion_tokens': 0},
            'budget': {'energy_remaining': 10, 'wall_seconds_remaining': 290}})
        return FakeProcess(endpoint)

    monkeypatch.setattr(benchmark, 'launch', fake_launch)
    monkeypatch.setattr(benchmark.time, 'sleep', lambda _seconds: None)
    summary = benchmark.run(project / 'experiments/E4/e4-pool', config, '', workers=4,
                            project=project, model_endpoints=endpoints)
    assert len(launched) == len(set(name for name, _ in launched)) == 6
    assert set(endpoint for _, endpoint in launched) == set(endpoints)
    assert summary['status'] == 'completed' and not busy
    assert all(row['energy_used'] == 0 and row['exploration_seconds'] == 10 for row in summary['worlds'])


def test_summary_separates_exploration_evaluation_and_checks_each_output(tmp_path):
    benchmark._write(tmp_path / 'config.json', {'environment': {'ruleset': 'e4', 'wall_seconds': 300},
                                               'model': {'max_tokens_per_call': 4096}})
    benchmark._write(tmp_path / 'web.json', {'exploration_wall_seconds': 297,
        'evaluation_wall_seconds': 9, 'wall_seconds_including_evaluation': 308})
    (tmp_path / 'model_events.jsonl').write_text('\n'.join(json.dumps({'event': 'request',
        'usage': {'completion_tokens': value}}) for value in (100, 4200)))
    row = benchmark.summarize({'status': 'incomplete', 'world_id': 'world_1',
        'model_usage': {'calls': 2, 'completion_tokens': 4300},
        'budget': {'energy_remaining': 7, 'wall_seconds_remaining': 3}}, tmp_path)
    assert row['energy_used'] == 3
    assert row['exploration_seconds'] == 297 and row['evaluation_seconds'] == 9
    assert row['wall_seconds_including_evaluation'] == 308
    assert row['average_output_tokens_per_call'] == 2150
    assert row['max_call_output_tokens'] == 4200 and row['output_limit_exceeded_calls'] == 1
    assert row['output_cap_compliant'] is False


def test_e4_watchdog_uses_mission_deadline_and_excludes_evaluation():
    from datetime import datetime, timezone
    current = datetime(2026, 11, 7, 0, 5, 11, tzinfo=timezone.utc)
    metadata = {'ruleset': 'e4', 'status': 'running', 'exploration_deadline_at': '2026-11-07T00:05:00+00:00'}
    assert benchmark.watchdog_expired(metadata, current)
    assert not benchmark.watchdog_expired(dict(metadata, status='evaluating'), current)
    assert not benchmark.watchdog_expired(dict(metadata, exploration_finished_at='2026-11-07T00:05:00+00:00'), current)
    assert not benchmark.watchdog_expired({'ruleset': 'e4', 'status': 'queued'}, current)
    assert not benchmark.watchdog_expired(dict(metadata, ruleset='e3'), current)


def test_no_thinking_cli_passes_false_to_configuration(tmp_path, monkeypatch):
    project, config = project_config(tmp_path)
    captured = {}

    def fake_configuration(**kwargs):
        captured.update(kwargs)
        value = copy.deepcopy(config)
        value['model']['thinking'] = kwargs['thinking']
        return value

    def fake_run(output, effective, key, workers):
        assert effective['model']['thinking'] is False
        assert key == 'synthetic-test-credential'
        return {'worlds': []}

    monkeypatch.setattr(benchmark, 'configuration', fake_configuration)
    monkeypatch.setattr(benchmark, 'run', fake_run)
    monkeypatch.setattr(benchmark.signal, 'signal', lambda *args: None)
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'synthetic-test-credential')
    monkeypatch.setattr(benchmark.sys, 'argv', ['benchmark_v15.py', '--output', str(tmp_path / 'new'), '--no-thinking'])
    benchmark.main()
    assert captured['thinking'] is False
