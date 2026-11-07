"""Prompt-only ablation and opt-in seed wire contract; no scientific score claims."""
import json
from pathlib import Path

import pytest

from shore_agent.agent import Agent
from shore_agent.schemas import tool_schemas
from test_model import FakeRuntime, assistant, call, make_client, response
from test_qwen_model import client, answer_stream


class Runtime(FakeRuntime):
    ruleset = 'e5'
    schemas = tool_schemas(ruleset='e5')
    last_valid_draft = None

    def budget(self):
        return {'wall_seconds_remaining': 100, 'energy_remaining': 10}

    def finalize_draft(self, reason):
        return None


@pytest.mark.parametrize('profile', ['baseline', 'e3', 'concise'])
def test_profiles_preserve_tools_and_original_main_prompt(tmp_path, monkeypatch, profile):
    value, requests = make_client(tmp_path, monkeypatch,
        [response(assistant(calls=[call()]), 'tool_calls')])
    result = Agent(value, Runtime(), tmp_path, {'guidance_profile': profile}).run()
    prompt = requests[0]['messages'][0]['content']
    base = (Path(__file__).parents[1] / 'shore_agent/prompts/main.txt').read_text()
    assert prompt.startswith(base)
    assert (prompt == base) is (profile == 'e3')
    assert requests[0]['tools'] == tool_schemas(ruleset='e5')
    assert result['status'] == 'submitted'


@pytest.mark.parametrize('seed', [None, 42, 43])
def test_local_sampling_seed_is_opt_in(tmp_path, monkeypatch, seed):
    value, requests, _ = client(tmp_path, monkeypatch, [answer_stream()],
        deployment='local', base_url='http://127.0.0.1:8000/v1', thinking=False,
        api_key_env='NO_KEY', api_key_required=False, sampling_seed=seed)
    try:
        value.complete([{'role': 'user', 'content': 'synthetic seed test'}])
    finally:
        value.close()
    body = json.loads(requests[0].content)
    assert body.get('seed') == seed
    assert ('seed' in body) is (seed is not None)
    assert body['chat_template_kwargs']['enable_thinking'] is False
