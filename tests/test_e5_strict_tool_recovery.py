"""Synthetic protocol failures only; scientific actions remain model choices."""
import copy
import json

import httpx
import pytest

from shore_agent.agent import Agent
from shore_agent.model import DeepSeekClient
from test_e5_length_recovery import Runtime, tool_message
from test_e5_tool_failure_feedback import FailureRuntime, messages_for


def run_mock(directory, runtime, replies, config=None, *, model_config=None):
    requests = []
    queue = iter(replies)

    def handler(request):
        requests.append(json.loads(request.content))
        message = copy.deepcopy(next(queue))
        runtime.remaining -= 1
        for index, call in enumerate(message.get('tool_calls', [])):
            call['index'] = index
        chunks = [
            {'choices': [{'index': 0, 'delta': message,
                          'finish_reason': 'tool_calls' if message.get('tool_calls') else 'stop'}]},
            {'choices': [], 'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}}]
        wire = ''.join('data: ' + json.dumps(chunk) + '\n\n' for chunk in chunks) + 'data: [DONE]\n\n'
        return httpx.Response(200, content=wire, headers={'content-type': 'text/event-stream'})

    client = DeepSeekClient({'ruleset': runtime.ruleset, 'deployment': 'local',
        'base_url': 'http://127.0.0.1:8000/v1', 'api_key_required': False,
        'reasoning_protocol': 'qwen', 'thinking': False, 'sampling_seed': 42,
        'strict_tools': runtime.ruleset == 'e5', 'max_tokens_per_call': 4096,
        **(model_config or {})}, directory,
        remaining_seconds=lambda: runtime.remaining, transport=httpx.MockTransport(handler))
    try:
        result = Agent(client, runtime, directory,
                       {'guidance_profile': 'e3', 'strict_tool_recovery': True,
                        **(config or {})}).run()
    finally:
        client.close()
    events = [json.loads(line) for line in (directory / 'events.jsonl').read_text().splitlines()]
    return result, requests, events


def test_hidden_tool_runs_normally_then_one_required_request_and_returns_auto(tmp_path):
    runtime = FailureRuntime(tmp_path)
    runtime.energy = 0
    before = copy.deepcopy(runtime.schemas)
    result, requests, events = run_mock(tmp_path, runtime, [
        messages_for(('insert_probe', 'hidden', {'probes': []}), ('list_files', 'legal', {})),
        tool_message('list_files', 'model-selected'),
        {'role': 'assistant', 'content': '普通研究进展'},
        tool_message(),
    ], {'budget_aware_tools': True})

    assert result['status'] == 'submitted'
    assert [request['tool_choice'] for request in requests] == ['auto', 'required', 'auto', 'auto']
    assert all('insert_probe' not in [tool['function']['name'] for tool in request['tools']]
               for request in requests)
    assert runtime.schemas == before
    assert [name for name, _ in runtime.executed] == ['insert_probe', 'list_files', 'list_files', 'submit']
    assert runtime.results[0]['ok'] is False
    context = requests[1]['messages']
    assert [m['role'] for m in context[-3:]] == ['assistant', 'tool', 'tool']
    assert [m['tool_call_id'] for m in context[-2:]] == ['hidden', 'legal']
    assert [json.loads(m['content']) for m in context[-2:]] == runtime.results[:2]
    assert not any(e['event'] == 'repeated_tool_failure_feedback' for e in events)
    recovery = [e for e in events if e['event'] == 'strict_tool_recovery_requested']
    assert len(recovery) == 1 and recovery[0]['turn'] == 2
    assert recovery[0]['triggers'] == [{'reason': 'unadvertised_tool', 'tool': 'insert_probe',
                                       'tool_call_id': 'hidden'}]
    assert recovery[0]['tool_choice'] == 'required'
    assert result['model_usage']['calls'] == 4 and result['model_usage']['completion_tokens'] == 80
    assert all(r['max_tokens'] == 4096 and r['seed'] == 42
               and r['chat_template_kwargs']['enable_thinking'] is False for r in requests)
    raw = [json.loads(row) for row in (tmp_path / 'tools.jsonl').read_text().splitlines()]
    assert [row['result'] for row in raw] == runtime.results


def test_second_nonconsecutive_identical_failure_recovers_and_can_retrigger(tmp_path):
    runtime = FailureRuntime(tmp_path)
    args = {'times': list(range(60)), 'body_id': 'synthetic'}
    reverse_args = dict(reversed(list(args.items())))
    result, requests, events = run_mock(tmp_path, runtime, [
        messages_for(('observe_body', 'bad1', args)),
        tool_message('list_files', 'unrelated'),
        messages_for(('observe_body', 'bad2', reverse_args), ('list_files', 'legal', {})),
        messages_for(('observe_body', 'bad3', args)),
        tool_message('list_files', 'recovered'),
        tool_message(),
    ])
    assert result['status'] == 'submitted'
    assert [r['tool_choice'] for r in requests] == ['auto', 'auto', 'auto', 'required', 'required', 'auto']
    for request in requests[3:5]:
        assert request['messages'][-1]['role'] == 'tool'  # No unsolicited prompt changes.
    recovery = [e for e in events if e['event'] == 'strict_tool_recovery_requested']
    assert [e['triggers'][0]['repeat_count'] for e in recovery] == [2, 3]
    assert all(e['triggers'][0]['reason'] == 'repeated_tool_failure' for e in recovery)


def test_success_resets_failure_history_including_same_batch(tmp_path):
    runtime = FailureRuntime(tmp_path)
    original_execute = runtime.execute
    outcomes = iter([False, False, True, False])

    def controlled_execute(name, args):
        if name == 'insert_probe':
            runtime.succeed = next(outcomes)
        return original_execute(name, args)

    runtime.execute = controlled_execute
    result, requests, events = run_mock(tmp_path, runtime, [
        messages_for(('insert_probe', 'bad1', {})),
        messages_for(('insert_probe', 'bad2', {}), ('insert_probe', 'good', {})),
        messages_for(('insert_probe', 'new-bad1', {})),
        tool_message(),
    ])
    assert result['status'] == 'submitted'
    assert all(r['tool_choice'] == 'auto' for r in requests)
    assert not any(e['event'].startswith('strict_tool_recovery') for e in events)


def test_failure_recovery_keeps_existing_text_feedback_after_all_tools(tmp_path):
    runtime = FailureRuntime(tmp_path)
    args = {'times': list(range(60))}
    _, requests, events = run_mock(tmp_path, runtime, [
        messages_for(('observe_body', 'bad1', args), ('observe_body', 'bad2', args),
                     ('list_files', 'legal', {})),
        tool_message(),
    ], {'repeated_tool_failure_feedback': True})
    assert requests[1]['tool_choice'] == 'required'
    assert [m['role'] for m in requests[1]['messages'][-5:]] == ['assistant', 'tool', 'tool', 'tool', 'user']
    assert '不得原样重试' in requests[1]['messages'][-1]['content']
    assert len([e for e in events if e['event'] == 'repeated_tool_failure_feedback']) == 1


def test_expired_deadline_does_not_issue_scheduled_recovery(tmp_path):
    runtime = FailureRuntime(tmp_path)
    runtime.energy = 0
    original_execute = runtime.execute

    def expire(name, args):
        result = original_execute(name, args)
        runtime.remaining = 0
        result['budget'] = runtime.budget()
        return result

    runtime.execute = expire
    result, requests, events = run_mock(tmp_path, runtime, [tool_message('insert_probe', 'hidden')],
                                         {'budget_aware_tools': True})
    assert len(requests) == 1 and result['submission'] is None
    assert result['reason'] == 'wall_time_exhausted_without_saved_draft'
    assert any(e['event'] == 'strict_tool_recovery_scheduled' for e in events)
    assert not any(e['event'] == 'strict_tool_recovery_requested' for e in events)


def test_model_chosen_submission_in_same_batch_needs_no_recovery(tmp_path):
    runtime = FailureRuntime(tmp_path)
    runtime.energy = 0
    result, requests, events = run_mock(tmp_path, runtime, [
        messages_for(('insert_probe', 'hidden', {}), ('submit', 'chosen', {})),
    ], {'budget_aware_tools': True})
    assert result['status'] == 'submitted' and len(requests) == 1
    assert [name for name, _ in runtime.executed] == ['insert_probe', 'submit']
    assert not any(e['event'].startswith('strict_tool_recovery') for e in events)


@pytest.mark.parametrize('ruleset,config', [('e5', {}), ('e5', {'strict_tool_recovery': False}),
    ('e3', {'strict_tool_recovery': True}), ('e4', {'strict_tool_recovery': True})])
def test_legacy_fakeclient_signature_is_unchanged(tmp_path, ruleset, config):
    runtime = FailureRuntime(tmp_path, ruleset)

    class LegacyClient:
        usage = {'calls': 0}
        last_finish_reason = 'tool_calls'

        def __init__(self):
            self.replies = iter([tool_message('insert_probe', 'bad1'),
                                 tool_message('insert_probe', 'bad2'), tool_message()])

        def remaining_seconds(self):
            return runtime.remaining

        def complete(self, messages, tools=None, role='main'):
            self.usage['calls'] += 1
            return next(self.replies)

    result = Agent(LegacyClient(), runtime, tmp_path, {'guidance_profile': 'e3', **config}).run()
    assert result['status'] == 'submitted' and result['model_usage']['calls'] == 3
    assert 'strict_tool_recovery' not in (tmp_path / 'events.jsonl').read_text()


@pytest.mark.parametrize('flag', [None, 0, 1, 'true', {}, []])
def test_recovery_flag_requires_boolean(tmp_path, flag):
    with pytest.raises(ValueError, match='strict_tool_recovery must be boolean'):
        Agent(None, Runtime(), tmp_path, {'strict_tool_recovery': flag})


def test_recovery_requires_compatible_client(tmp_path):
    with pytest.raises(ValueError, match='requires a local Qwen E5 required-tool client'):
        Agent(None, Runtime(), tmp_path, {'strict_tool_recovery': True})
