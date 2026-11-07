"""Deadline/atomic draft tests use synthetic model decisions, never real inference."""
import copy
import json
import io
import sys
import signal
import time

import pytest

from shore_agent.agent import Agent
from shore_agent.environment import Environment
from shore_agent.model import ModelError
from shore_agent.runtime import ToolRuntime
from shore_agent.schemas import SCHEMAS, tool_schemas
from shore_agent.web_jobs import accepted_submission
from shore_agent.web_worker import ExplorationDeadline, exploration_watchdog


CLAIMS = {'dynamics_order': 2, 'hidden_matter': False, 'time_dependence': False}


@pytest.fixture(params=['e4', 'e5'])
def runtime(tmp_path, request):
    # The real legacy observation worker provides arbitrary data for format-only
    # draft checks. Test declarations below make no scientific correctness claim.
    env = Environment({'noise': False, 'seed': 12})
    env.ruleset = request.param
    rt = ToolRuntime(env, tmp_path)
    assert rt.mission()['ok']
    rt.exploration_started_monotonic = time.monotonic()
    rt.exploration_deadline_monotonic = time.monotonic() + 300
    law = rt.execute('fit_law_and_rollout', {'law_spec': {'ax': '0', 'ay': '0'},
                     'parameter_spec': [], 'train_probe_ids': list(rt.store.records['probe'])})
    assert law['ok'], law
    rt.test_law_id = law['data']['law_id']
    yield rt
    env.close()


def save(rt, **changes):
    args = {'law_id': rt.test_law_id, 'claims': copy.deepcopy(CLAIMS),
            'physical_explanation': 'Synthetic engineering fixture; not a scientific answer.'}
    args.update(changes)
    return rt.execute('save_draft', args)


def test_e3_tool_surface_unchanged():
    assert tool_schemas() == SCHEMAS
    assert len(SCHEMAS) == 8
    assert [s['function']['name'] for s in tool_schemas(ruleset='e4')][-1] == 'save_draft'


def test_only_explicit_timely_valid_pair_replaces_draft(runtime, monkeypatch):
    assert not save(runtime, claims={})['ok']
    assert runtime.last_valid_draft is None
    first = save(runtime)
    assert first['ok'] and first['data']['status'] == 'saved'
    assert accepted_submission(runtime.run_dir) is None
    assert not runtime.session_ended
    original = copy.deepcopy(runtime.last_valid_draft)
    assert not save(runtime, law_id='absent')['ok']
    assert runtime.last_valid_draft == original
    monkeypatch.setattr(runtime, 'exploration_deadline_monotonic', time.monotonic()-1)
    assert not save(runtime)['ok']
    assert runtime.last_valid_draft == original
    assert json.loads((runtime.run_dir/'latest_draft.json').read_text()) == original


def test_deadline_seals_exact_saved_pair_without_new_validation(runtime, monkeypatch):
    first = save(runtime)['data']
    source = runtime.run_dir/'drafts'/first['draft_id']/'law.py'
    saved_bytes = source.read_bytes()
    # A later proposed law does not replace the explicit model-selected draft.
    runtime.execute('fit_law_and_rollout', {'law_spec': {'ax': 'vx', 'ay': 'vy'},
                    'parameter_spec': [], 'train_probe_ids': list(runtime.store.records['probe'])})
    monkeypatch.setattr(runtime, 'budget', lambda: {'wall_seconds_remaining': 0, 'session_ended': True})
    from shore_agent import submission
    monkeypatch.setattr(submission, 'export_submission', lambda *a, **k: pytest.fail('must not revalidate after deadline'))
    data = runtime.finalize_draft('wall_time_exhausted')
    assert data['law_id'] == first['law_id'] and data['claims'] == CLAIMS
    assert data['draft_saved_at'] == first['saved_at']
    assert data['submission_deadline_met'] is True
    assert data['pair_validated_elapsed_seconds'] == first['pair_validated_elapsed_seconds']
    assert accepted_submission(runtime.run_dir)['submission_id'] == data['submission_id']
    assert (runtime.run_dir/'submissions'/data['submission_id']/'law.py').read_bytes() == saved_bytes


class FailedClient:
    usage = {'calls': 1, 'completion_tokens': 0, 'total_tokens': 0}
    last_finish_reason = None

    def remaining_seconds(self):
        return 100

    def complete(self, *args, **kwargs):
        raise ModelError('api_timeout')


def test_failure_without_draft_is_honestly_incomplete(runtime):
    result = Agent(FailedClient(), runtime, runtime.run_dir, {}).run()
    assert result['status'] == 'incomplete' and result['submission'] is None
    assert accepted_submission(runtime.run_dir) is None


def test_model_failure_preserves_prior_model_selected_draft(runtime):
    first = save(runtime)['data']
    result = Agent(FailedClient(), runtime, runtime.run_dir, {}).run()
    if runtime.ruleset=='e4':
        assert result['status']=='incomplete' and result['submission'] is None
        assert runtime.last_valid_draft['draft_id']==first['draft_id']
        assert not result['draft_finalization_blocked_by_submission_gate']['allowed']
    else:
        assert result['status'] == 'submitted'
        assert result['reason'] == 'saved_draft_after_api_timeout'
        assert result['submission']['draft_id'] == first['draft_id']


def test_finish_reserve_uses_saved_pair_without_another_model_call(runtime, monkeypatch):
    save(runtime)
    old_budget = runtime.budget
    monkeypatch.setattr(runtime, 'budget', lambda: dict(old_budget(), wall_seconds_remaining=25))
    client = FailedClient()
    monkeypatch.setattr(client, 'complete', lambda *a, **k: pytest.fail('reserve must not start another model call'))
    result = Agent(client, runtime, runtime.run_dir, {}).run()
    assert result['status'] == 'submitted'
    assert result['reason'] == ('mandatory_noisy_deadline_submit' if runtime.ruleset=='e4' else 'deadline_saved_draft')


def test_watchdog_cannot_be_swallowed_by_tool_exception_handlers():
    previous = signal.getsignal(signal.SIGALRM)
    with pytest.raises(ExplorationDeadline):
        with exploration_watchdog(.02, enabled=True):
            try:
                time.sleep(.2)
            except Exception:
                pytest.fail('deadline must bypass broad tool exception handling')
    assert signal.getsignal(signal.SIGALRM) == previous
    assert signal.getitimer(signal.ITIMER_REAL)[0] == 0
    # Independent evaluation is outside the context and has no exploration alarm.
    time.sleep(.03)


def test_legacy_environment_metadata_is_not_forwarded_to_old_simulator():
    with Environment({'ruleset': 'e3', 'energy_budget': 100, 'noise': False}) as env:
        assert env.request('mission')['ok']
    with pytest.raises(ValueError, match='requires v15'):
        Environment({'ruleset': 'e4'})


@pytest.mark.parametrize('submitted', [False, True])
@pytest.mark.parametrize('ruleset', ['e4', 'e5'])
def test_worker_deadline_and_post_session_evaluation_are_separate(tmp_path, monkeypatch, submitted, ruleset):
    from shore_agent import agent, environment, model, runtime as runtime_module, web_worker
    (tmp_path/'config.json').write_text(json.dumps({'environment': {'world_set': 'v15', 'ruleset': ruleset},
        'model': {'deployment': 'local', 'base_url': 'http://127.0.0.1:8000/v1',
                  'api_key_required': False}}))
    monkeypatch.setattr(sys, 'stdin', io.StringIO('{"api_key":""}\n'))
    class EnvironmentStub:
        def __init__(self, *a, **k): pass
        def close(self): pass
    class RuntimeStub:
        def __init__(self, *a, **k): pass
        def mission(self):
            return {'ok': True, 'budget': {'wall_seconds_remaining': .05}}
        def budget(self): return {'wall_seconds_remaining': .05}
    class ClientStub:
        def __init__(self, config, *a, **k):
            assert config['ruleset'] == ruleset and config['max_tokens_per_call'] == 4096
        def close(self): pass
    class AgentStub:
        def __init__(self, *a, **k): pass
        def run(self):
            if not submitted:
                time.sleep(.3)
                pytest.fail('worker watchdog did not interrupt model/tool work')
            return {'status': 'submitted', 'submission': {'submission_deadline_met': True,
                                                        'pair_validated_elapsed_seconds': .01}}
        def _finish(self, status, reason):
            assert status == 'incomplete' and reason == 'wall_time_exhausted_without_saved_draft'
            return {'status': status, 'reason': reason, 'submission': None}
    monkeypatch.setattr(environment, 'Environment', EnvironmentStub)
    monkeypatch.setattr(runtime_module, 'ToolRuntime', RuntimeStub)
    monkeypatch.setattr(model, 'DeepSeekClient', ClientStub)
    monkeypatch.setattr(agent, 'Agent', AgentStub)
    monkeypatch.setattr(web_worker, 'accepted_submission', lambda p: {'status': 'accepted'} if submitted else None)
    evaluations = []
    def evaluate(*a, **k):
        assert signal.getitimer(signal.ITIMER_REAL)[0] == 0
        metadata = json.loads((tmp_path/'web.json').read_text())
        assert metadata['status'] == 'evaluating' and metadata['exploration_finished_at']
        time.sleep(.08)  # Longer than exploration's test deadline, with no alarm.
        evaluations.append(True)
        return type('Result', (), {'returncode': 0})()
    monkeypatch.setattr(web_worker.subprocess, 'run', evaluate)
    assert web_worker.run(tmp_path) == 0
    metadata = json.loads((tmp_path/'web.json').read_text())
    assert metadata['exploration_wall_seconds'] < .2
    assert bool(evaluations) == submitted
    if submitted:
        assert metadata['submission_deadline_met'] is True
        assert metadata['evaluation_wall_seconds'] >= .08
    else:
        assert metadata['status'] == 'incomplete' and 'evaluation_started_at' not in metadata


@pytest.mark.parametrize('ruleset', ['e4', 'e5'])
def test_cli_e4_reuses_worker_without_parent_mission_or_secret_argv(tmp_path, monkeypatch, ruleset):
    from shore_agent import cli
    config = tmp_path/'input.json'
    config.write_text(json.dumps({'environment': {'world_set': 'v15', 'world_id': 'world_1',
        'ruleset': ruleset, 'wall_seconds': 3600, 'noise': False}, 'model': {
        'deployment': 'local', 'base_url': 'http://127.0.0.1:8000/v1', 'api_key_required': False,
        'api_key_env': 'E4_TEST_KEY', 'max_tokens_per_call': 65536}}))
    directory = tmp_path/'run'
    monkeypatch.setenv('E4_TEST_KEY', 'synthetic-cli-secret')
    monkeypatch.setattr(sys, 'argv', ['shore', 'run', '--config', str(config), '--run-dir', str(directory)])
    monkeypatch.setattr(cli, 'Environment', lambda *a, **k: pytest.fail('parent must not call mission'))
    observed = []
    def launch(args, **kwargs):
        assert args[-2:] == ['--run-dir', str(directory.resolve())]
        assert 'shore_agent.web_worker' in args
        assert 'synthetic-cli-secret' not in repr(args) and 'E4_TEST_KEY' not in kwargs['env']
        assert json.loads(kwargs['input']) == {'api_key': 'synthetic-cli-secret'}
        saved = json.loads((directory/'config.json').read_text())
        assert saved['model']['max_tokens_per_call'] == 4096
        assert saved['environment']['wall_seconds'] == 300 and saved['environment']['noise'] is (ruleset == 'e4')
        observed.append(True)
        return type('Process', (), {'returncode': 0})()
    monkeypatch.setattr(cli.subprocess, 'run', launch)
    cli.main()
    assert observed == [True]
