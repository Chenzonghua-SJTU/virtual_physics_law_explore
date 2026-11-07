"""One-turn alternatives for duplicate successful actions, using synthetic data."""
import copy
import json

import pytest

from shore_agent.agent import Agent
from shore_agent.schemas import tool_schemas
from test_e5_length_recovery import Runtime, tool_message
from test_e5_strict_tool_recovery import run_mock
from test_e5_tool_failure_feedback import FailureRuntime, messages_for


COMPUTATIONS = ['fit_law_and_rollout', 'validate_law', 'diagnose_dynamics', 'analyze_residual']
CONFIG = {'stagnation_recovery': True, 'strict_tool_recovery': False}


def successful_runtime(path, ruleset='e5'):
    runtime = FailureRuntime(path, ruleset)
    runtime.succeed = True
    runtime.schemas = tool_schemas(ruleset=ruleset, diagnostics_enabled=True)
    return runtime


def names(request):
    return {tool['function']['name'] for tool in request['tools']}


@pytest.mark.parametrize('name', ['observe_body'] + COMPUTATIONS)
def test_second_identical_success_excludes_only_that_name_for_one_request(tmp_path, name):
    runtime = successful_runtime(tmp_path)
    before = copy.deepcopy(runtime.schemas)
    args = {'times': [0, 1]} if name == 'observe_body' else {'synthetic': ['same-input']}
    result, requests, events = run_mock(tmp_path, runtime, [
        messages_for((name, 'first', args)),
        messages_for((name, 'repeat', args)),
        tool_message('list_files', 'model-selected'),
        tool_message(),
    ], CONFIG)

    assert result['status'] == 'submitted'
    assert [r['tool_choice'] for r in requests] == ['auto', 'auto', 'required', 'auto']
    assert names(requests[2]) == names(requests[0]) - {name}
    assert names(requests[3]) == names(requests[0])
    assert {'list_files', 'read_file', 'save_draft', 'submit'} <= names(requests[2])
    assert runtime.schemas == before
    assert [n for n, _ in runtime.executed] == [name, name, 'list_files', 'submit']
    assert all(row['ok'] is True for row in runtime.results)
    assert requests[2]['messages'][-1]['role'] == 'tool'
    assert requests[0]['messages'][0] == requests[2]['messages'][0]
    raw = [json.loads(row) for row in (tmp_path / 'tools.jsonl').read_text().splitlines()]
    assert [row['result'] for row in raw] == runtime.results
    for event_name in ('strict_tool_recovery_scheduled', 'strict_tool_recovery_requested'):
        recovery = [event for event in events if event['event'] == event_name]
        assert len(recovery) == 1
        assert recovery[0]['temporarily_excluded_tool_names'] == [name]
        assert recovery[0]['triggers'][0]['reason'] == 'repeated_success'
        assert recovery[0]['triggers'][0]['repeat_count'] == 2
    assert result['model_usage']['calls'] == 4 and result['model_usage']['completion_tokens'] == 80
    assert all(r['max_tokens'] == 4096 for r in requests)


@pytest.mark.parametrize('data_tool,data_args', [
    ('insert_probe', {'probes': ['synthetic-new-data']}), ('observe_body', {'times': [2, 3]}),
])
@pytest.mark.parametrize('computation', COMPUTATIONS)
def test_new_data_allows_same_computation_again_then_tracks_new_revision(tmp_path, data_tool, data_args, computation):
    runtime = successful_runtime(tmp_path)
    args = {'synthetic': 'same-input'}
    _, requests, events = run_mock(tmp_path, runtime, [
        messages_for((computation, 'old-data', args)),
        messages_for((data_tool, 'new-data', data_args)),
        messages_for((computation, 'new-data-first', args)),
        messages_for((computation, 'new-data-repeat', args)),
        tool_message(),
    ], CONFIG)
    assert [r['tool_choice'] for r in requests] == ['auto', 'auto', 'auto', 'auto', 'required']
    trigger = next(e for e in events if e['event'] == 'strict_tool_recovery_requested')['triggers'][0]
    assert trigger['tool'] == computation and trigger['repeat_count'] == 2
    assert trigger['data_version'] == 1


def test_same_absolute_times_are_not_new_data_and_do_not_clear_computation_counts(tmp_path):
    runtime = successful_runtime(tmp_path)
    _, requests, events = run_mock(tmp_path, runtime, [
        messages_for(('observe_body', 'times-first', {'times': [0, 1]})),
        messages_for(('validate_law', 'validate-first', {'law_id': 'synthetic', 'test_probe_ids': ['p']})),
        messages_for(('observe_body', 'times-repeat', {'times': [0.0, 1.0]})),
        messages_for(('validate_law', 'validate-repeat', {'test_probe_ids': ['p'], 'law_id': 'synthetic'})),
        tool_message(),
    ], CONFIG)
    assert [r['tool_choice'] for r in requests] == ['auto', 'auto', 'auto', 'required', 'required']
    assert 'observe_body' not in names(requests[3]) and 'validate_law' in names(requests[3])
    assert 'validate_law' not in names(requests[4]) and 'observe_body' in names(requests[4])
    triggers = [e['triggers'][0] for e in events if e['event'] == 'strict_tool_recovery_requested']
    assert [(t['tool'], t['repeat_count'], t['data_version']) for t in triggers] == [
        ('observe_body', 2, 1), ('validate_law', 2, 1)]


def test_new_observation_times_are_allowed_without_recovery(tmp_path):
    runtime = successful_runtime(tmp_path)
    _, requests, events = run_mock(tmp_path, runtime, [
        messages_for(('observe_body', 'first', {'times': [0, 1]})),
        messages_for(('observe_body', 'extension', {'times': [2, 3]})),
        tool_message(),
    ], CONFIG)
    assert all(r['tool_choice'] == 'auto' for r in requests)
    assert not any(e['event'].startswith('strict_tool_recovery') for e in events)


def test_old_observation_signature_stays_duplicate_after_other_data_arrives(tmp_path):
    runtime = successful_runtime(tmp_path)
    _, requests, events = run_mock(tmp_path, runtime, [
        messages_for(('observe_body', 'first', {'times': [0, 1]})),
        messages_for(('observe_body', 'different', {'times': [2, 3]})),
        tool_message('insert_probe', 'new-probe'),
        messages_for(('observe_body', 'old-repeat', {'times': [0, 1]})),
        tool_message(),
    ], CONFIG)
    assert [r['tool_choice'] for r in requests] == ['auto', 'auto', 'auto', 'auto', 'required']
    trigger = next(e for e in events if e['event'] == 'strict_tool_recovery_requested')['triggers'][0]
    assert trigger['tool'] == 'observe_body' and trigger['repeat_count'] == 2
    assert trigger['data_version'] == 3


@pytest.mark.parametrize('name,args', [
    ('insert_probe', {}), ('observe_body', {'times': list(range(60))}),
])
def test_failed_acquisition_does_not_reset_successful_computation_counts(tmp_path, name, args):
    runtime = successful_runtime(tmp_path)
    runtime.succeed = False
    _, requests, events = run_mock(tmp_path, runtime, [
        tool_message('validate_law', 'first'),
        messages_for((name, 'failed-acquisition', args)),
        tool_message('validate_law', 'repeat'), tool_message(),
    ], CONFIG)
    assert [r['tool_choice'] for r in requests] == ['auto', 'auto', 'auto', 'required']
    trigger = next(e for e in events if e['event'] == 'strict_tool_recovery_requested')['triggers'][0]
    assert trigger['reason'] == 'repeated_success' and trigger['data_version'] == 0
    assert runtime.results[1]['ok'] is False


def test_new_data_later_in_same_batch_cancels_stale_computation_recovery(tmp_path):
    runtime = successful_runtime(tmp_path)
    _, requests, events = run_mock(tmp_path, runtime, [
        messages_for(('validate_law', 'first', {'law_id': 'synthetic'}),
                     ('validate_law', 'repeat', {'law_id': 'synthetic'}),
                     ('insert_probe', 'new-data', {})),
        messages_for(('validate_law', 'valid-after-data', {'law_id': 'synthetic'})),
        tool_message(),
    ], CONFIG)
    assert all(r['tool_choice'] == 'auto' for r in requests)
    assert not any(e['event'].startswith('strict_tool_recovery') for e in events)


def test_multiple_repeated_tools_are_excluded_without_affecting_other_batch_actions(tmp_path):
    runtime = successful_runtime(tmp_path)
    _, requests, events = run_mock(tmp_path, runtime, [
        messages_for(('fit_law_and_rollout', 'fit1', {}), ('fit_law_and_rollout', 'fit2', {}),
                     ('analyze_residual', 'res1', {}), ('analyze_residual', 'res2', {}),
                     ('list_files', 'legal', {})),
        tool_message(),
    ], CONFIG)
    assert len(runtime.executed) == 6
    assert names(requests[1]) == names(requests[0]) - {'fit_law_and_rollout', 'analyze_residual'}
    assert [m['role'] for m in requests[1]['messages'][-6:]] == ['assistant'] + ['tool'] * 5
    recovery = next(e for e in events if e['event'] == 'strict_tool_recovery_requested')
    assert recovery['temporarily_excluded_tool_names'] == ['analyze_residual', 'fit_law_and_rollout']


@pytest.mark.parametrize('name', ['list_files', 'read_file', 'save_draft', 'insert_probe'])
def test_protected_and_data_acquisition_actions_are_not_blocked(tmp_path, name):
    runtime = successful_runtime(tmp_path)
    _, requests, events = run_mock(tmp_path, runtime, [
        tool_message(name, 'first'), tool_message(name, 'repeat'), tool_message(),
    ], CONFIG)
    assert all(r['tool_choice'] == 'auto' for r in requests)
    assert not any(e['event'].startswith('strict_tool_recovery') for e in events)


def test_runtime_still_executes_model_call_to_temporarily_hidden_tool_and_records_success(tmp_path):
    runtime = successful_runtime(tmp_path)
    result, requests, events = run_mock(tmp_path, runtime, [
        tool_message('fit_law_and_rollout', 'first'), tool_message('fit_law_and_rollout', 'second'),
        tool_message('fit_law_and_rollout', 'unexpected-but-model-selected'), tool_message(),
    ], CONFIG)
    assert result['status'] == 'submitted'
    assert [r['tool_choice'] for r in requests] == ['auto', 'auto', 'required', 'required']
    assert [name for name, _ in runtime.executed] == ['fit_law_and_rollout'] * 3 + ['submit']
    assert all(result['ok'] for result in runtime.results)
    repeats = [e['triggers'][0]['repeat_count'] for e in events
               if e['event'] == 'strict_tool_recovery_requested']
    assert repeats == [2, 3]


def test_expiry_preserves_raw_successes_without_request_or_automatic_submission(tmp_path):
    runtime = successful_runtime(tmp_path)
    original_execute = runtime.execute

    def expire(name, args):
        result = original_execute(name, args)
        if len(runtime.executed) == 2:
            runtime.remaining = 0
            result['budget'] = runtime.budget()
        return result

    runtime.execute = expire
    result, requests, events = run_mock(tmp_path, runtime, [
        tool_message('validate_law', 'first'), tool_message('validate_law', 'repeat'),
    ], CONFIG)
    assert len(requests) == 2 and result['submission'] is None
    assert result['reason'] == 'wall_time_exhausted_without_saved_draft'
    assert not any(e['event'] == 'strict_tool_recovery_requested' for e in events)


@pytest.mark.parametrize('ruleset,flag', [('e5', None), ('e5', False), ('e3', True), ('e4', True)])
def test_default_and_previous_rulesets_keep_legacy_client_signature(tmp_path, ruleset, flag):
    runtime = successful_runtime(tmp_path, ruleset)

    class LegacyClient:
        usage = {'calls': 0}
        last_finish_reason = 'tool_calls'

        def __init__(self):
            self.replies = iter([tool_message('observe_body', 'first', '{"times":[0,1]}'),
                                 tool_message('observe_body', 'second', '{"times":[0,1]}'), tool_message()])

        def remaining_seconds(self):
            return runtime.remaining

        def complete(self, messages, tools=None, role='main'):
            self.usage['calls'] += 1
            return next(self.replies)

    config = {} if flag is None else {'stagnation_recovery': flag}
    result = Agent(LegacyClient(), runtime, tmp_path, {'guidance_profile': 'e3', **config}).run()
    assert result['status'] == 'submitted' and result['model_usage']['calls'] == 3
    assert 'strict_tool_recovery' not in (tmp_path / 'events.jsonl').read_text()


@pytest.mark.parametrize('flag', [None, 0, 1, 'true', {}, []])
def test_stagnation_flag_requires_boolean(tmp_path, flag):
    with pytest.raises(ValueError, match='stagnation_recovery must be boolean'):
        Agent(None, Runtime(), tmp_path, {'stagnation_recovery': flag})


def test_stagnation_requires_compatible_client(tmp_path):
    with pytest.raises(ValueError, match='stagnation_recovery requires a local Qwen E5 required-tool client'):
        Agent(None, Runtime(), tmp_path, {'stagnation_recovery': True})
