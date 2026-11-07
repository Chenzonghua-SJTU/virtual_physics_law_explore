"""Explicit request seed contracts only; mocks do not establish reproducibility."""
import json

import httpx
import pytest

from shore_agent.model import DeepSeekClient
from test_model import assistant, make_client, response
from test_qwen_model import answer_stream, client as qwen_client


@pytest.mark.parametrize('seed', [0, 42, 2**32 - 1])
def test_explicit_seed_reaches_local_qwen_wire_and_all_audit_events(tmp_path, monkeypatch, seed):
    value, requests, _ = qwen_client(
        tmp_path, monkeypatch, [answer_stream()],
        deployment='local', base_url='http://127.0.0.1:8000/v1',
        thinking=False, sampling_seed=seed, ruleset='e5')
    try:
        value.complete([{'role': 'user', 'content': 'mock request'}])
    finally:
        value.close()

    body = json.loads(requests[0].content)
    assert body['seed'] == seed and type(body['seed']) is int
    assert body['max_tokens'] == 4096
    assert body['chat_template_kwargs'] == {'enable_thinking': False}
    assert value.config['sampling_seed'] == seed
    assert value.usage['calls'] == 1
    assert value.usage['completion_tokens'] == 12
    events = [json.loads(line) for line in (tmp_path / 'model_events.jsonl').read_text().splitlines()]
    assert [event['event'] for event in events] == ['configuration', 'request_started', 'request']
    assert all(event['seed'] == seed for event in events)
    assert 'unit-qwen-credential' not in ''.join(path.read_text() for path in tmp_path.iterdir())


def test_omitted_seed_preserves_historical_request_and_event_shape(tmp_path, monkeypatch):
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
    events = [json.loads(line) for line in (tmp_path / 'model_events.jsonl').read_text().splitlines()]
    assert all('seed' not in event for event in events)
    assert 'sampling_seed' not in value.config


@pytest.mark.parametrize('seed', [True, False, None, -1, 2**32, 1.0, '42', [], {}])
def test_invalid_explicit_seed_is_rejected_before_any_http_request(tmp_path, seed):
    def forbidden_request(_request):
        pytest.fail('invalid seed reached HTTP transport')

    with pytest.raises(ValueError, match='sampling_seed must be an integer between 0 and 4294967295'):
        DeepSeekClient({'sampling_seed': seed}, tmp_path, lambda: 300,
                       transport=httpx.MockTransport(forbidden_request))
    assert not (tmp_path / 'model_events.jsonl').exists()


def test_seed_stays_fixed_across_retries_and_calls_without_changing_usage(tmp_path, monkeypatch):
    value, requests = make_client(tmp_path, monkeypatch, [
        httpx.Response(503), response(assistant()), response(assistant()),
    ], config={'sampling_seed': 20261107, 'max_retries': 1})
    try:
        value.complete([{'role': 'user', 'content': 'first mock'}])
        value.complete([{'role': 'user', 'content': 'second mock'}])
    finally:
        value.close()

    assert [request['seed'] for request in requests] == [20261107] * 3
    assert all(request['max_tokens'] == 4096 for request in requests)
    assert value.usage['calls'] == 3
    assert value.usage['completion_tokens'] == 20
    assert value.usage['conservative_reserved_tokens'] > 0  # The failed attempt remains reserved.
    events = [json.loads(line) for line in (tmp_path / 'model_events.jsonl').read_text().splitlines()]
    starts = [event for event in events if event['event'] == 'request_started']
    finished = [event for event in events if event['event'] == 'request']
    assert len(starts) == len(finished) == 3
    assert all(event['seed'] == 20261107 for event in events)
    assert [event['call_number'] for event in finished] == [1, 2, 3]
