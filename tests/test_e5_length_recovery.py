"""Synthetic transport checks; no model experiments or scientific answers."""
import copy
import json
from pathlib import Path

import httpx
import pytest

from shore_agent.agent import Agent
from shore_agent.model import DeepSeekClient
from shore_agent.schemas import tool_schemas


def tool_message(name='submit', call_id='accepted', arguments='{}'):
    return {'role': 'assistant', 'content': None, 'tool_calls': [
        {'type': 'function', 'id': call_id, 'function': {'name': name, 'arguments': arguments}}]}


class Runtime:
    def __init__(self, ruleset='e5', draft=None):
        self.ruleset = ruleset
        self.schemas = tool_schemas(ruleset=ruleset)
        self.last_valid_draft = draft
        self.remaining = 300
        self.energy = 10
        self.executed = []
        self.mission_calls = 0

    def budget(self):
        return {'wall_seconds_remaining': self.remaining, 'energy_remaining': self.energy}

    def mission(self):
        self.mission_calls += 1
        return {'ok': True, 'data': {'task': 'synthetic'}, 'budget': self.budget()}

    def execute(self, name, args):
        self.executed.append((name, args))
        data = {'status': 'accepted', 'session_ended': True} if name == 'submit' else {'observations': 'synthetic'}
        return {'ok': True, 'data': data, 'budget': self.budget()}

    def finalize_draft(self, reason):
        return copy.deepcopy(self.last_valid_draft)


def client_for(directory, runtime, responses):
    queue = iter(responses)
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        message, finish, spent, tokens = next(queue)
        runtime.remaining -= spent
        delta = copy.deepcopy(message)
        for index, call in enumerate(delta.get('tool_calls', [])):
            call['index'] = index
        chunks = [
            {'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish}]},
            {'choices': [], 'usage': {'prompt_tokens': 100, 'completion_tokens': tokens, 'total_tokens': 100 + tokens}}]
        stream = ''.join('data: ' + json.dumps(chunk) + '\n\n' for chunk in chunks) + 'data: [DONE]\n\n'
        return httpx.Response(200, content=stream.encode(), headers={'content-type': 'text/event-stream'})

    client = DeepSeekClient({'ruleset': runtime.ruleset, 'deployment': 'local',
        'base_url': 'http://127.0.0.1:8000/v1', 'api_key_required': False,
        'reasoning_protocol': 'qwen', 'thinking': False, 'max_tokens_per_call': 4096}, directory,
        remaining_seconds=lambda: max(0, runtime.remaining - 5), transport=httpx.MockTransport(handler))
    return client, requests


def test_e3_guidance_in_e5_preserves_original_system_prompt_and_hard_limits(tmp_path):
    runtime = Runtime()
    client, requests = client_for(tmp_path, runtime, [(tool_message(), 'tool_calls', 5, 40)])
    try:
        result = Agent(client, runtime, tmp_path, {'guidance_profile': 'e3'}).run()
    finally:
        client.close()
    original = (Path(__file__).parents[1] / 'shore_agent/prompts/main.txt').read_text()
    assert requests[0]['messages'][0]['content'] == original
    assert requests[0]['max_tokens'] == 4096
    assert requests[0]['chat_template_kwargs']['enable_thinking'] is False
    assert result['status'] == 'submitted'


@pytest.mark.parametrize('arguments', ['{}', '{"partial":'])
def test_e5_recovers_once_without_executing_length_tools_and_preserves_valid_history(tmp_path, arguments):
    runtime = Runtime()
    first = tool_message('observe_body', 'prior')
    truncated = tool_message('insert_probe', 'never-execute', arguments)
    truncated['content'] = 'synthetic repetition ' * 30
    client, requests = client_for(tmp_path, runtime, [
        (first, 'tool_calls', 5, 30), (truncated, 'length', 65, 4096),
        (tool_message(), 'tool_calls', 10, 50)])
    try:
        result = Agent(client, runtime, tmp_path, {}).run()
    finally:
        client.close()
    assert result['status'] == 'submitted'
    assert runtime.executed == [('observe_body', {}), ('submit', {})]
    assert runtime.mission_calls == 1 and runtime.energy == 10
    assert result['budget']['wall_seconds_remaining'] == 220
    assert result['model_usage']['calls'] == 3
    assert result['model_usage']['completion_tokens'] == 4176
    assert all(r['max_tokens'] == 4096 and r['chat_template_kwargs']['enable_thinking'] is False for r in requests)
    recovered = requests[2]['messages']
    assert recovered[:4] == requests[1]['messages']  # First valid tool exchange preserved byte-for-byte.
    assert recovered[-2]['role'] == 'assistant' and 'tool_calls' not in recovered[-2]
    assert recovered[-1]['role'] == 'user' and '不要续写' in recovered[-1]['content']
    assert 'never-execute' not in json.dumps(recovered)
    events = [json.loads(line) for line in (tmp_path / 'events.jsonl').read_text().splitlines()]
    original = [e for e in events if e['event'] == 'model_length_recovered']
    assert len(original) == 1 and original[0]['original_message'] == truncated
    assert not any(e['event'] == 'tool_started' and e['name'] == 'insert_probe' for e in events)


@pytest.mark.parametrize('draft', [None, {'status': 'accepted', 'session_ended': True, 'law_id': 'previously-saved'}])
def test_second_length_stops_or_seals_existing_draft_without_a_third_request(tmp_path, draft):
    runtime = Runtime(draft=draft)
    truncated = tool_message('insert_probe', arguments='{}')
    client, requests = client_for(tmp_path, runtime, [
        (truncated, 'length', 65, 4096), (truncated, 'length', 65, 4096)])
    try:
        result = Agent(client, runtime, tmp_path, {}).run()
    finally:
        client.close()
    assert len(requests) == 2 and not runtime.executed
    assert result['model_usage']['completion_tokens'] == 8192
    assert result['budget']['wall_seconds_remaining'] == 170
    if draft:
        assert result['status'] == 'submitted' and result['submission'] == draft
        assert result['reason'] == 'saved_draft_after_model_finish_length'
    else:
        assert result['status'] == 'incomplete' and result['submission'] is None
        assert result['reason'] == 'model_finish_length'


def test_length_recovery_does_not_bypass_expired_deadline(tmp_path):
    runtime = Runtime()
    client, requests = client_for(tmp_path, runtime, [(tool_message(), 'length', 280, 4096)])
    complete = client.complete
    def expires_after_response(*args, **kwargs):
        message = complete(*args, **kwargs)
        runtime.remaining = 0
        return message
    client.complete = expires_after_response
    try:
        result = Agent(client, runtime, tmp_path, {}).run()
    finally:
        client.close()
    assert len(requests) == 1 and not runtime.executed
    assert result['reason'] == 'wall_time_exhausted_without_saved_draft'
    assert result['model_usage']['completion_tokens'] == 4096


@pytest.mark.parametrize('ruleset', ['e3', 'e4'])
def test_previous_profiles_still_stop_on_first_length(tmp_path, ruleset):
    runtime = Runtime(ruleset)
    client, requests = client_for(tmp_path, runtime, [(tool_message(), 'length', 65, 4096)])
    try:
        result = Agent(client, runtime, tmp_path, {}).run()
    finally:
        client.close()
    assert len(requests) == 1 and not runtime.executed
    assert result['reason'] == 'model_finish_length'
