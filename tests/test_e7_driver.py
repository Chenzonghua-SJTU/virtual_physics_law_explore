"""E7 orchestration uses mocked HTTP and child processes, never scientific experiments."""
import io
import json
import signal

import pytest

import benchmark_v15 as benchmark
from deployment import run_e7 as driver


class Response(io.BytesIO):
    status = 200

    def __init__(self, value):
        super().__init__(json.dumps(value).encode())


class Opener:
    def __init__(self, replacements=None):
        self.replacements = replacements or {}
        self.calls = []

    def __call__(self, url, timeout):
        assert timeout == 5
        self.calls.append(url)
        value = self.replacements.get(url, {'ready': 4, 'busy': 0} if url.endswith('/health')
                                      else {'data': [{'id': driver.MODEL}]})
        if isinstance(value, BaseException):
            raise value
        return Response(value)


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path/'project'
    (root/'deployment').mkdir(parents=True)
    (root/'experiments/E5').mkdir(parents=True)
    (root/'config.example.json').write_bytes((benchmark.PROJECT/'config.example.json').read_bytes())
    override = {'model': {'deployment': 'local', 'api_key_required': False,
                         'base_url': driver.ENDPOINTS[0], 'reasoning_protocol': 'qwen',
                         'local_model_endpoints': {driver.MODEL: driver.ENDPOINTS[0]}},
                'agent': {'guidance_profile': 'e3', 'loop_recovery': True}}
    (root/'deployment/config.e6.final.json').write_text(json.dumps(override))
    (root/'experiments/E5/e6-final-selection.json').write_text(json.dumps({'selected_profile': 'e3'}))
    monkeypatch.setattr(driver.time, 'sleep', lambda seconds: None)
    return root


def reserved(project):
    return sorted((project/'runs').glob('e7-*'))


def assert_terminal(project, count):
    directories = reserved(project)
    assert len(directories) == count
    for directory in directories:
        result = benchmark.read_json(directory/'result.json')
        metadata = benchmark.read_json(directory/'web.json')
        assert result['status'] not in ('queued', 'starting', 'running', 'evaluating')
        assert metadata['status'] not in ('queued', 'starting', 'running', 'evaluating')
        assert metadata['worker_pid'] is None and metadata['finished_at']
    return directories


def assert_no_outputs(project):
    assert not reserved(project)
    assert not list((project/'experiments/E5').glob('e7-*'))


def test_preflight_checks_all_endpoints_without_creating_runs(project):
    opener = Opener()
    driver.preflight(driver.plans(project), opener=opener)
    assert opener.calls == [endpoint+'/models' for endpoint in driver.ENDPOINTS] + [driver.SYMBOLIC_ENDPOINT+'/health']
    assert_no_outputs(project)


@pytest.mark.parametrize('url,value,expected', [
    (driver.ENDPOINTS[3]+'/models', {'data': [{'id': 'other-model'}]}, 'expected qwen3.8-27b'),
    (driver.ENDPOINTS[1]+'/models', OSError('synthetic private failure'), 'endpoint unavailable or invalid'),
    (driver.SYMBOLIC_ENDPOINT+'/health', {'ready': 3, 'busy': 0}, 'four ready, idle'),
    (driver.SYMBOLIC_ENDPOINT+'/health', {'ready': 4, 'busy': 1}, 'four ready, idle'),
    (driver.SYMBOLIC_ENDPOINT+'/health', {'ready': 4, 'busy': False}, 'four ready, idle'),
])
def test_failed_service_preflight_creates_no_universe_runs(project, url, value, expected):
    with pytest.raises(RuntimeError, match=expected) as error:
        driver.run_study(project, opener=Opener({url: value}))
    assert 'synthetic private' not in str(error.value)
    assert_no_outputs(project)


@pytest.mark.parametrize('target_kind', ['output', 'run', 'broken_symlink'])
def test_preflight_detects_collision_in_last_arm_before_any_reservation(project, target_kind):
    planned = driver.plans(project)
    target = (planned[-1]['output'] if target_kind == 'output'
              else planned[-1]['planned_runs']['world_6'])
    target.parent.mkdir(parents=True, exist_ok=True)
    if target_kind == 'broken_symlink':
        target.symlink_to(target.parent/'missing-target')
    else:
        target.mkdir()
        (target/'preserved.txt').write_text('existing artifact')
    before = set(project.rglob('*'))
    opener = Opener()
    with pytest.raises(ValueError, match='already_exists_no_overwrite'):
        driver.run_study(project, opener=opener)
    assert set(project.rglob('*')) == before and not opener.calls


def test_partial_second_prepare_finalizes_every_reserved_run(project, monkeypatch):
    real_prepare = driver.prepare
    calls = []
    def failing_prepare(output, config, **kwargs):
        calls.append(output)
        if len(calls) == 2:
            output.mkdir(parents=True)
            directory = project/'runs'/f'{output.name}-world_1'
            directory.mkdir()
            raise OSError('synthetic prepare failed before config write')
        return real_prepare(output, config, **kwargs)
    monkeypatch.setattr(driver, 'prepare', failing_prepare)
    monkeypatch.setattr(driver, 'launch', lambda *args: pytest.fail('Preparation must finish before any launch'))
    with pytest.raises(OSError, match='prepare failed'):
        driver.run_study(project, opener=Opener())
    assert_terminal(project, 7)
    summaries = [benchmark.read_json(path/'summary.json') for path in calls]
    assert all(summary['status'] == 'interrupted' for summary in summaries)
    assert summaries[1]['preparation_complete'] is False
    assert len(summaries[1]['worlds']) == 1 and len(summaries[1]['unreserved_worlds']) == 5
    assert len(list((project/'experiments/E5').glob('e7-*'))) == 2


@pytest.mark.parametrize('collision_kind', ['initial_check', 'output_mkdir', 'run_mkdir'])
def test_reservation_race_does_not_finalize_another_drivers_run(project, monkeypatch, collision_kind):
    preserved = {}
    def collision_prepare(output, config, **kwargs):
        output.mkdir(parents=True)
        directory = project/'runs'/f'{output.name}-world_1'
        directory.mkdir(parents=True)
        for path in (output/'manifest.json', directory/'web.json'):
            path.write_text(json.dumps({'status': 'running', 'owner': 'another-driver'}))
            preserved[path] = path.read_bytes()
        if collision_kind == 'initial_check':
            raise ValueError('experiment_or_run_directory_already_exists_no_overwrite')
        if collision_kind == 'output_mkdir':
            raise FileExistsError(17, 'File exists', str(output))
        # Here the output belongs to this driver, but the colliding run does not.
        preserved.pop(output/'manifest.json')
        raise FileExistsError(17, 'File exists', str(directory))
    monkeypatch.setattr(driver, 'prepare', collision_prepare)
    with pytest.raises((ValueError, FileExistsError)):
        driver.run_study(project, opener=Opener())
    assert all(path.read_bytes() == content for path, content in preserved.items())
    assert not any(path.is_file() for path in (project/'runs').glob('*/result.json'))


class Process:
    def __init__(self, endpoint, *, running=False):
        self.endpoint, self.running = endpoint, running
        self.returncode = None if running else 0
        self.waited = self.terminated = False

    def poll(self):
        return self.returncode

    def wait(self):
        self.waited = True
        return self.returncode


def fake_launch(directory, api_key, project, *, running=False):
    assert api_key == ''
    config = benchmark.read_json(directory/'config.json')
    process = Process(config['model']['base_url'], running=running)
    if not running:
        benchmark._write(directory/'result.json', {'status': 'incomplete', 'reason': 'synthetic_worker_result',
            'submission': None, 'model_usage': {'calls': 0, 'completion_tokens': 0},
            'budget': {'energy_remaining': 10, 'wall_seconds_remaining': 290}})
    return process


def stop_process(process):
    process.terminated = True
    process.returncode = -15


def test_dispatch_config_failure_still_marks_popped_attempt_and_all_reserved_runs(project, monkeypatch):
    original_write = driver._write
    def failing_write(path, value):
        if path.name == 'config.json':
            raise OSError('synthetic dispatch write failed')
        return original_write(path, value)
    monkeypatch.setattr(driver, '_write', failing_write)
    monkeypatch.setattr(driver, 'launch', lambda *args: pytest.fail('No launch after dispatch write failure'))
    with pytest.raises(OSError, match='dispatch write failed'):
        driver.run_study(project, opener=Opener())
    assert_terminal(project, 24)
    assert all(benchmark.read_json(path/'summary.json')['status'] == 'interrupted'
               for path in (project/'experiments/E5').glob('e7-*'))


def test_stop_during_launch_registers_process_before_cleanup_and_closes_manager(project, monkeypatch):
    stopped, processes, managers = [], [], []
    original_manager = driver.RunManager
    class Manager(original_manager):
        def __init__(self, *args):
            super().__init__(*args)
            managers.append(self)
    def launch(*args):
        process = fake_launch(*args, running=True)
        processes.append(process)
        stopped.append(True)
        return process
    monkeypatch.setattr(driver, 'RunManager', Manager)
    monkeypatch.setattr(driver, 'launch', launch)
    monkeypatch.setattr(driver, 'terminate', stop_process)
    with pytest.raises(KeyboardInterrupt, match='stop requested'):
        driver.run_study(project, opener=Opener(), stop_requested=lambda: bool(stopped))
    assert len(processes) == 1 and processes[0].terminated
    assert managers[0]._closed
    directories = assert_terminal(project, 24)
    reasons = [benchmark.read_json(path/'result.json')['reason'] for path in directories]
    assert reasons.count('study_interrupted') == 1
    assert reasons.count('not_started_study_interrupted') == 23


def test_one_hour_deadline_terminates_owned_worker_and_keeps_all_attempts(project, monkeypatch):
    current, processes = [100.0], []
    monkeypatch.setattr(driver.time, 'monotonic', lambda: current[0])
    def launch(*args):
        process = fake_launch(*args, running=True)
        processes.append(process)
        current[0] += 3601
        return process
    monkeypatch.setattr(driver, 'launch', launch)
    monkeypatch.setattr(driver, 'terminate', stop_process)
    with pytest.raises(TimeoutError, match='one-hour'):
        driver.run_study(project, opener=Opener())
    assert len(processes) == 1 and processes[0].terminated
    assert_terminal(project, 24)


def test_launch_failure_is_retained_without_retry_and_other_worlds_finish(project, monkeypatch):
    calls = []
    def launch(*args):
        calls.append(args[0].name)
        if len(calls) == 1:
            raise OSError('synthetic launch failed')
        return fake_launch(*args)
    monkeypatch.setattr(driver, 'launch', launch)
    driver.run_study(project, opener=Opener())
    assert len(calls) == len(set(calls)) == 24
    directories = assert_terminal(project, 24)
    results = [benchmark.read_json(path/'result.json') for path in directories]
    assert sum(result['reason'] == 'worker_start_failed' for result in results) == 1
    assert all(benchmark.read_json(path/'summary.json')['status'] == 'completed'
               for path in (project/'experiments/E5').glob('e7-*'))


def test_interleaved_attempts_never_share_an_active_endpoint(project, monkeypatch):
    busy, calls = set(), []
    class DelayedProcess(Process):
        def __init__(self, endpoint):
            super().__init__(endpoint, running=True)
            self.polls = 0
        def poll(self):
            self.polls += 1
            if self.polls == 1:
                return None
            busy.remove(self.endpoint)
            self.returncode = 0
            return 0
    def launch(directory, key, root):
        endpoint = benchmark.read_json(directory/'config.json')['model']['base_url']
        assert endpoint not in busy
        busy.add(endpoint)
        calls.append((directory.name, endpoint))
        fake_launch(directory, key, root)
        return DelayedProcess(endpoint)
    monkeypatch.setattr(driver, 'launch', launch)
    driver.run_study(project, opener=Opener())
    assert len(calls) == len({name for name, endpoint in calls}) == 24 and not busy
    assert {endpoint for name, endpoint in calls} == set(driver.ENDPOINTS)
    assert [name.rsplit('-', 1)[-1] for name, _ in calls[:4]] == ['world_1'] * 4
    assert ['-pysr-on-' in name for name, _ in calls[:4]] == [False, True, True, False]
    assert_terminal(project, 24)


def test_cleanup_failure_does_not_skip_remaining_attempts_or_hide_original_error(project, monkeypatch, capsys):
    stopped, calls = [], []
    original_finished = driver.finished
    def launch(*args):
        stopped.append(True)
        return fake_launch(*args, running=True)
    def finish(directory, *args, **kwargs):
        calls.append(directory.name)
        if len(calls) == 1:
            raise OSError('synthetic persistent filesystem failure')
        return original_finished(directory, *args, **kwargs)
    monkeypatch.setattr(driver, 'launch', launch)
    monkeypatch.setattr(driver, 'terminate', stop_process)
    monkeypatch.setattr(driver, 'finished', finish)
    with pytest.raises(KeyboardInterrupt) as error:
        driver.run_study(project, opener=Opener(), stop_requested=lambda: bool(stopped))
    assert len(calls) == len(set(calls)) == 24
    diagnostics = '\n'.join(getattr(error.value, '__notes__', [])) + capsys.readouterr().err
    assert 'E7 cleanup incomplete: finish:' in diagnostics
    assert all(benchmark.read_json(path/'result.json') is not None for path in reserved(project)
               if path.name != calls[0])


def test_main_defers_sigterm_until_safe_checkpoint_and_restores_handlers(monkeypatch):
    installed, originals = {}, {signal.SIGTERM: object(), signal.SIGINT: object()}
    def set_signal(sig, handler):
        previous = installed.get(sig, originals[sig])
        installed[sig] = handler
        return previous
    def run_study(*, stop_requested):
        assert not stop_requested()
        installed[signal.SIGTERM](signal.SIGTERM, None)
        assert stop_requested()
    monkeypatch.setattr(driver.signal, 'signal', set_signal)
    monkeypatch.setattr(driver, 'run_study', run_study)
    driver.main()
    assert installed == originals


def test_predeclared_single_batch_reuses_cleanup_and_records_extra_sources(project,monkeypatch):
    plan=driver.plans(project)[0]
    plan['experiment_group']='E8'
    plan['symbolic_runtime_preflight']={'actual_threads':4}
    source=project/'deployment/generic_basis.py'
    source.write_text('generic implementation')
    (project/'experiments/E5/e6-final-selection.json').unlink()
    calls=[]
    def launch(*args):
        calls.append(args[0].name)
        return fake_launch(*args)
    monkeypatch.setattr(driver,'launch',launch)
    driver.run_study(project,opener=Opener(),planned_batches=[plan],
                     extra_source_paths=['deployment/generic_basis.py'])
    assert len(calls)==len(set(calls))==6
    manifest=benchmark.read_json(plan['output']/'manifest.json')
    assert manifest['experiment_group']=='E8'
    assert manifest['symbolic_runtime_preflight']['actual_threads']==4
    assert len(manifest['source_sha256']['deployment/generic_basis.py'])==64
    for directory in assert_terminal(project,6):
        assert benchmark.read_json(directory/'web.json')['experiment_group']=='E8'


def test_explicit_replica_subset_is_used_in_dispatch_and_manifest(project,monkeypatch):
    endpoints=driver.ENDPOINTS[1:];calls=[]
    def launch(directory,key,root):
        calls.append(benchmark.read_json(directory/'config.json')['model']['base_url'])
        return fake_launch(directory,key,root)
    monkeypatch.setattr(driver,'launch',launch)
    driver.run_study(project,opener=Opener(),model_endpoints=endpoints)
    assert len(calls)==24
    assert set(calls)==set(endpoints)
    assert_terminal(project,24)
    for p in (project/'experiments/E5').glob('e7-*'):
        manifest=benchmark.read_json(p/'manifest.json')
        assert manifest['workers']==3
