"""Loop recovery changes control flow, never the physical tools or hypotheses."""
import copy
import json
from types import SimpleNamespace

import pytest

from shore_agent.agent import Agent
from shore_agent.model import ModelError
from shore_agent.schemas import tool_schemas
from shore_agent.store import Store
from shore_agent.workspace import SessionFiles


def call(name='read_file', args=None, ident='c1', raw=None):
    return {'id': ident, 'type': 'function', 'function': {'name': name,
            'arguments': raw if raw is not None else json.dumps(args if args is not None else {'path': 'data.json'})}}


def reply(*calls, finish='tool_calls', content=None):
    return {'message': {'role': 'assistant', 'content': content, 'tool_calls': list(calls)}, 'finish': finish}


class Client:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.usage = {'calls': 0, 'completion_tokens': 0, 'total_tokens': 0}
        self.last_finish_reason = None
        self.requests = []

    def remaining_seconds(self):
        return 200

    def complete(self, messages, tools=None, role='main'):
        self.requests.append(copy.deepcopy({'messages': messages, 'tools': tools}))
        try:
            item = next(self.replies)
        except StopIteration:
            raise ModelError('test_exhausted')
        self.usage['calls'] += 1
        self.usage['completion_tokens'] += 4096 if item['finish'] == 'length' else 50
        self.last_finish_reason = item['finish']
        return copy.deepcopy(item['message'])


class Runtime:
    ruleset = 'e5'
    code_enabled = False

    def __init__(self, fail=False, draft=False, fresh_observations=True):
        self.schemas = tool_schemas(ruleset=self.ruleset)
        self.calls = []
        self.fail = fail
        self.fresh_observations = fresh_observations
        self.last_valid_draft = {'law_id': 'saved-law'} if draft else None
        self.store = SimpleNamespace(records={'probe': {'initial': {}}, 'body_observation': {'initial': {}}})

    def budget(self):
        return {'wall_seconds_remaining': 200, 'energy_remaining': 7, 'session_ended': False}

    def mission(self):
        return {'ok': True, 'data': {}, 'budget': self.budget()}

    def execute(self, name, args):
        self.calls.append((name, copy.deepcopy(args)))
        if name == 'submit':
            return {'ok': True, 'data': {'status': 'accepted', 'session_ended': True, 'law_id': 'submitted-law'},
                    'budget': self.budget()}
        failed = self.fail(name, args, len(self.calls)) if callable(self.fail) else self.fail
        if failed:
            return {'ok': False, 'error': {'code': 'invalid_input', 'message': 'observed fixture failure'},
                    'data': None, 'budget': self.budget()}
        if name in ('insert_probe', 'observe_body') and self.fresh_observations:
            kind = 'probe' if name == 'insert_probe' else 'body_observation'
            self.store.records[kind][str(len(self.calls))] = {}
        # Deliberately changing synthetic IDs must not appear as new evidence.
        data = {'law_id': f'law_{len(self.calls)}', 'validation_id': f'validation_{len(self.calls)}'}
        return {'ok': True, 'data': data, 'budget': self.budget()}

    def finalize_draft(self, reason):
        if self.last_valid_draft:
            return {'status': 'accepted', 'session_ended': True, **self.last_valid_draft}
        return None


class FileRuntime(Runtime):
    """Use the real public file registry to exercise non-observation changes."""
    def __init__(self, directory):
        super().__init__()
        self.store = Store(directory / 'records')
        self.store.add('probe', {'sample': 1}, 'initial')
        self.store.add('law', {'sample': 'existing'}, 'existing')
        self.files = SessionFiles(self.store, directory)

    def execute(self, name, args):
        if name in ('read_file', 'list_files'):
            self.calls.append((name, copy.deepcopy(args)))
            try:
                return {'ok': True, 'data': getattr(self.files, name)(**args), 'budget': self.budget()}
            except ValueError as exc:
                return {'ok': False, 'data': None, 'error': {'code': 'workspace_error', 'message': str(exc)},
                        'budget': self.budget()}
        response = super().execute(name, args)
        if name == 'fit_law_and_rollout':
            self.store.add('law', {'source': copy.deepcopy(args)}, response['data']['law_id'])
        if name == 'validate_law':
            self.store.add('validation', {'source': copy.deepcopy(args)}, response['data']['validation_id'])
        return response


def run(tmp_path, runtime, replies, config=None):
    client = Client(replies)
    agent = Agent(client, runtime, tmp_path, {'loop_recovery': True, **(config or {})})
    result = agent.run()
    return result, client, agent


def events(directory):
    return [json.loads(line) for line in (directory/'events.jsonl').read_text().splitlines()]


def test_identical_failure_has_one_actual_retry_then_bounded_stop_and_auditable_feedback(tmp_path):
    runtime = Runtime(fail=True)
    result, client, agent = run(tmp_path, runtime, [reply(call(ident=str(i))) for i in range(10)])
    assert len(runtime.calls) == 2 and client.usage['calls'] == 4
    assert result['reason'] == 'repeated_tool_failure_limit' and result['status'] == 'incomplete'
    feedback = [e for e in events(tmp_path) if e['event'] == 'loop_recovery_feedback']
    assert [e['same_error_failures'] for e in feedback] == [1, 2]
    assert feedback[1]['last_error']['code'] == 'invalid_input'
    assert feedback[1]['budget']['energy_remaining'] == 7
    assert '工具调用恢复反馈' in client.requests[1]['messages'][-1]['content']
    assert result['model_usage'] == client.usage
    assert all(request['tools'] == runtime.schemas for request in client.requests)


def test_canonical_json_keys_and_integral_float_representations_share_repeat_identity(tmp_path):
    runtime = Runtime(fail=True)
    raw = ['{"offset":1,"path":"same"}', '{"path":"same", "offset":1.0}', '{"offset":1, "path":"same"}', '{"offset":1.0,"path":"same"}']
    result, _, _ = run(tmp_path, runtime, [reply(call(raw=value, ident=str(i))) for i,value in enumerate(raw)])
    assert len(runtime.calls) == 2 and result['reason'] == 'repeated_tool_failure_limit'


@pytest.mark.parametrize('name', ['read_file', 'list_files', 'fit_law_and_rollout', 'validate_law', 'analyze_residual'])
def test_successful_deterministic_repetition_ignores_new_record_ids(tmp_path, name):
    runtime = Runtime()
    result, _, _ = run(tmp_path, runtime, [reply(call(name, {}, ident=str(i))) for i in range(5)])
    assert len(runtime.calls) == 2
    assert result['reason'] == 'repeated_deterministic_call_limit'
    feedback = [e for e in events(tmp_path) if e['event'] == 'loop_recovery_feedback']
    assert len(feedback) == 1 and feedback[0]['identical_attempts_without_new_observations'] == 2


@pytest.mark.parametrize('observation', ['insert_probe', 'observe_body'])
def test_new_acquired_observation_resets_old_fit_identity(tmp_path, observation):
    runtime = Runtime()
    replies = [reply(call('fit_law_and_rollout', {}, ident='a')),
               reply(call('fit_law_and_rollout', {}, ident='b')),
               reply(call(observation, {}, ident='c')),
               reply(call('fit_law_and_rollout', {}, ident='d')),
               reply(call('submit', {}, ident='e'))]
    result, _, _ = run(tmp_path, runtime, replies)
    assert result['status'] == 'submitted'
    assert [name for name, _ in runtime.calls].count('fit_law_and_rollout') == 3


def test_cached_body_observation_does_not_reset_deterministic_loop(tmp_path):
    runtime = Runtime(fresh_observations=False)
    result, _, _ = run(tmp_path, runtime, [reply(call('read_file', ident='a')), reply(call('read_file', ident='b')),
        reply(call('observe_body', {}, ident='c')), reply(call('read_file', ident='d')), reply(call('read_file', ident='e'))])
    assert result['reason'] == 'repeated_deterministic_call_limit'
    assert len(runtime.calls) == 3


def test_successful_repeated_probe_deployments_remain_allowed_for_noise_statistics(tmp_path):
    runtime = Runtime()
    result, _, _ = run(tmp_path, runtime, [reply(call('insert_probe', {}, ident=str(i))) for i in range(5)] +
                       [reply(call('submit', {}, ident='submit'))])
    assert result['status'] == 'submitted'
    assert len(runtime.calls) == 6


def test_cached_body_read_loop_is_bounded_but_fresh_body_measurements_are_allowed(tmp_path):
    cached = Runtime(fresh_observations=False)
    result, _, _ = run(tmp_path/'cached', cached, [reply(call('observe_body', {}, ident=str(i))) for i in range(4)])
    assert result['reason'] == 'repeated_deterministic_call_limit' and len(cached.calls) == 2
    fresh = Runtime()
    result, _, _ = run(tmp_path/'fresh', fresh, [reply(call('observe_body', {}, ident=str(i))) for i in range(5)] +
                       [reply(call('submit', {}, ident='submit'))])
    assert result['status'] == 'submitted' and len(fresh.calls) == 6


def test_failed_probe_deployments_do_not_receive_the_success_exemption(tmp_path):
    runtime = Runtime(fail=True)
    result, _, _ = run(tmp_path, runtime, [reply(call('insert_probe', {}, ident=str(i))) for i in range(4)])
    assert result['reason'] == 'repeated_tool_failure_limit'
    assert len(runtime.calls) == 2


def test_volatile_error_message_cannot_bypass_same_failure_limit(tmp_path):
    class VolatileRuntime(Runtime):
        def execute(self, name, args):
            result = super().execute(name, args)
            result['error']['message'] += f' (request {len(self.calls)})'
            return result
    runtime = VolatileRuntime(fail=True)
    result, _, _ = run(tmp_path, runtime, [reply(call('insert_probe', {}, ident=str(i))) for i in range(4)])
    assert result['reason'] == 'repeated_tool_failure_limit' and len(runtime.calls) == 2


def test_other_operation_or_changed_arguments_can_continue_after_feedback(tmp_path):
    runtime = Runtime(fail=lambda name, args, _: args.get('path') == 'wrong')
    result, _, _ = run(tmp_path, runtime, [reply(call(args={'path':'wrong'}, ident='a')),
        reply(call(args={'path':'wrong'}, ident='b')), reply(call(args={'path':'correct'}, ident='c')),
        reply(call('submit', {}, ident='d'))])
    assert result['status'] == 'submitted' and len(runtime.calls) == 4


def test_repeated_failures_cannot_evade_guard_by_interleaving_unrelated_reads(tmp_path):
    runtime = Runtime(fail=lambda name, args, _: args.get('path') == 'wrong')
    result, _, _ = run(tmp_path, runtime, [reply(call(args={'path':'wrong'}, ident='a')),
        reply(call(args={'path':'different'}, ident='b')), reply(call(args={'path':'wrong'}, ident='c')),
        reply(call(args={'path':'wrong'}, ident='d')), reply(call(args={'path':'wrong'}, ident='e'))])
    assert result['reason'] == 'repeated_tool_failure_limit' and len(runtime.calls) == 3


def test_batch_protocol_is_complete_after_guard_skips_remaining_calls_and_preserves_draft(tmp_path):
    runtime = Runtime(fail=True, draft=True)
    calls = [call(ident=str(i)) for i in range(10)]
    result, client, agent = run(tmp_path, runtime, [reply(*calls), reply(call(ident='next-turn'))])
    assert result['reason'] == 'saved_draft_after_repeated_tool_failure_limit'
    assert result['submission']['law_id'] == 'saved-law'
    assert len(runtime.calls) == 2
    assert client.usage['calls'] == 2
    assert [m['tool_call_id'] for m in agent.messages if m['role']=='tool'] == [c['id'] for c in calls] + ['next-turn']


def test_repeated_invalid_json_is_bounded_without_executing_any_tool(tmp_path):
    runtime = Runtime()
    result, _, _ = run(tmp_path, runtime, [reply(call(raw='{', ident=str(i))) for i in range(4)])
    assert result['reason'] == 'repeated_tool_failure_limit' and runtime.calls == []


def test_length_recovers_once_discards_incomplete_calls_and_keeps_usage_and_audit(tmp_path):
    runtime = Runtime()
    incomplete = reply(call('insert_probe', raw='{"probes":', ident='broken'), finish='length', content='partial')
    result, client, _ = run(tmp_path, runtime, [incomplete, reply(call('submit', {}, ident='ok'))])
    assert result['status'] == 'submitted'
    assert [name for name, _ in runtime.calls] == ['submit']
    assert client.usage['completion_tokens'] == 4146
    second = client.requests[1]['messages']
    assert not any(m.get('tool_calls') for m in second)
    assert '4096' in second[-1]['content']
    audit = next(e for e in events(tmp_path) if e['event'] == 'model_length_recovery')
    assert audit['discarded_message']['tool_calls'][0]['id'] == 'broken'


def test_second_length_is_finite_and_saves_existing_draft(tmp_path):
    runtime = Runtime(draft=True)
    result, client, _ = run(tmp_path, runtime, [reply(finish='length'), reply(finish='length')])
    assert result['reason'] == 'saved_draft_after_model_finish_length_recovery_exhausted'
    assert client.usage['calls'] == 2 and runtime.calls == []


def test_default_flag_off_preserves_historical_repetition_and_length_behavior(tmp_path):
    runtime = Runtime(fail=True)
    result, client, _ = run(tmp_path, runtime, [reply(call(ident=str(i))) for i in range(4)] +
                           [reply(finish='length')], {'loop_recovery': False})
    assert len(runtime.calls) == 4 and client.usage['calls'] == 5
    assert result['reason'] == 'model_finish_length'
    assert not any(e['event'].startswith('loop_recovery') for e in events(tmp_path))


def test_first_block_is_a_recovery_opportunity_and_changed_action_can_finish(tmp_path):
    runtime = Runtime(fail=lambda name, args, _: args.get('path') == 'wrong')
    result, client, _ = run(tmp_path, runtime, [reply(call(args={'path':'wrong'}, ident=str(i))) for i in range(3)] +
        [reply(call(args={'path':'correct'}, ident='correct')), reply(call('submit', {}, ident='submit'))])
    assert result['status'] == 'submitted'
    assert len(runtime.calls) == 4 and client.usage['calls'] == 5
    blocked = [e for e in events(tmp_path) if e['event'] == 'loop_recovery_blocked']
    assert len(blocked) == 1 and blocked[0]['continuation_allowed'] is True
    assert '恢复机会' in client.requests[3]['messages'][-1]['content']


def test_new_observation_after_first_block_allows_the_old_hypothesis_to_be_refitted(tmp_path):
    runtime = Runtime()
    result, _, _ = run(tmp_path, runtime, [reply(call('fit_law_and_rollout', {}, ident=str(i))) for i in range(3)] +
        [reply(call('insert_probe', {}, ident='new-data')), reply(call('fit_law_and_rollout', {}, ident='retry')),
         reply(call('submit', {}, ident='submit'))])
    assert result['status'] == 'submitted'
    assert [name for name, _ in runtime.calls].count('fit_law_and_rollout') == 3


def test_new_law_file_refreshes_the_requested_directory_without_new_observations(tmp_path):
    runtime = FileRuntime(tmp_path)
    result, _, _ = run(tmp_path, runtime, [reply(call('list_files', {'path':'laws'}, ident='a')),
        reply(call('list_files', {'path':'laws'}, ident='b')), reply(call('fit_law_and_rollout', {}, ident='fit')),
        reply(call('list_files', {'path':'laws'}, ident='c')), reply(call('submit', {}, ident='submit'))])
    assert result['status'] == 'submitted'
    assert [name for name, _ in runtime.calls].count('list_files') == 3
    assert len(runtime.store.records['probe']) == 1 and len(runtime.store.records['body_observation']) == 0


def test_unrelated_validation_file_does_not_refresh_unchanged_law_directory(tmp_path):
    runtime = FileRuntime(tmp_path)
    result, _, _ = run(tmp_path, runtime, [reply(call('list_files', {'path':'laws'}, ident='a')),
        reply(call('list_files', {'path':'laws'}, ident='b')), reply(call('validate_law', {}, ident='validation')),
        reply(call('list_files', {'path':'laws'}, ident='c')), reply(call('list_files', {'path':'laws'}, ident='d'))])
    assert result['reason'] == 'repeated_deterministic_call_limit'
    assert [name for name, _ in runtime.calls].count('list_files') == 2


def test_file_created_after_missing_reads_can_be_read_with_identical_arguments(tmp_path):
    runtime = FileRuntime(tmp_path)
    args = {'path':'laws/law_3.json'}
    result, _, _ = run(tmp_path, runtime, [reply(call('read_file', args, ident='a')),
        reply(call('read_file', args, ident='b')), reply(call('fit_law_and_rollout', {}, ident='fit')),
        reply(call('read_file', args, ident='c')), reply(call('submit', {}, ident='submit'))])
    assert result['status'] == 'submitted'
    assert [name for name, _ in runtime.calls].count('read_file') == 3


def test_other_file_creation_does_not_refresh_read_of_unchanged_content(tmp_path):
    runtime = FileRuntime(tmp_path)
    args = {'path':'laws/existing.json'}
    result, _, _ = run(tmp_path, runtime, [reply(call('read_file', args, ident='a')),
        reply(call('read_file', args, ident='b')), reply(call('fit_law_and_rollout', {}, ident='fit')),
        reply(call('read_file', args, ident='c')), reply(call('read_file', args, ident='d'))])
    assert result['reason'] == 'repeated_deterministic_call_limit'
    assert [name for name, _ in runtime.calls].count('read_file') == 2


def test_file_registry_changes_never_reset_identical_fit_repetitions(tmp_path):
    runtime = FileRuntime(tmp_path)
    result, _, _ = run(tmp_path, runtime, [reply(call('fit_law_and_rollout', {}, ident='a')),
        reply(call('fit_law_and_rollout', {}, ident='b')), reply(call('list_files', {}, ident='listing')),
        reply(call('fit_law_and_rollout', {}, ident='c')), reply(call('fit_law_and_rollout', {}, ident='d'))])
    assert result['reason'] == 'repeated_deterministic_call_limit'
    assert [name for name, _ in runtime.calls].count('fit_law_and_rollout') == 2


@pytest.mark.parametrize('value', [1, None, 'true', []])
def test_flag_is_explicit_boolean(tmp_path, value):
    with pytest.raises(ValueError, match='loop_recovery'):
        Agent(Client([]), Runtime(), tmp_path, {'loop_recovery': value})
