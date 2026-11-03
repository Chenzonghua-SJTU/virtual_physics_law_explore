"""Protocol-only mocks. No test here demonstrates scientific discovery."""
import json

import httpx
import pytest

from shore_agent.agent import Agent
from shore_agent.model import DeepSeekClient, ModelError
from shore_agent.schemas import SCHEMAS


def response(message, finish='stop', usage=None):
    return {'choices': [{'message': message, 'finish_reason': finish}],
            'usage': usage or {'prompt_tokens': 20, 'completion_tokens': 10, 'total_tokens': 30},
            'model': 'provider-model-version', 'system_fingerprint': 'test-fingerprint'}


def assistant(content='研究进展', calls=None, reasoning='private reasoning retained'):
    msg = {'role': 'assistant', 'content': content, 'reasoning_content': reasoning}
    if calls is not None:
        msg['tool_calls'] = calls
    return msg


def call(name='submit', call_id='test_call_1', arguments='{}'):
    return {'type': 'function', 'id': call_id, 'function': {'name': name, 'arguments': arguments}}


class FakeRuntime:
    schemas = SCHEMAS

    def __init__(self, accepted=True):
        self.executed = []
        self.accepted = accepted

    def mission(self):
        return {'ok': True, 'data': {'task': 'mock protocol test, no physical model'},
                'error': None, 'budget': {'remaining_seconds': 100}}

    def execute(self, name, args):
        self.executed.append((name, args))
        return {'ok': True, 'data': {'status': 'accepted' if self.accepted else 'rejected',
                                    'session_ended': self.accepted}, 'error': None,
                'budget': {'remaining_seconds': 99}}


def make_client(tmp_path, monkeypatch, results, config=None, remaining=None):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'unit-test-secret-do-not-log')
    requests = []
    queue = iter(results)

    def handler(request):
        requests.append(json.loads(request.content))
        item = next(queue)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, httpx.Response):
            return item
        return httpx.Response(200, json=item)

    client = DeepSeekClient(config or {}, tmp_path, remaining or (lambda: 100),
                            transport=httpx.MockTransport(handler))
    return client, requests


def test_reasoning_survives_content_only_turn_and_auto_tools(tmp_path, monkeypatch, capsys):
    first = assistant('先检查证据。')
    second = assistant('调用模拟接口。', [call()])
    client, requests = make_client(tmp_path, monkeypatch,
                                  [response(first), response(second, 'tool_calls')])
    runtime = FakeRuntime()
    result = Agent(client, runtime, tmp_path, {}).run()
    assert result['status'] == 'submitted'
    assert requests[1]['messages'][2] == first
    assert requests[0]['tool_choice'] == 'auto'
    assert requests[0]['thinking'] == {'type': 'enabled'}
    assert requests[0]['reasoning_effort'] == 'high'
    assert len(requests[0]['tools']) == 7
    assert all(t['function']['name'] != 'summarize_data' for t in requests[0]['tools'])
    saved = json.loads((tmp_path / 'messages.json').read_text())
    assert saved[-2] == second
    assert saved[-1]['tool_call_id'] == 'test_call_1'
    stdout = capsys.readouterr().out
    assert '先检查证据' in stdout and 'private reasoning' not in stdout
    events = (tmp_path / 'model_events.jsonl').read_text()
    assert 'provider-model-version' in events and 'test-fingerprint' in events
    assert 'unit-test-secret-do-not-log' not in ''.join(p.read_text() for p in tmp_path.iterdir())


def test_every_tool_call_paired_even_after_submission(tmp_path, monkeypatch):
    calls = [call(), call('observe_body', 'later_call', '{"times":[0]}')]
    client, _ = make_client(tmp_path, monkeypatch, [response(assistant(calls=calls), 'tool_calls')])
    runtime = FakeRuntime()
    agent = Agent(client, runtime, tmp_path, {})
    assert agent.run()['status'] == 'submitted'
    assert len(runtime.executed) == 1
    assert [m['tool_call_id'] for m in agent.messages if m['role'] == 'tool'] == ['test_call_1', 'later_call']
    assert json.loads(agent.messages[-1]['content'])['error']['code'] == 'session_ended'


def test_no_action_is_not_submission_and_is_bounded(tmp_path, monkeypatch):
    client, requests = make_client(tmp_path, monkeypatch, [response(assistant('已完成。'))] * 3)
    result = Agent(client, FakeRuntime(), tmp_path, {}).run()
    assert result['status'] == 'incomplete'
    assert result['reason'] == 'consecutive_no_action_limit'
    assert result['submission'] is None
    assert len(requests) == 3


def test_length_never_executes_even_well_formed_tool_json(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch, [response(assistant(calls=[call()]), 'length')])
    runtime = FakeRuntime()
    assert Agent(client, runtime, tmp_path, {}).run()['reason'] == 'model_finish_length'
    assert not runtime.executed


def test_malformed_json_gets_matching_error_then_recovers(tmp_path, monkeypatch):
    client, requests = make_client(tmp_path, monkeypatch, [
        response(assistant(calls=[call(arguments='{"partial":')]), 'tool_calls'),
        response(assistant(calls=[call(call_id='retry')]), 'tool_calls')])
    runtime = FakeRuntime()
    assert Agent(client, runtime, tmp_path, {}).run()['status'] == 'submitted'
    assert len(runtime.executed) == 1
    error_msg = requests[1]['messages'][-1]
    assert error_msg['tool_call_id'] == 'test_call_1'
    assert json.loads(error_msg['content'])['error']['code'] == 'invalid_tool_arguments_json'


def test_duplicate_call_ids_stop_before_side_effects(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch, [response(assistant(calls=[call(), call()]), 'tool_calls')])
    runtime = FakeRuntime()
    assert Agent(client, runtime, tmp_path, {}).run()['reason'] == 'malformed_tool_call_protocol'
    assert not runtime.executed


def test_rejected_submit_does_not_complete(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch, [
        response(assistant(calls=[call()]), 'tool_calls'), response(assistant())])
    result = Agent(client, FakeRuntime(False), tmp_path, {'max_no_action': 1}).run()
    assert result['status'] == 'incomplete' and result['submission'] is None
    assert result['reason'] == 'consecutive_no_action_limit'


def test_legacy_body_positions_reach_model_and_web_only_after_explicit_observation(tmp_path, monkeypatch):
    from shore_agent.environment import Environment
    from shore_agent.runtime import ToolRuntime
    from shore_agent.web_jobs import RunManager

    def assert_no_body_coordinates(value):
        serialized = json.dumps(value)
        for key in ('positions_obs', 'visible_bodies', 'known_bodies', 'body_position_estimate'):
            assert f'"{key}"' not in serialized

    manager = RunManager(tmp_path.parent, runs_dir=tmp_path.parent)
    client, requests = make_client(tmp_path, monkeypatch, [
        response(assistant(calls=[call('call_back', 'before_observation', '{"record_type":"all"}')]),
                 'tool_calls'),
        response(assistant(calls=[call('observe_body', 'explicit_observation', '{"times":[0,1]}')]),
                 'tool_calls'),
        response(assistant('协议测试结束，不声称发现规律。')),
    ])
    try:
        with Environment({'noise': False, 'seed': 12, 'physics_version': 'v3'}) as environment:
            runtime = ToolRuntime(environment, tmp_path)
            initial_mission = runtime.mission()['data']
            assert_no_body_coordinates(initial_mission)
            assert not runtime.known_bodies and not runtime.store.records['body_observation']
            assert runtime.budget()['observations_remaining'] == 20
            before = manager.snapshot(tmp_path.name)
            assert before['bodies'] == [] and before['body_position_estimate'] is None
            assert before['records']['body_observations'] == []
            assert before['body_position_source'] == 'no_observations'

            result = Agent(client, runtime, tmp_path, {'max_no_action': 1}).run()
            assert result['reason'] == 'consecutive_no_action_limit'
            assert len(requests) == 3
            first_input = json.loads(requests[0]['messages'][1]['content'].split('\n', 1)[1])
            assert first_input['data'] == initial_mission
            assert_no_body_coordinates(first_input)
            callback = requests[1]['messages'][-1]
            assert callback['tool_call_id'] == 'before_observation'
            callback_result = json.loads(callback['content'])
            assert callback_result['ok']
            assert {r['record_type'] for r in callback_result['data']['records']} == {'probe'}
            assert_no_body_coordinates(callback_result)

            observed = requests[2]['messages'][-1]
            assert observed['tool_call_id'] == 'explicit_observation'
            observation_result = json.loads(observed['content'])
            assert observation_result['ok']
            observation = observation_result['data']
            assert len(observation['positions_obs']) == 2
            assert observation['body_position_estimate']['observation_ids'] == [observation['observation_id']]
            assert runtime.budget()['observations_remaining'] == 19
            acquired = json.loads(json.dumps(runtime.store.records['body_observation']))
            assert runtime.mission()['data'] == initial_mission
            assert runtime.store.records['body_observation'] == acquired
            assert runtime.budget()['observations_remaining'] == 19
            assert_no_body_coordinates(json.loads((tmp_path / 'mission.json').read_text()))

            after = manager.snapshot(tmp_path.name)
            assert after['body_position_source'] == 'observed_estimate'
            assert after['bodies'] == observation['body_position_estimate']['bodies']
            assert len(after['records']['body_observations']) == 1
    finally:
        client.close()
        manager.close()


def test_v4_model_receives_known_initial_states_and_cached_free_body_series(tmp_path, monkeypatch):
    from shore_agent.environment import Environment
    from shore_agent.runtime import ToolRuntime
    from shore_agent.web_jobs import RunManager

    config = {'noise': False, 'seed': 12, 'world_id': 'world_6', 'physics_version': 'v4'}
    (tmp_path / 'config.json').write_text(json.dumps({'environment': config}))
    client, requests = make_client(tmp_path, monkeypatch, [
        response(assistant(calls=[call('call_back', 'initial_records', '{"record_type":"all"}')]),
                 'tool_calls'),
        response(assistant('协议测试结束，不声称发现规律。')),
    ])
    manager = RunManager(tmp_path.parent, runs_dir=tmp_path.parent)
    try:
        with Environment(config) as environment:
            runtime = ToolRuntime(environment, tmp_path)
            mission = runtime.mission()['data']
            assert len(mission['task']['body_initial_states']) == 3
            assert 'static_visible_bodies' not in mission['task']
            free = mission['first_light']['body_observation']
            assert len(free['times']) == 8
            assert free['positions_obs'][0] != free['positions_obs'][-1]
            assert max(free['times']) == 3.5
            for probe in mission['first_light']['probes']:
                assert probe['times'] == free['times']
            result = Agent(client, runtime, tmp_path, {'max_no_action': 1}).run()
            assert result['reason'] == 'consecutive_no_action_limit'
            initial = json.loads(requests[0]['messages'][1]['content'].split('\n', 1)[1])
            assert initial['data'] == mission
            callback = json.loads(requests[1]['messages'][-1]['content'])
            assert {r['record_type'] for r in callback['data']['records']} == {'probe', 'body_observation'}
            assert runtime.budget()['observations_remaining'] == 20
            assert runtime.budget()['energy_remaining'] == 100
            snapshot = manager.snapshot(tmp_path.name)
            assert snapshot['world_id'] == 'world_6'
            assert snapshot['body_position_source'] == 'observed_trajectories'
            assert snapshot['body_position_estimate'] == runtime.body_position_estimate
            assert snapshot['body_position_estimate']['time_range'] == [0, 3.5]
            assert snapshot['records']['body_observations'] == [free]
    finally:
        client.close()
        manager.close()


def test_physical_explanation_flows_from_model_to_submission_and_web(tmp_path, monkeypatch):
    from shore_agent.environment import Environment
    from shore_agent.runtime import ToolRuntime
    from shore_agent.web_jobs import RunManager

    explanation = '数学推论：该候选为位置的仿射函数。\n工程测试文字，不代表自主发现。\n<script>不得作为 HTML 执行</script>'
    with Environment({'noise': False, 'seed': 12}) as environment:
        runtime = ToolRuntime(environment, tmp_path)
        assert runtime.mission()['ok']
        fitted = runtime.execute('fit_law_and_rollout', {
            'law_spec': {'ax': 'a*x+b*y+c', 'ay': 'b*x+d*y+e'},
            'parameter_spec': [{'name': name, 'initial': 0} for name in 'abcde'],
            'train_probe_ids': list(runtime.store.records['probe']),
        })
        assert fitted['ok']
        arguments = {'law_id': fitted['data']['law_id'],
                     'claims': {'dynamics_order': 2, 'hidden_matter': False, 'time_dependence': False},
                     'physical_explanation': explanation}
        client, requests = make_client(tmp_path, monkeypatch, [response(
            assistant(calls=[call(arguments=json.dumps(arguments))]), 'tool_calls')])
        result = Agent(client, runtime, tmp_path, {}).run()
    assert result['status'] == 'submitted'
    assert result['submission']['physical_explanation'] == explanation
    saved = json.loads((tmp_path / 'result.json').read_text())
    assert saved == result
    schema = next(t['function']['parameters'] for t in requests[0]['tools'] if t['function']['name'] == 'submit')
    assert 'physical_explanation' in schema['required']
    assert 'physical_explanation' in requests[0]['messages'][0]['content']
    manager = RunManager(tmp_path.parent, runs_dir=tmp_path.parent)
    try:
        snapshot = manager.snapshot(tmp_path.name)
        assert snapshot['result']['submission']['physical_explanation'] == explanation
        assert snapshot['records']['submissions'][0]['physical_explanation'] == explanation
        returned = next(e for e in snapshot['events'] if e['kind'] == 'tool_result' and e['tool'] == 'submit')
        assert returned['data']['physical_explanation'] == explanation
    finally:
        manager.close()


def test_api_failures_redacted_and_retries_count(tmp_path, monkeypatch):
    monkeypatch.setattr('shore_agent.model.time.sleep', lambda seconds: None)
    client, requests = make_client(tmp_path, monkeypatch, [
        httpx.Response(503, text='secret body must not be logged'), response(assistant())])
    client.complete([{'role': 'user', 'content': 'test'}])
    assert len(requests) == 2
    assert client.usage['calls'] == 2
    assert client.usage['roles']['main']['calls'] == 2
    assert client.usage['total_tokens'] == 30
    assert client.usage['conservative_reserved_tokens'] > 0
    assert 'secret body' not in (tmp_path / 'model_events.jsonl').read_text()


def test_retry_is_counted_but_not_blocked_by_legacy_call_limit(tmp_path, monkeypatch):
    monkeypatch.setattr('shore_agent.model.time.sleep', lambda seconds: None)
    client, requests = make_client(tmp_path, monkeypatch, [
        httpx.Response(429), response(assistant())], {'max_calls': 1, 'main_max_calls': 1})
    client.complete([])
    assert len(requests) == client.usage['calls'] == 2
    assert client.usage['conservative_reserved_tokens'] > 0
    client.close()


def test_missing_key_is_explicit_and_no_call(tmp_path, monkeypatch):
    client, requests = make_client(tmp_path, monkeypatch, [])
    monkeypatch.delenv('DEEPSEEK_API_KEY')
    with pytest.raises(ModelError, match='missing_deepseek_api_key'):
        client.complete([])
    assert client.usage['calls'] == 0 and not requests


def test_token_preflight_and_legacy_main_limit_ignored(tmp_path, monkeypatch):
    client, requests = make_client(tmp_path, monkeypatch, [], {'max_total_tokens': 100})
    with pytest.raises(ModelError, match='model_token_budget_exhausted'):
        client.complete([])
    assert not requests
    client2, requests2 = make_client(tmp_path, monkeypatch, [response(assistant())] * 3,
                                    {'max_calls': 2, 'main_max_calls': 1})
    for _ in range(3):
        client2.complete([])
    assert client2.usage['roles']['main']['calls'] == 3
    assert len(requests2) == 3
    assert 'response_format' not in requests2[0]
    client2.usage['total_tokens'] = client2.max_total_tokens
    with pytest.raises(ModelError, match='model_token_budget_exhausted'):
        client2.complete([])
    assert len(requests2) == 3
    client.close()
    client2.close()


def test_reported_prefix_allows_next_request_without_counting_all_bytes_again(tmp_path, monkeypatch):
    usage = {'prompt_tokens': 2000, 'completion_tokens': 100, 'total_tokens': 2100,
             'prompt_cache_hit_tokens': 1900}
    client, requests = make_client(tmp_path, monkeypatch,
        [response(assistant(), usage=usage)] * 2, {'max_total_tokens': 10000})
    messages = [{'role': 'user', 'content': 'text ' * 1600}]
    reply = client.complete(messages, tools=SCHEMAS[:0])
    messages += [reply, {'role': 'user', 'content': '继续'}]
    client.complete(messages)
    assert len(requests) == 2
    budget = client.usage['request_budget']
    assert budget['method'] == 'reported_prefix_plus_utf8_suffix'
    assert budget['utf8_upper_bound'] > budget['available_tokens']
    assert budget['estimated_prompt_tokens'] < budget['available_tokens']
    assert budget['reference_prompt_tokens'] == 2000  # cached tokens still count
    assert requests[1]['messages'] == messages
    assert client.usage['total_tokens'] == 4200
    client.close()


@pytest.mark.parametrize('change', ['history', 'reasoning', 'tools', 'thinking', 'model'])
def test_prompt_anchor_is_invalidated_by_changed_prefix_or_context(tmp_path, monkeypatch, change):
    client, _ = make_client(tmp_path, monkeypatch, [response(assistant())])
    messages = [assistant('old', reasoning='preserve exactly')]
    client.complete(messages, tools=SCHEMAS)
    body = {'model': client.model, 'messages': messages, 'stream': False,
            'thinking': {'type': 'enabled'}, 'reasoning_effort': client.reasoning_effort,
            'tools': SCHEMAS, 'tool_choice': 'auto'}
    assert client._prompt_estimate(body)['method'] == 'reported_prefix_plus_utf8_suffix'
    if change == 'history': messages[0]['content'] = 'new'
    elif change == 'reasoning': messages[0]['reasoning_content'] = 'changed'
    elif change == 'tools': body['tools'] = SCHEMAS[:-1]
    elif change == 'thinking': body['thinking'] = {'type': 'disabled'}
    else: body['model'] = 'another-model'
    assert client._prompt_estimate(body)['method'] == 'utf8_upper_bound'
    client.close()


def test_budget_block_records_reason_without_request_or_history_leak(tmp_path, monkeypatch):
    client, requests = make_client(tmp_path, monkeypatch, [], {'max_total_tokens': 1000})
    with pytest.raises(ModelError, match='model_token_budget_exhausted'):
        client.complete([{'role': 'user', 'content': 'confidential-marker ' * 100}])
    assert not requests and client.usage['calls'] == 0
    budget = client.usage['request_budget']
    assert budget['status'] == 'blocked' and budget['available_tokens'] == 1000
    assert budget['estimated_prompt_tokens'] > 1000
    assert budget['minimum_output_tokens'] == 64
    events = (tmp_path / 'model_events.jsonl').read_text()
    assert 'budget_blocked' in events and 'confidential-marker' not in events
    client.close()


def test_unknown_usage_is_reserved_and_cannot_calibrate_prompt(tmp_path, monkeypatch):
    payload = response(assistant()); payload.pop('usage')
    client, _ = make_client(tmp_path, monkeypatch, [payload])
    client.complete([{'role': 'user', 'content': 'test'}])
    assert client._prompt_reference is None
    assert client.usage['total_tokens'] == 0
    assert client.usage['conservative_reserved_tokens'] > 0
    client.close()


def test_retry_limit_remains_enforced_without_total_call_limit(tmp_path, monkeypatch):
    monkeypatch.setattr('shore_agent.model.time.sleep', lambda seconds: None)
    client, requests = make_client(tmp_path, monkeypatch, [httpx.Response(503)] * 2,
                                   {'max_retries': 1, 'max_calls': 1})
    with pytest.raises(ModelError, match='http_status_503'):
        client.complete([])
    assert len(requests) == client.usage['calls'] == 2
    client.close()


def test_response_after_wall_deadline_never_executes(tmp_path, monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'mock')
    clock = {'remaining': 10}

    def handler(request):
        clock['remaining'] = 0
        return httpx.Response(200, json=response(assistant(calls=[call()]), 'tool_calls'))

    client = DeepSeekClient({}, tmp_path, lambda: clock['remaining'], transport=httpx.MockTransport(handler))
    runtime = FakeRuntime()
    result = Agent(client, runtime, tmp_path, {}).run()
    assert result['reason'] == 'wall_time_exhausted'
    assert not runtime.executed
    assert client.usage['total_tokens'] == 30


def test_budget_session_end_without_data_stops_and_pairs_calls(tmp_path, monkeypatch):
    client, requests = make_client(tmp_path, monkeypatch, [response(assistant(calls=[
        call('observe_body'), call('insert_probe', 'late')]), 'tool_calls')])
    runtime = FakeRuntime()

    def execute(name, args):
        runtime.executed.append((name, args))
        return {'ok': False, 'data': None, 'error': {'code': 'expired'},
                'budget': {'session_ended': True, 'wall_seconds_remaining': 0}}

    runtime.execute = execute
    agent = Agent(client, runtime, tmp_path, {})
    result = agent.run()
    assert result['status'] == 'incomplete'
    assert len(requests) == 1 and len(runtime.executed) == 1
    assert [m['tool_call_id'] for m in agent.messages if m['role'] == 'tool'] == ['test_call_1', 'late']


def test_none_tool_budget_does_not_break_history(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch, [
        response(assistant(calls=[call()]), 'tool_calls'), response(assistant())])
    runtime = FakeRuntime()
    runtime.execute = lambda name, args: {'ok': False, 'data': None, 'error': {'code': 'unavailable'}, 'budget': None}
    agent = Agent(client, runtime, tmp_path, {'max_no_action': 1})
    assert agent.run()['status'] == 'incomplete'
    tool_message = next(m for m in agent.messages if m['role'] == 'tool')
    assert json.loads(tool_message['content'])['budget'] is None


def test_finish_refreshes_budget_after_model_elapsed_time(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch, [response(assistant(), 'length')])
    runtime = FakeRuntime()
    runtime.budget = lambda: {'wall_seconds_remaining': 35, 'session_ended': False}
    result = Agent(client, runtime, tmp_path, {}).run()
    assert result['budget']['wall_seconds_remaining'] == 35
    assert json.loads((tmp_path / 'result.json').read_text())['budget'] == result['budget']


def test_finish_budget_failure_keeps_previous_snapshot(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch, [response(assistant(), 'length')])
    runtime = FakeRuntime()

    def failed_budget():
        raise RuntimeError('backend diagnostic must not be logged')

    runtime.budget = failed_budget
    result = Agent(client, runtime, tmp_path, {}).run()
    assert result['budget'] == {'remaining_seconds': 100}
    assert 'backend diagnostic' not in (tmp_path / 'events.jsonl').read_text()


def test_project_large_output_budget_reaches_provider(tmp_path, monkeypatch):
    from pathlib import Path
    config = json.loads((Path(__file__).resolve().parents[1] / 'config.example.json').read_text())['model']
    client, requests = make_client(tmp_path, monkeypatch,
                                  [response(assistant())],
                                  config, remaining=lambda: 3600)
    client.complete([{'role': 'user', 'content': 'test'}])
    assert requests[0]['max_tokens'] == 65536
    assert client.timeout == 600
    assert client.max_total_tokens == 5000000
    assert client.usage['total_tokens'] == 30
    client.close()


@pytest.mark.parametrize('role', ['analyst', 'unknown'])
def test_removed_model_roles_rejected_before_request(tmp_path, monkeypatch, role):
    client, requests = make_client(tmp_path, monkeypatch, [], {'analyst_max_calls': 4})
    with pytest.raises(ModelError, match='invalid_model_role'):
        client.complete([], role=role)
    assert not requests
    assert client.usage['calls'] == 0
    assert set(client.usage['roles']) == {'main'}
    assert set(client.role_limits) == {'main'}
    client.close()


@pytest.mark.parametrize('config', [{}, {'max_calls': None, 'main_max_calls': None},
                                   {'max_calls': 24, 'main_max_calls': 24}])
def test_main_continues_past_old_default_and_web_call_caps(tmp_path, monkeypatch, config):
    client, requests = make_client(tmp_path, monkeypatch, [response(assistant())] * 65, config)
    assert client.max_calls is None
    assert client.role_limits == {'main': None}
    for _ in range(65):
        client.complete([])
    assert len(requests) == 65
    assert client.usage['roles']['main']['calls'] == client.usage['calls'] == 65
    configuration = json.loads((tmp_path / 'model_events.jsonl').read_text().splitlines()[0])
    assert configuration['max_calls'] is None and configuration['role_limits'] == {'main': None}
    client.close()


def test_agent_continues_past_old_turn_limit_until_accepted_submission(tmp_path, monkeypatch):
    replies = [response(assistant(calls=[call('call_back', f'lookup-{i}')]), 'tool_calls')
               for i in range(35)]
    replies.append(response(assistant(calls=[call()]), 'tool_calls'))
    client, requests = make_client(tmp_path, monkeypatch, replies)
    runtime = FakeRuntime()
    original_execute = runtime.execute

    def execute(name, args):
        if name == 'submit':
            return original_execute(name, args)
        runtime.executed.append((name, args))
        return {'ok': True, 'data': {}, 'error': None, 'budget': {'wall_seconds_remaining': 99}}

    runtime.execute = execute
    result = Agent(client, runtime, tmp_path, {'max_turns': 1, 'max_rounds': 1}).run()
    assert result['status'] == 'submitted'
    assert len(requests) == len(runtime.executed) == 36
    assert result['model_usage']['calls'] == 36
    progress = [json.loads(line) for line in (tmp_path / 'events.jsonl').read_text().splitlines()
                if json.loads(line)['event'] == 'research_progress']
    assert [event['turn'] for event in progress] == list(range(1, 37))
    client.close()
