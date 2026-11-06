"""Synthetic SSE protocol checks; no model capability or network claims."""
import copy
import json

import httpx
import pytest

from shore_agent.agent import Agent
from shore_agent.model import DeepSeekClient, ModelError
from test_model import FakeRuntime


MODELS = ('qwen3.8-27b', 'qwen3.6-35b-a3b', 'qwen3.5-122b-a10b')
USAGE = {'prompt_tokens': 31, 'completion_tokens': 12, 'total_tokens': 43}


def chunk(delta=None, finish=None, **extra):
    return {'model': MODELS[0], 'choices': [{'index': 0, 'delta': delta or {},
                                            'finish_reason': finish}], **extra}


def wire(chunks, *, done=True):
    result = ''.join('data: ' + json.dumps(item, ensure_ascii=False) + '\n\n' for item in chunks)
    return (result + ('data: [DONE]\n\n' if done else '')).encode('utf-8')


def answer_stream(text='ready', *, usage=True):
    chunks = [chunk({'role': 'assistant'}), chunk({'content': text}), chunk(finish='stop')]
    if usage:
        chunks.append({'choices': [], 'usage': USAGE})
    return wire(chunks)


class BytesStream(httpx.SyncByteStream):
    def __init__(self, data, width=11):
        self.data, self.width = data, width
        self.closed = False

    def __iter__(self):
        # Split JSON, UTF-8 codepoints and SSE delimiters across network chunks.
        for offset in range(0, len(self.data), self.width):
            yield self.data[offset:offset + self.width]

    def close(self):
        self.closed = True


def client(tmp_path, monkeypatch, streams, *, remaining=None, **overrides):
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'unit-qwen-credential')
    requests, received = [], []
    responses = iter(streams)

    def handler(request):
        requests.append(request)
        data = next(responses)
        if isinstance(data, httpx.Response):
            return data
        stream = data if isinstance(data, httpx.SyncByteStream) else BytesStream(data)
        received.append(stream)
        return httpx.Response(200, stream=stream, headers={'content-type': 'text/event-stream'})

    config = {'model': MODELS[0], 'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
              'reasoning_protocol': 'qwen', 'api_key_env': 'DASHSCOPE_API_KEY',
              'thinking': True, 'reasoning_effort': 'high', 'max_total_tokens': 500000,
              'max_retries': 0, **overrides}
    value = DeepSeekClient(config, tmp_path, remaining or (lambda: 100),
                           transport=httpx.MockTransport(handler))
    return value, requests, received


@pytest.mark.parametrize('model', MODELS)
@pytest.mark.parametrize('thinking', [True, False])
def test_qwen_wire_uses_own_thinking_protocol_and_streaming(tmp_path, monkeypatch, model, thinking):
    value, requests, streams = client(tmp_path, monkeypatch, [answer_stream('就绪')],
                                      model=model, thinking=thinking)
    try:
        returned = value.complete([{'role': 'user', 'content': 'test'}])
    finally:
        value.close()
    body = json.loads(requests[0].content)
    assert body['model'] == model
    assert body['enable_thinking'] is thinking
    assert body['stream'] is True and body['stream_options'] == {'include_usage': True}
    assert 'thinking' not in body and 'reasoning_effort' not in body
    assert 'chat_template_kwargs' not in body

    assert str(requests[0].url).endswith('/compatible-mode/v1/chat/completions')
    assert returned == {'role': 'assistant', 'content': '就绪'}
    assert value.usage['total_tokens'] == 43 and value.usage['conservative_reserved_tokens'] == 0
    assert all(stream.closed for stream in streams)
    events = [json.loads(line) for line in (tmp_path / 'model_events.jsonl').read_text().splitlines()]
    assert all(event['requested_reasoning_effort'] is None for event in events)
    assert 'unit-qwen-credential' not in ''.join(path.read_text() for path in tmp_path.iterdir())


@pytest.mark.parametrize('thinking', [False, True])
def test_local_qwen_uses_vllm_template_switch(tmp_path, monkeypatch, thinking):
    value, requests, _ = client(tmp_path, monkeypatch, [answer_stream()],
        deployment='local', base_url='http://127.0.0.1:8000/v1', thinking=thinking,
        api_key_env='UNCONFIGURED_LOCAL_KEY', api_key_required=False)
    try:
        value.complete([{'role': 'user', 'content': 'test'}])
    finally:
        value.close()
    body = json.loads(requests[0].content)
    assert body['chat_template_kwargs'] == {'enable_thinking': thinking}
    assert 'enable_thinking' not in body and 'reasoning_effort' not in body
    assert 'authorization' not in requests[0].headers


def tool_chunks():
    return [
        chunk({'role': 'assistant', 'reasoning_content': 'first '}),
        chunk({'reasoning_content': 'second', 'content': '实验'}),
        chunk({'tool_calls': [
            {'index': 0, 'id': 'call_0', 'type': 'function',
             'function': {'name': 'obser', 'arguments': '{"times":'}},
            {'index': 1, 'id': 'call_1', 'type': 'function',
             'function': {'name': 'list_files', 'arguments': '{'}},
        ]}),
        chunk({'tool_calls': [
            {'index': 1, 'function': {'arguments': '}'}},
            {'index': 0, 'function': {'name': 've_body', 'arguments': '[0,1]}'}},
        ]}),
        chunk(finish='tool_calls'), {'choices': [], 'usage': USAGE},
    ]


def test_interleaved_tool_deltas_and_reasoning_survive_roundtrip(tmp_path, monkeypatch):
    value, requests, _ = client(tmp_path, monkeypatch, [wire(tool_chunks()), answer_stream()])
    tools = [{'type': 'function', 'function': {'name': 'observe_body', 'parameters': {}}}]
    messages = [{'role': 'user', 'content': 'test'}]
    try:
        result = value.complete(messages, tools)
        assert result['reasoning_content'] == 'first second'
        assert result['content'] == '实验'
        assert result['tool_calls'] == [
            {'id': 'call_0', 'type': 'function', 'function': {'name': 'observe_body', 'arguments': '{"times":[0,1]}'}},
            {'id': 'call_1', 'type': 'function', 'function': {'name': 'list_files', 'arguments': '{}'}},
        ]
        messages += [result, {'role': 'tool', 'tool_call_id': 'call_0', 'content': '{}'},
                     {'role': 'tool', 'tool_call_id': 'call_1', 'content': '{}'}]
        original = copy.deepcopy(messages)
        value.complete(messages, tools)
        assert messages == original
        assert json.loads(requests[1].content)['messages'] == original
        assert json.loads(requests[0].content)['tool_choice'] == 'auto'
    finally:
        value.close()


@pytest.mark.parametrize('data,code', [
    (wire(tool_chunks(), done=False), 'incomplete_api_stream'),
    (wire(tool_chunks()[:-2]), 'incomplete_api_stream'),
    (b'data: {broken}\n\n', 'invalid_api_stream'),
    (wire([{'error': {'message': 'sensitive server detail'}}]), 'api_stream_error'),
    (wire([chunk(finish='tool_calls')]), 'invalid_api_stream'),
    (wire([chunk({'tool_calls': [{'index': -1}]})]), 'invalid_api_stream'),
    (wire([chunk({'role': 'system'})]), 'invalid_api_stream'),
    (wire([{'choices': [{'index': 1, 'delta': {}}]}]), 'invalid_api_stream'),
    (wire([chunk(finish='stop'), chunk({'content': 'late'})]), 'invalid_api_stream'),
    (wire([chunk(finish='unrecognized')]), 'invalid_api_stream'),
    (b'{"choices": []}', 'invalid_api_stream'),
])
def test_invalid_or_truncated_stream_never_executes_tools(tmp_path, monkeypatch, data, code):
    value, requests, streams = client(tmp_path, monkeypatch, [data])
    runtime = FakeRuntime()
    try:
        result = Agent(value, runtime, tmp_path, {}).run()
    finally:
        value.close()
    assert result['status'] != 'submitted'
    assert code in result['reason']
    assert runtime.executed == []
    assert len(requests) == 1
    assert value.usage['conservative_reserved_tokens'] > 0
    assert all(stream.closed for stream in streams)
    assert 'sensitive server detail' not in ''.join(path.read_text() for path in tmp_path.iterdir())


def test_length_completion_never_executes_complete_tool_call(tmp_path, monkeypatch):
    data = tool_chunks()
    data[-2] = chunk(finish='length')
    value, _, _ = client(tmp_path, monkeypatch, [wire(data)])
    runtime = FakeRuntime()
    try:
        result = Agent(value, runtime, tmp_path, {}).run()
    finally:
        value.close()
    assert result['reason'] == 'model_finish_length'
    assert runtime.executed == []
    assert value.usage['total_tokens'] == 43


def test_missing_usage_retains_full_reservation(tmp_path, monkeypatch):
    value, _, _ = client(tmp_path, monkeypatch, [answer_stream(usage=False)])
    try:
        assert value.complete([{'role': 'user', 'content': 'test'}])['content'] == 'ready'
    finally:
        value.close()
    assert value.usage['total_tokens'] == 0
    assert value.usage['conservative_reserved_tokens'] > 0


def test_wall_budget_checked_during_stream_and_stream_closed(tmp_path, monkeypatch):
    remaining = [100]

    class ExpiringStream(BytesStream):
        def __iter__(self):
            yield wire([chunk({'content': 'partial'})], done=False)
            remaining[0] = 0
            yield wire([chunk(finish='stop')])

    value, _, streams = client(tmp_path, monkeypatch, [ExpiringStream(b'')],
                                remaining=lambda: remaining[0])
    try:
        with pytest.raises(ModelError, match='wall_time_exhausted'):
            value.complete([{'role': 'user', 'content': 'test'}])
    finally:
        value.close()
    assert streams[0].closed


def test_http_error_is_redacted_and_retry_is_accounted(tmp_path, monkeypatch):
    monkeypatch.setattr('shore_agent.model.time.sleep', lambda _: None)
    value, requests, _ = client(tmp_path, monkeypatch, [
        httpx.Response(503, json={'error': {'message': 'never-log-service-error'}}), answer_stream()],
        max_retries=1)
    try:
        assert value.complete([{'role': 'user', 'content': 'test'}])['content'] == 'ready'
    finally:
        value.close()
    assert len(requests) == 2 and value.usage['calls'] == 2
    assert value.usage['total_tokens'] == 43 and value.usage['conservative_reserved_tokens'] > 0
    assert 'never-log-service-error' not in ''.join(path.read_text() for path in tmp_path.iterdir())


def test_qwen_agent_can_finish_a_tool_turn(tmp_path, monkeypatch):
    data = wire([chunk({'role': 'assistant', 'reasoning_content': 'protocol fixture'}),
                 chunk({'tool_calls': [{'index': 0, 'id': 'submit_1', 'type': 'function',
                                        'function': {'name': 'submit', 'arguments': '{}'}}]}),
                 chunk(finish='tool_calls'), {'choices': [], 'usage': USAGE}])
    value, _, _ = client(tmp_path, monkeypatch, [data])
    runtime = FakeRuntime()
    try:
        result = Agent(value, runtime, tmp_path, {}).run()
    finally:
        value.close()
    assert result['status'] == 'submitted'
    assert runtime.executed == [('submit', {})]


def test_qwen_default_key_does_not_reuse_deepseek_credentials():
    from shore_agent.model import model_auth_config
    assert model_auth_config({'reasoning_protocol': 'qwen'}) == ('DASHSCOPE_API_KEY', True)
    assert model_auth_config({}) == ('DEEPSEEK_API_KEY', True)
    assert model_auth_config({'reasoning_protocol': 'qwen', 'api_key_env': 'CUSTOM_LLM_KEY'}) == ('CUSTOM_LLM_KEY', True)


def test_request_started_is_visible_before_http_returns(tmp_path, monkeypatch):
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'credential-not-for-progress')
    observed = []

    def handler(request):
        observed.append(json.loads((tmp_path / 'model_progress.json').read_text()))
        events = [json.loads(line) for line in (tmp_path / 'model_events.jsonl').read_text().splitlines()]
        assert events[-1]['event'] == 'request_started'
        assert events[-1]['call_number'] == 1
        return httpx.Response(200, content=answer_stream())

    value = DeepSeekClient({'reasoning_protocol': 'qwen'}, tmp_path, lambda: 100,
                          transport=httpx.MockTransport(handler))
    try:
        value.complete([{'role': 'user', 'content': 'private-prompt-not-for-progress'}])
    finally:
        value.close()
    assert observed[0]['phase'] == 'waiting_first_byte' and observed[0]['status'] == 'running'
    assert observed[0]['received_chunks'] == 0 and observed[0]['http_status'] is None
    assert observed[0]['started_at'] and observed[0]['updated_at']
    progress = json.loads((tmp_path / 'model_progress.json').read_text())
    assert progress['status'] == 'completed' and progress['finish_reason'] == 'stop'
    assert progress['http_status'] == 200 and progress['received_characters'] == len('ready')
    assert not (tmp_path / '.model_progress.json.tmp').exists()
    public = (tmp_path / 'model_progress.json').read_text() + (tmp_path / 'model_events.jsonl').read_text()
    assert 'credential-not-for-progress' not in public and 'private-prompt-not-for-progress' not in public


def test_stream_progress_is_throttled_but_phase_changes_publish_immediately(tmp_path, monkeypatch):
    clock = [100.]
    monkeypatch.setattr('shore_agent.model.time.monotonic', lambda: clock[0])
    snapshots = []

    class ObservedStream(BytesStream):
        def __iter__(self):
            for seconds, delta in [(0., {'reasoning_content': 'private'}),
                                   (1., {'reasoning_content': '-more'}),
                                   (2.1, {'reasoning_content': '-still'}),
                                   (2.2, {'content': 'public-answer'})]:
                clock[0] = 100. + seconds
                yield wire([chunk(delta)], done=False)
                snapshots.append(json.loads((tmp_path / 'model_progress.json').read_text()))
            yield wire([chunk(finish='stop'), {'choices': [], 'usage': USAGE}])

    value, _, _ = client(tmp_path, monkeypatch, [ObservedStream(b'')])
    try:
        result = value.complete([{'role': 'user', 'content': 'test'}])
    finally:
        value.close()
    assert result['reasoning_content'] == 'private-more-still'
    assert [item['phase'] for item in snapshots] == ['thinking', 'thinking', 'thinking', 'content']
    assert snapshots[0]['reasoning_characters'] == len('private')
    assert snapshots[1]['reasoning_characters'] == len('private')  # Throttled in the same phase.
    assert snapshots[2]['reasoning_characters'] == len('private-more-still')
    assert snapshots[3]['content_characters'] == len('public-answer')
    assert snapshots[3]['elapsed_seconds'] == pytest.approx(2.2)
    progress = (tmp_path / 'model_progress.json').read_text()
    assert 'private' not in progress and 'public-answer' not in progress


def test_failed_stream_progress_has_a_safe_error_and_partial_counts(tmp_path, monkeypatch):
    value, _, _ = client(tmp_path, monkeypatch,
                         [wire([chunk({'reasoning_content': 'private ongoing thought'})], done=False)])
    try:
        with pytest.raises(ModelError, match='incomplete_api_stream'):
            value.complete([{'role': 'user', 'content': 'test'}])
    finally:
        value.close()
    progress = json.loads((tmp_path / 'model_progress.json').read_text())
    assert progress['status'] == 'error' and progress['phase'] == 'error'
    assert progress['error'] == 'incomplete_api_stream'
    assert progress['reasoning_characters'] == len('private ongoing thought')
    assert progress['finish_reason'] is None
    assert 'private ongoing thought' not in json.dumps(progress)


def test_progress_write_failure_does_not_change_model_turn(tmp_path, monkeypatch):
    # A telemetry filename conflict must not create an extra model call or stop discovery.
    (tmp_path / 'model_progress.json').mkdir()
    value, requests, _ = client(tmp_path, monkeypatch, [answer_stream()])
    try:
        assert value.complete([{'role': 'user', 'content': 'test'}])['content'] == 'ready'
    finally:
        value.close()
    assert len(requests) == 1
    assert not (tmp_path / '.model_progress.json.tmp').exists()


@pytest.mark.parametrize('thinking,budget,expected', [
    (True, None, None), (True, 8192, 8192), (False, 8192, None),
])
def test_thinking_budget_is_opt_in_and_only_sent_when_thinking(tmp_path, monkeypatch,
                                                             thinking, budget, expected):
    config = {'thinking': thinking}
    if budget is not None:
        config['thinking_budget'] = budget
    value, requests, _ = client(tmp_path, monkeypatch, [answer_stream()], **config)
    try:
        value.complete([{'role': 'user', 'content': 'test'}])
    finally:
        value.close()
    body = json.loads(requests[0].content)
    if expected is None:
        assert 'thinking_budget' not in body
    else:
        assert body['thinking_budget'] == expected
    assert body['max_tokens'] == 4096  # Existing output and total-budget policy is unchanged.
    assert value.max_total_tokens == 500000


@pytest.mark.parametrize('budget', [True, 0, -1, 1.5, float('inf'), '8192'])
def test_invalid_thinking_budget_fails_before_http(tmp_path, monkeypatch, budget):
    with pytest.raises(ValueError, match='thinking_budget'):
        client(tmp_path, monkeypatch, [], thinking_budget=budget)


def test_qwen_thinking_budget_is_not_sent_to_deepseek(tmp_path, monkeypatch):
    from test_model import make_client, response, assistant
    value, requests = make_client(tmp_path, monkeypatch, [response(assistant())],
                                  config={'thinking_budget': 8192})
    try:
        value.complete([{'role': 'user', 'content': 'test'}])
    finally:
        value.close()
    assert 'thinking_budget' not in requests[0]


def test_e4_caps_actual_wire_request_and_disables_thinking(tmp_path, monkeypatch):
    value, requests, _ = client(tmp_path, monkeypatch, [answer_stream()], ruleset='e4',
                                max_tokens_per_call=65536, thinking=True, thinking_budget=8192)
    try:
        value.complete([{'role': 'user', 'content': 'test'}])
    finally:
        value.close()
    body = json.loads(requests[0].content)
    assert body['max_tokens'] == 4096
    assert body['enable_thinking'] is False
    assert 'thinking_budget' not in body
