"""One-request protocol recovery stays within the ordinary model budgets."""
import copy
import json

import pytest

from shore_agent.schemas import tool_schemas
from test_model_strict_tools import local_overrides
from test_qwen_model import answer_stream, client as qwen_client


def test_required_is_one_request_only_and_logs_actual_choice(tmp_path, monkeypatch):
    supplied = tool_schemas(ruleset='e5')
    original = copy.deepcopy(supplied)
    value, requests, _ = qwen_client(tmp_path, monkeypatch, [answer_stream(), answer_stream()],
                                     remaining=lambda: 18,
                                     **local_overrides(strict_tools=True))
    try:
        value.complete([{'role': 'user', 'content': 'synthetic'}], tools=supplied,
                       tool_choice_override='required')
        value.complete([{'role': 'user', 'content': 'synthetic'}], tools=supplied)
    finally:
        value.close()
    bodies = [json.loads(request.content) for request in requests]
    assert [body['tool_choice'] for body in bodies] == ['required', 'auto']
    assert supplied == original
    for body in bodies:
        assert all(tool['function']['strict'] is True for tool in body['tools'])
        assert body['seed'] == 42 and body['max_tokens'] == 4096
        assert body['chat_template_kwargs'] == {'enable_thinking': False}
    assert value.usage['calls'] == 2 and value.usage['completion_tokens'] == 24
    events = [json.loads(line) for line in (tmp_path / 'model_events.jsonl').read_text().splitlines()]
    for kind in ('request_started', 'request'):
        logged = [row for row in events if row['event'] == kind]
        assert [row['tool_choice'] for row in logged] == ['required', 'auto']
        assert all(row['timeout_seconds'] <= 18 for row in logged)
    assert 'unit-qwen-credential' not in ''.join(path.read_text() for path in tmp_path.iterdir())


@pytest.mark.parametrize('choice', ['auto', 'none', 'submit', True, False, 0, {}, []])
def test_rejects_invalid_override_before_http_or_usage(tmp_path, monkeypatch, choice):
    value, requests, _ = qwen_client(tmp_path, monkeypatch, [],
                                     **local_overrides(strict_tools=True))
    try:
        with pytest.raises(ValueError, match='tool_choice_override must be required'):
            value.complete([], tools=tool_schemas(), tool_choice_override=choice)
    finally:
        value.close()
    assert not requests and value.usage['calls'] == 0


@pytest.mark.parametrize('config', [
    local_overrides(), local_overrides(ruleset='e3'), local_overrides(ruleset='e4'),
    {'deployment': 'cloud', 'reasoning_protocol': 'qwen', 'ruleset': 'e5'},
    local_overrides(reasoning_protocol='deepseek'),
])
def test_rejects_unverified_profile_before_http(tmp_path, monkeypatch, config):
    value, requests, _ = qwen_client(tmp_path, monkeypatch, [], **config)
    try:
        with pytest.raises(ValueError, match='requires strict local Qwen E5'):
            value.complete([], tools=tool_schemas(), tool_choice_override='required')
    finally:
        value.close()
    assert not requests and value.usage['calls'] == 0


@pytest.mark.parametrize('tools', [None, []])
def test_required_without_tools_is_rejected(tmp_path, monkeypatch, tools):
    value, requests, _ = qwen_client(tmp_path, monkeypatch, [],
                                     **local_overrides(strict_tools=True))
    try:
        with pytest.raises(ValueError, match='requires advertised tools'):
            value.complete([], tools=tools, tool_choice_override='required')
    finally:
        value.close()
    assert not requests and value.usage['calls'] == 0
