"""Explicit temperature transport contracts; no sampling-quality claims."""
import json

import httpx
import pytest

from shore_agent.model import DeepSeekClient
from shore_agent.schemas import tool_schemas
from test_model import assistant, make_client, response
from test_model_strict_tools import local_overrides
from test_qwen_model import answer_stream, client as qwen_client


@pytest.mark.parametrize('temperature', [0, 0.0, 0.2, 1, 2.0])
@pytest.mark.parametrize('choice', [None, 'required'])
def test_explicit_temperature_reaches_wire_and_all_audits_with_existing_limits(
        tmp_path, monkeypatch, temperature, choice):
    value, requests, _ = qwen_client(tmp_path, monkeypatch, [answer_stream()],
        **local_overrides(strict_tools=True, temperature=temperature,
                          max_tokens_per_call=8192, thinking=True))
    try:
        value.complete([{'role': 'user', 'content': 'mock request'}],
                       tools=tool_schemas(ruleset='e5'), tool_choice_override=choice)
    finally:
        value.close()
    body = json.loads(requests[0].content)
    assert body['temperature'] == temperature
    assert body['seed'] == 42 and body['max_tokens'] == 4096
    assert body['chat_template_kwargs'] == {'enable_thinking': False}
    assert body['tool_choice'] == (choice or 'auto')
    assert all(tool['function']['strict'] is True for tool in body['tools'])
    assert value.config['temperature'] == temperature
    assert value.usage['calls'] == 1 and value.usage['completion_tokens'] == 12
    events = [json.loads(line) for line in (tmp_path / 'model_events.jsonl').read_text().splitlines()]
    assert [event['event'] for event in events] == ['configuration', 'request_started', 'request']
    assert all(event['temperature'] == temperature and event['seed'] == 42 for event in events)
    assert 'unit-qwen-credential' not in ''.join(path.read_text() for path in tmp_path.iterdir())


def test_omitted_temperature_keeps_historical_wire_and_event_shape(tmp_path, monkeypatch):
    value, requests = make_client(tmp_path, monkeypatch, [response(assistant())])
    try:
        value.complete([{'role': 'user', 'content': 'mock request'}])
    finally:
        value.close()
    assert requests[0] == {
        'model': 'deepseek-flash', 'messages': [{'role': 'user', 'content': 'mock request'}],
        'stream': False, 'thinking': {'type': 'enabled'}, 'reasoning_effort': 'high',
        'max_tokens': 4096,
    }
    assert 'temperature' not in value.config
    events = [json.loads(line) for line in (tmp_path / 'model_events.jsonl').read_text().splitlines()]
    assert all('temperature' not in event for event in events)


@pytest.mark.parametrize('ruleset', ['e3', 'e4', 'e5'])
def test_default_local_qwen_does_not_override_provider_temperature(tmp_path, monkeypatch, ruleset):
    value, requests, _ = qwen_client(tmp_path, monkeypatch, [answer_stream()],
                                     **local_overrides(ruleset=ruleset))
    try:
        value.complete([{'role': 'user', 'content': 'mock request'}])
    finally:
        value.close()
    assert 'temperature' not in json.loads(requests[0].content)
    events = [json.loads(line) for line in (tmp_path / 'model_events.jsonl').read_text().splitlines()]
    assert all('temperature' not in event for event in events)


@pytest.mark.parametrize('temperature', [
    True, False, None, -0.1, 2.1, float('nan'), float('inf'), float('-inf'),
    '0.2', [], {}, 10**500,
])
def test_invalid_temperature_is_rejected_before_transport_or_logging(tmp_path, temperature):
    def forbidden_request(_request):
        pytest.fail('invalid temperature reached HTTP transport')

    with pytest.raises(ValueError, match='temperature must be a finite number between 0 and 2'):
        DeepSeekClient({'temperature': temperature}, tmp_path, lambda: 300,
                       transport=httpx.MockTransport(forbidden_request))
    assert not (tmp_path / 'model_events.jsonl').exists()


def test_explicit_temperature_stays_fixed_across_retries_and_calls(tmp_path, monkeypatch):
    value, requests, _ = qwen_client(tmp_path, monkeypatch, [
        httpx.Response(503), answer_stream(), answer_stream(),
    ], **local_overrides(temperature=0.2, max_retries=1))
    try:
        value.complete([{'role': 'user', 'content': 'first mock'}])
        value.complete([{'role': 'user', 'content': 'second mock'}])
    finally:
        value.close()
    bodies = [json.loads(request.content) for request in requests]
    assert all(body['temperature'] == 0.2 and body['seed'] == 42
               and body['max_tokens'] == 4096 for body in bodies)
    assert value.usage['calls'] == 3 and value.usage['completion_tokens'] == 24
    assert value.usage['conservative_reserved_tokens'] > 0
    events = [json.loads(line) for line in (tmp_path / 'model_events.jsonl').read_text().splitlines()]
    assert all(event['temperature'] == 0.2 for event in events)
    for kind in ('request_started', 'request'):
        assert len([event for event in events if event['event'] == kind]) == 3
