"""Default auto schemas stay untouched; recovery alone enables Qwen grammar."""
import copy
import json

import pytest

from shore_agent.agent import Agent
from shore_agent.schemas import tool_schemas
from test_e5_length_recovery import Runtime, tool_message
from test_e5_strict_tool_recovery import run_mock
from test_e5_tool_failure_feedback import FailureRuntime, messages_for
from test_model_strict_tools import local_overrides
from test_qwen_model import answer_stream, client as qwen_client


def assert_required_schema_copy(actual, original):
    expected = copy.deepcopy(original)
    for tool in expected:
        field = tool['function']['parameters']['properties'].get('physical_explanation')
        if field is not None:
            field['pattern'] = r'^[\s\S]*\S[\s\S]*$'
    assert actual == expected
    assert all('strict' not in tool['function'] for tool in actual)


def test_non_strict_auto_required_auto_preserves_raw_schemas_and_sampling_limits(tmp_path, monkeypatch):
    schemas = tool_schemas(ruleset='e5')
    original = copy.deepcopy(schemas)
    value, requests, _ = qwen_client(tmp_path, monkeypatch, [answer_stream()] * 3,
        **local_overrides(strict_tools=False, temperature=0.2))
    assert value.supports_required_tool_choice is True
    try:
        for override in (None, 'required', None):
            value.complete([{'role': 'user', 'content': 'synthetic'}], tools=schemas,
                           tool_choice_override=override)
    finally:
        value.close()
    bodies = [json.loads(request.content) for request in requests]
    assert [body['tool_choice'] for body in bodies] == ['auto', 'required', 'auto']
    assert bodies[0]['tools'] == bodies[2]['tools'] == schemas == original
    assert_required_schema_copy(bodies[1]['tools'], original)
    assert all(body['max_tokens'] == 4096 and body['seed'] == 42 and body['temperature'] == 0.2
               and body['chat_template_kwargs'] == {'enable_thinking': False} for body in bodies)
    assert value.usage['calls'] == 3 and value.usage['completion_tokens'] == 36
    events = [json.loads(line) for line in (tmp_path / 'model_events.jsonl').read_text().splitlines()]
    assert all(event['strict_tools'] is False for event in events)
    for kind in ('request_started', 'request'):
        assert [event['tool_choice'] for event in events if event['event'] == kind] == ['auto', 'required', 'auto']


@pytest.mark.parametrize('trigger', ['unadvertised', 'repeated_failure', 'repeated_success'])
def test_agent_recovery_without_global_strict_preserves_raw_execution_records(tmp_path, trigger):
    runtime = FailureRuntime(tmp_path)
    original_schemas = copy.deepcopy(runtime.schemas)
    config = {'strict_tool_recovery': True, 'stagnation_recovery': True}
    if trigger == 'unadvertised':
        runtime.energy = 0
        config['budget_aware_tools'] = True
        initial = [tool_message('insert_probe', 'hidden')]
        reason = 'unadvertised_tool'
    elif trigger == 'repeated_failure':
        args = {'times': list(range(60))}
        initial = [messages_for(('observe_body', 'bad1', args)), messages_for(('observe_body', 'bad2', args))]
        reason = 'repeated_tool_failure'
    else:
        initial = [tool_message('validate_law', 'same1'), tool_message('validate_law', 'same2')]
        reason = 'repeated_success'
    result, requests, events = run_mock(tmp_path, runtime,
        initial + [tool_message('list_files', 'model-selected'), tool_message()], config,
        model_config={'strict_tools': False, 'temperature': 0.2})

    assert result['status'] == 'submitted'
    assert [request['tool_choice'] for request in requests] == ['auto'] * len(initial) + ['required', 'auto']
    assert runtime.schemas == original_schemas
    for index, request in enumerate(requests):
        assert all('strict' not in tool['function'] for tool in request['tools'])
        for tool in request['tools']:
            original = next(item for item in original_schemas if item['function']['name'] == tool['function']['name'])
            if index == len(initial):
                assert_required_schema_copy([tool], [original])
            else:
                assert tool == original
    raw = [json.loads(line) for line in (tmp_path / 'tools.jsonl').read_text().splitlines()]
    assert [row['result'] for row in raw] == runtime.results
    messages = json.loads((tmp_path / 'messages.json').read_text())
    assert [json.loads(message['content']) for message in messages if message['role'] == 'tool'] == runtime.results
    recovery = [event for event in events if event['event'] == 'strict_tool_recovery_requested']
    assert len(recovery) == 1 and recovery[0]['triggers'][0]['reason'] == reason
    assert requests[len(initial)]['messages'][-1]['role'] == 'tool'


@pytest.mark.parametrize('overrides', [
    {'ruleset': 'e3'}, {'ruleset': 'e4'},
    {'deployment': 'cloud', 'base_url': 'https://example.test/v1'},
    {'reasoning_protocol': 'deepseek'}, {'reasoning_protocol': 'chat_template'},
])
@pytest.mark.parametrize('flag', ['strict_tool_recovery', 'stagnation_recovery'])
def test_unsupported_client_cannot_enable_e5_recovery(tmp_path, monkeypatch, overrides, flag):
    value, requests, _ = qwen_client(tmp_path, monkeypatch, [],
                                     **local_overrides(strict_tools=False, **overrides))
    try:
        assert value.supports_required_tool_choice is False
        with pytest.raises(ValueError, match='requires a local Qwen E5 required-tool client'):
            Agent(value, Runtime('e5'), tmp_path, {flag: True})
    finally:
        value.close()
    assert not requests and value.usage['calls'] == 0
