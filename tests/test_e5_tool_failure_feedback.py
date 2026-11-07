"""Synthetic repeated-error recovery; no live models or scientific assertions."""
import copy
import json

import pytest

from shore_agent.agent import Agent
from shore_agent.store import append_event
from test_e5_length_recovery import Runtime, client_for, tool_message


class FailureRuntime(Runtime):
    def __init__(self, directory, ruleset='e5'):
        super().__init__(ruleset)
        self.directory = directory
        self.energy = 1
        self.results = []
        self.succeed = False

    def execute(self, name, args):
        if name == 'insert_probe' and not self.succeed:
            self.executed.append((name, copy.deepcopy(args)))
            result = {'ok': False, 'data': None,
                      'error': {'code': 'ValueError', 'message': "{'code': 'energy_budget', 'message': 'Not enough energy for this batch'}"},
                      'budget': self.budget()}
        elif name == 'observe_body' and len(args.get('times', [])) > 50:
            self.executed.append((name, copy.deepcopy(args)))
            result = {'ok': False, 'data': None,
                      'error': {'code': 'ValidationError', 'message': 'times is too long; maxItems=50'},
                      'budget': self.budget()}
        else:
            result = super().execute(name, args)
        self.results.append(copy.deepcopy(result))
        append_event(self.directory / 'tools.jsonl',
                     {'tool': name, 'arguments': args, 'result': result})
        return result


def messages_for(*calls):
    return {'role': 'assistant', 'content': '',
            'tool_calls': [tool_message(name, call_id, json.dumps(args))['tool_calls'][0]
                           for name, call_id, args in calls]}


def run_mock(tmp_path, runtime, replies, config=None):
    client, requests = client_for(tmp_path, runtime,
                                 [(reply, 'tool_calls', 1, 20) for reply in replies])
    try:
        result = Agent(client, runtime, tmp_path,
                       {'guidance_profile': 'e3', **(config or {})}).run()
    finally:
        client.close()
    events = [json.loads(line) for line in (tmp_path / 'events.jsonl').read_text().splitlines()]
    return result, requests, events


def test_second_same_failure_prompts_after_all_tool_replies_and_keeps_raw_results(tmp_path):
    runtime = FailureRuntime(tmp_path)
    args = {'times': list(range(60))}
    result, requests, events = run_mock(tmp_path, runtime, [
        messages_for(('observe_body', 'bad1', args)),
        messages_for(('observe_body', 'bad2', args), ('list_files', 'legal', {})),
        tool_message(),
    ], {'repeated_tool_failure_feedback': True})

    assert result['status'] == 'submitted'
    assert [name for name, _ in runtime.executed] == ['observe_body', 'observe_body', 'list_files', 'submit']
    assert requests[1]['messages'][-1]['role'] == 'tool'  # First failure causes no feedback.
    context = requests[2]['messages']
    assert [m['role'] for m in context[-4:]] == ['assistant', 'tool', 'tool', 'user']
    assert [m['tool_call_id'] for m in context[-3:-1]] == ['bad2', 'legal']
    content = context[-1]['content']
    assert all(text in content for text in ['已失败 2 次', 'ValidationError', '60 项', '50 项',
                                            '不得原样重试', '当前剩余预算', 'energy_remaining'])
    assert requests[0]['messages'][0] == requests[2]['messages'][0]  # System prompt is untouched.
    logged = [json.loads(line) for line in (tmp_path / 'tools.jsonl').read_text().splitlines()]
    assert [row['result'] for row in logged] == runtime.results
    tool_messages = [m for m in json.loads((tmp_path / 'messages.json').read_text()) if m['role'] == 'tool']
    assert [json.loads(m['content']) for m in tool_messages] == runtime.results
    feedback_events = [e for e in events if e['event'] == 'repeated_tool_failure_feedback']
    assert len(feedback_events) == 1
    assert feedback_events[0]['failures'][0]['repeat_count'] == 2
    assert result['model_usage']['calls'] == 3 and result['model_usage']['completion_tokens'] == 60
    assert all(request['max_tokens'] == 4096 for request in requests)


def test_nonconsecutive_failures_with_reordered_keys_get_budget_hint_without_auto_action(tmp_path):
    runtime = FailureRuntime(tmp_path)
    args = {'probes': [{'r0': [1, 0], 'v0': [0, 0]}] * 4, 't0': 0, 'dt': .1, 'n_samples': 2}
    reordered = dict(reversed(list(args.items())))
    result, requests, events = run_mock(tmp_path, runtime, [
        messages_for(('insert_probe', 'first', args)),
        messages_for(('list_files', 'unrelated', {})),
        messages_for(('insert_probe', 'second', reordered)),
        messages_for(('insert_probe', 'third', args), ('list_files', 'still-legal', {})),
        {'role': 'assistant', 'content': 'synthetic stop'},
    ], {'repeated_tool_failure_feedback': True, 'max_no_action': 1})

    assert result['status'] == 'incomplete' and result['submission'] is None
    assert [name for name, _ in runtime.executed] == ['insert_probe', 'list_files', 'insert_probe',
                                                     'insert_probe', 'list_files']
    second_feedback = requests[3]['messages'][-1]['content']
    assert '已失败 2 次' in second_feedback and 'energy_budget' in second_feedback
    assert '超过剩余能量' in second_feedback and '"energy_remaining": 1' in second_feedback
    third_feedback = requests[4]['messages'][-1]['content']
    assert '已失败 3 次' in third_feedback and '此前恢复提醒后仍在重复失败' in third_feedback
    assert all(name != 'submit' for name, _ in runtime.executed)
    assert len([e for e in events if e['event'] == 'repeated_tool_failure_feedback']) == 2


def test_repeated_failures_in_one_batch_do_not_cancel_model_selected_submission(tmp_path):
    runtime = FailureRuntime(tmp_path)
    args = {'times': list(range(60))}
    result, requests, events = run_mock(tmp_path, runtime, [messages_for(
        ('observe_body', 'bad1', args), ('observe_body', 'bad2', args), ('submit', 'chosen', {}),
    )], {'repeated_tool_failure_feedback': True})
    assert len(requests) == 1 and result['status'] == 'submitted'
    assert [name for name, _ in runtime.executed] == ['observe_body', 'observe_body', 'submit']
    saved = json.loads((tmp_path / 'messages.json').read_text())
    assert [m['tool_call_id'] for m in saved if m['role'] == 'tool'] == ['bad1', 'bad2', 'chosen']
    assert not any(e['event'] == 'repeated_tool_failure_feedback' for e in events)


@pytest.mark.parametrize('ruleset,flag', [('e5', None), ('e5', False), ('e3', True), ('e4', True)])
def test_default_disabled_and_prior_rulesets_preserve_history(tmp_path, ruleset, flag):
    runtime = FailureRuntime(tmp_path, ruleset)
    config = {} if flag is None else {'repeated_tool_failure_feedback': flag}
    args = {'times': list(range(60))}
    result, requests, events = run_mock(tmp_path, runtime, [
        messages_for(('observe_body', 'bad1', args)),
        messages_for(('observe_body', 'bad2', args)),
        tool_message(),
    ], config)
    assert result['status'] == 'submitted'
    assert requests[2]['messages'][-1]['role'] == 'tool'
    assert not any(e['event'] == 'repeated_tool_failure_feedback' for e in events)


def test_success_of_same_signature_resets_failure_count(tmp_path):
    runtime = FailureRuntime(tmp_path)
    args = {'probes': [], 't0': 0, 'dt': .1, 'n_samples': 2}
    original_execute = runtime.execute
    outcomes = iter([False, True, False, False])

    def controlled_execute(name, given_args):
        if name == 'insert_probe':
            runtime.succeed = next(outcomes)
        return original_execute(name, given_args)

    runtime.execute = controlled_execute
    _, requests, events = run_mock(tmp_path, runtime, [
        *(messages_for(('insert_probe', f'call{i}', args)) for i in range(4)), tool_message(),
    ], {'repeated_tool_failure_feedback': True})
    assert requests[3]['messages'][-1]['role'] == 'tool'
    assert '已失败 2 次' in requests[4]['messages'][-1]['content']
    assert len([e for e in events if e['event'] == 'repeated_tool_failure_feedback']) == 1


def test_expiry_after_failure_feedback_still_stops_without_another_request(tmp_path):
    runtime = FailureRuntime(tmp_path)
    original_execute = runtime.execute

    def expires_after_second_failure(name, args):
        result = original_execute(name, args)
        if len(runtime.executed) == 2:
            runtime.remaining = 0
            result['budget'] = runtime.budget()
        return result

    runtime.execute = expires_after_second_failure
    args = {'times': list(range(60))}
    result, requests, _ = run_mock(tmp_path, runtime, [
        messages_for(('observe_body', 'bad1', args)),
        messages_for(('observe_body', 'bad2', args)),
    ], {'repeated_tool_failure_feedback': True})
    assert len(requests) == 2
    assert result['status'] == 'incomplete' and result['submission'] is None
    assert result['reason'] == 'wall_time_exhausted_without_saved_draft'


@pytest.mark.parametrize('flag', [None, 0, 1, 'true'])
def test_feedback_flag_requires_boolean(tmp_path, flag):
    with pytest.raises(ValueError, match='repeated_tool_failure_feedback must be boolean'):
        Agent(None, Runtime(), tmp_path, {'repeated_tool_failure_feedback': flag})
