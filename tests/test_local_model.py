"""Mock HTTP contracts only: these do not verify a deployed model's behavior."""
import copy
import json

import httpx
import pytest

from shore_agent.model import DeepSeekClient, ModelError, model_auth_config


def local_config(**overrides):
    return {
        'base_url': 'http://127.0.0.1:8000/v1',
        'model': 'deepseek-ai/DeepSeek-V4-Flash',
        'deployment': 'local',
        'api_key_env': 'LOCAL_LLM_API_KEY',
        'api_key_required': False,
        'reasoning_protocol': 'chat_template',
        'thinking': True,
        'reasoning_effort': 'low',
        'max_total_tokens': 5000000,
        **overrides,
    }


def completion(message=None):
    return {'choices': [{'message': message or {'role': 'assistant', 'content': 'ok'},
                         'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
            'model': 'served-checkpoint', 'system_fingerprint': 'test-only'}


def make_client(config, tmp_path, requests, responses=None):
    responses = iter(responses or [httpx.Response(200, json=completion())])

    def handler(request):
        requests.append(request)
        return next(responses)

    return DeepSeekClient(config, tmp_path, lambda: 100,
                          transport=httpx.MockTransport(handler))


@pytest.mark.parametrize('effort', ['low', 'high', 'max'])
def test_local_request_and_audit_match_requested_effort(tmp_path, monkeypatch, effort):
    monkeypatch.delenv('LOCAL_LLM_API_KEY', raising=False)
    # An unrelated cloud key must not leak to the configured local endpoint.
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'cloud-secret-never-send')
    requests = []
    client = make_client(local_config(reasoning_effort=effort), tmp_path, requests)
    try:
        client.complete([{'role': 'user', 'content': 'test'}])
    finally:
        client.close()
    req = requests[0]
    body = json.loads(req.content)
    assert str(req.url) == 'http://127.0.0.1:8000/v1/chat/completions'
    assert 'Authorization' not in req.headers
    assert body['model'] == 'deepseek-ai/DeepSeek-V4-Flash'
    assert body['chat_template_kwargs'] == {'thinking': True, 'reasoning_effort': effort}
    assert body['reasoning_effort'] == effort
    assert 'thinking' not in body
    events = [json.loads(line) for line in (tmp_path / 'model_events.jsonl').read_text().splitlines()]
    for event in events:
        assert event['reasoning_protocol'] == 'chat_template'
        assert event['requested_reasoning_effort'] == effort
        assert event['reasoning_parameters'] == {
            'chat_template_kwargs': {'thinking': True, 'reasoning_effort': effort},
            'reasoning_effort': effort}
    assert 'cloud-secret-never-send' not in ''.join(p.read_text() for p in tmp_path.iterdir())


def test_cloud_wire_contract_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'cloud-secret-never-log')
    requests = []
    client = make_client({}, tmp_path, requests)
    try:
        client.complete([{'role': 'user', 'content': 'test'}])
    finally:
        client.close()
    assert json.loads(requests[0].content) == {
        'model': 'deepseek-flash', 'messages': [{'role': 'user', 'content': 'test'}],
        'stream': False, 'thinking': {'type': 'enabled'}, 'reasoning_effort': 'high',
        'max_tokens': 4096}
    assert requests[0].headers['Authorization'] == 'Bearer cloud-secret-never-log'
    assert 'cloud-secret-never-log' not in ''.join(p.read_text() for p in tmp_path.iterdir())


@pytest.mark.parametrize('protocol', ['deepseek', 'chat_template'])
def test_thinking_disabled_is_explicit_and_does_not_send_effort(tmp_path, monkeypatch, protocol):
    monkeypatch.delenv('LOCAL_LLM_API_KEY', raising=False)
    requests = []
    client = make_client(local_config(thinking=False, reasoning_protocol=protocol), tmp_path, requests)
    try:
        client.complete([{'role': 'user', 'content': 'test'}])
    finally:
        client.close()
    body = json.loads(requests[0].content)
    assert 'reasoning_effort' not in body
    if protocol == 'chat_template':
        assert body['chat_template_kwargs'] == {'thinking': False}
    else:
        assert body['thinking'] == {'type': 'disabled'}


def test_custom_key_env_required_and_redacted(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCAL_LLM_API_KEY', 'local-secret-never-log')
    requests = []
    client = make_client(local_config(api_key_required=True), tmp_path, requests)
    try:
        client.complete([{'role': 'user', 'content': 'test'}])
        monkeypatch.delenv('LOCAL_LLM_API_KEY')
        with pytest.raises(ModelError, match='^missing_model_api_key$'):
            client.complete([{'role': 'user', 'content': 'test'}])
    finally:
        client.close()
    assert len(requests) == 1
    assert requests[0].headers['Authorization'] == 'Bearer local-secret-never-log'
    assert 'local-secret-never-log' not in ''.join(p.read_text() for p in tmp_path.iterdir())


@pytest.mark.parametrize('overrides', [
    {'deployment': 'cloud'},
    {'deployment': 'local', 'base_url': 'https://api.deepseek.com'},
    {'deployment': 'local', 'base_url': 'http://192.168.1.2:8000/v1'},
    {'deployment': 'local', 'base_url': 'http://localhost.example.com/v1'},
    {'deployment': 'local', 'base_url': 'http://127.0.0.1@external.example/v1'},
    {'deployment': 'local', 'base_url': 'http://127.0.0.1/v1?key=secret'},
])
def test_no_key_requires_explicit_local_loopback(overrides):
    with pytest.raises(ValueError):
        model_auth_config(local_config(**overrides))
    with pytest.raises(ValueError):
        model_auth_config({'base_url': 'http://127.0.0.1:8000/v1', 'api_key_required': False})


@pytest.mark.parametrize('url', ['http://localhost:8000/v1', 'http://127.0.0.1:8000/v1',
                               'http://[::1]:8000/v1'])
def test_loopback_auth_helper_has_no_secret_dependency(url, monkeypatch):
    monkeypatch.delenv('LOCAL_LLM_API_KEY', raising=False)
    assert model_auth_config(local_config(base_url=url)) == ('LOCAL_LLM_API_KEY', False)
    assert model_auth_config({}) == ('DEEPSEEK_API_KEY', True)


@pytest.mark.parametrize('overrides', [
    {'api_key_required': 'false'}, {'api_key_env': 'LOCAL_KEY=value'},
    {'deployment': 'unknown'}, {'reasoning_protocol': 'automatic'},
    {'reasoning_effort': 'medium'}, {'thinking': 'true'},
])
def test_invalid_local_contract_fails_before_http(tmp_path, overrides):
    with pytest.raises(ValueError):
        DeepSeekClient(local_config(**overrides), tmp_path, lambda: 100)


def test_cloud_cannot_accidentally_use_template_protocol(tmp_path):
    with pytest.raises(ValueError, match='requires deployment=local'):
        DeepSeekClient({'reasoning_protocol': 'chat_template'}, tmp_path, lambda: 100)


@pytest.mark.parametrize('reasoning_field', ['reasoning_content', 'reasoning'])
def test_full_reasoning_and_tool_history_survive_local_roundtrip(tmp_path, monkeypatch, reasoning_field):
    monkeypatch.delenv('LOCAL_LLM_API_KEY', raising=False)
    tool_call = {'id': 'call_1', 'type': 'function', 'function': {'name': 'probe', 'arguments': '{}'}}
    answer = {'role': 'assistant', 'content': None, reasoning_field: 'synthetic-test-placeholder',
              'tool_calls': [tool_call]}
    requests = []
    client = make_client(local_config(), tmp_path, requests,
                         [httpx.Response(200, json=completion(answer)),
                          httpx.Response(200, json=completion())])
    tools = [{'type': 'function', 'function': {'name': 'probe',
              'parameters': {'type': 'object', 'properties': {}}}}]
    messages = [{'role': 'user', 'content': 'test'}]
    try:
        returned = client.complete(messages, tools)
        messages += [returned, {'role': 'tool', 'tool_call_id': 'call_1', 'content': '{}'}]
        snapshot = copy.deepcopy(messages)
        client.complete(messages, tools)
    finally:
        client.close()
    assert returned == answer
    assert messages == snapshot
    assert json.loads(requests[1].content)['messages'] == messages
    assert json.loads(requests[1].content)['tools'] == tools


def test_unsupported_server_parameter_does_not_fallback_to_other_effort(tmp_path, monkeypatch):
    monkeypatch.delenv('LOCAL_LLM_API_KEY', raising=False)
    requests = []
    client = make_client(local_config(reasoning_effort='max', max_retries=3), tmp_path, requests,
                         [httpx.Response(400, json={'error': 'unsupported reasoning effort'})])
    try:
        with pytest.raises(ModelError, match='^http_status_400$'):
            client.complete([{'role': 'user', 'content': 'test'}])
    finally:
        client.close()
    assert len(requests) == 1
    assert json.loads(requests[0].content)['reasoning_effort'] == 'max'
