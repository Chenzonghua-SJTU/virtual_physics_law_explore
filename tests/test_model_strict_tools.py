"""Transport-only strict tool contracts, without live inference or grammar claims."""
import copy
import json

import pytest

from shore_agent.model import DeepSeekClient
from shore_agent.schemas import tool_schemas
from test_qwen_model import answer_stream, client as qwen_client


def local_overrides(**values):
    return {'deployment': 'local', 'base_url': 'http://127.0.0.1:8000/v1',
            'reasoning_protocol': 'qwen', 'ruleset': 'e5', 'thinking': False,
            'sampling_seed': 42, **values}


def test_strict_clones_advertised_schemas_preserves_auto_limits_and_logs_names(tmp_path, monkeypatch):
    schemas = tool_schemas(ruleset='e5')
    supplied = [schema for schema in schemas
                if schema['function']['name'] not in ('insert_probe', 'observe_body')]
    original = copy.deepcopy(supplied)
    value, requests, _ = qwen_client(tmp_path, monkeypatch, [answer_stream('研究进展')],
                                     **local_overrides(strict_tools=True))
    try:
        returned = value.complete([{'role': 'user', 'content': 'synthetic'}], tools=supplied)
    finally:
        value.close()

    body = json.loads(requests[0].content)
    assert body['tool_choice'] == 'auto'
    assert body['seed'] == 42 and body['max_tokens'] == 4096
    assert body['chat_template_kwargs'] == {'enable_thinking': False}
    assert all(tool['function']['strict'] is True for tool in body['tools'])
    assert [tool['function']['name'] for tool in body['tools']] == [tool['function']['name'] for tool in supplied]
    assert supplied == original and all('strict' not in s['function'] for s in schemas)
    for actual, expected in zip(body['tools'], supplied):
        assert actual['function']['parameters'] == expected['function']['parameters']
    assert returned['content'] == '研究进展'  # Ordinary text remains allowed by this client contract.
    assert value.usage['calls'] == 1 and value.usage['completion_tokens'] == 12

    events = [json.loads(line) for line in (tmp_path / 'model_events.jsonl').read_text().splitlines()]
    assert all(event['strict_tools'] is True for event in events)
    for event in events:
        if event['event'] in ('request_started', 'request'):
            assert event['advertised_tool_names'] == [s['function']['name'] for s in supplied]
            assert event['advertised_tool_count'] == len(supplied)
            assert event['seed'] == 42
    assert 'unit-qwen-credential' not in ''.join(path.read_text() for path in tmp_path.iterdir())


@pytest.mark.parametrize('explicit', [False, True])
def test_default_or_explicit_false_does_not_change_wire_tools(tmp_path, monkeypatch, explicit):
    supplied = tool_schemas(ruleset='e5')
    config = local_overrides(**({'strict_tools': False} if explicit else {}))
    value, requests, _ = qwen_client(tmp_path, monkeypatch, [answer_stream()], **config)
    try:
        value.complete([{'role': 'user', 'content': 'synthetic'}], tools=supplied)
    finally:
        value.close()
    body = json.loads(requests[0].content)
    assert body['tools'] == supplied
    assert all('strict' not in tool['function'] for tool in body['tools'])
    assert body['tool_choice'] == 'auto'
    assert 'strict_tools' not in body


def test_logs_actual_different_advertised_tools_each_request_without_mutating_history(tmp_path, monkeypatch):
    supplied = tool_schemas(ruleset='e5')
    subset = [tool for tool in supplied if tool['function']['name'] == 'submit']
    value, requests, _ = qwen_client(tmp_path, monkeypatch, [answer_stream(), answer_stream()],
                                     **local_overrides(strict_tools=True))
    try:
        value.complete([{'role': 'user', 'content': 'first'}], tools=supplied)
        value.complete([{'role': 'user', 'content': 'second'}], tools=subset)
    finally:
        value.close()
    bodies = [json.loads(request.content) for request in requests]
    assert len(bodies[0]['tools']) == len(supplied)
    assert len(bodies[1]['tools']) == 1
    events = [json.loads(line) for line in (tmp_path / 'model_events.jsonl').read_text().splitlines()]
    completed = [event for event in events if event['event'] == 'request']
    assert completed[0]['advertised_tool_count'] == len(supplied)
    assert completed[1]['advertised_tool_names'] == ['submit']
    assert completed[1]['advertised_tool_count'] == 1


def test_strict_without_tools_does_not_invent_tools_or_force_action(tmp_path, monkeypatch):
    value, requests, _ = qwen_client(tmp_path, monkeypatch, [answer_stream()],
                                     **local_overrides(strict_tools=True))
    try:
        value.complete([{'role': 'user', 'content': 'synthetic'}])
    finally:
        value.close()
    body = json.loads(requests[0].content)
    assert 'tools' not in body and 'tool_choice' not in body
    events = [json.loads(line) for line in (tmp_path / 'model_events.jsonl').read_text().splitlines()]
    for event in events:
        if event['event'] in ('request_started', 'request'):
            assert event['advertised_tool_names'] == [] and event['advertised_tool_count'] == 0


@pytest.mark.parametrize('flag', [None, 0, 1, 'true', [], {}])
def test_strict_flag_must_be_boolean(tmp_path, flag):
    with pytest.raises(ValueError, match='strict_tools must be boolean'):
        DeepSeekClient(local_overrides(strict_tools=flag), tmp_path, lambda: 300)


@pytest.mark.parametrize('overrides', [
    {'ruleset': 'e3'}, {'ruleset': 'e4'},
    {'deployment': 'cloud', 'base_url': 'https://example.test/v1'},
    {'reasoning_protocol': 'deepseek'}, {'reasoning_protocol': 'chat_template'},
])
def test_strict_true_rejects_unverified_profiles(tmp_path, overrides):
    with pytest.raises(ValueError, match='strict_tools requires E5'):
        DeepSeekClient(local_overrides(strict_tools=True, **overrides), tmp_path, lambda: 300)
