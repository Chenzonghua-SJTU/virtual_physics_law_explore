"""Search provenance, unchanged baseline tools, and budget accounting."""
import copy
import json
import sys
from types import ModuleType

import pytest

from shore_agent.runtime import ToolRuntime
from shore_agent.schemas import tool_schemas


class Environment:
    ruleset = 'e5'
    remaining = 100

    def request(self, name):
        assert name == 'budget'
        return {'ok': True, 'budget': {'wall_seconds_remaining': self.remaining,
                'energy_remaining': 10, 'session_ended': False}}


@pytest.fixture
def runtime(tmp_path):
    rt = ToolRuntime(Environment(), tmp_path, {'symbolic_regression_enabled': True})
    rt.task = {'position_noise_sigma': 0}
    rt.known_bodies = [{'position': [0, 0]}]
    for i in range(1, 5):
        record = {'probe_id': f'p{i}', 'times': [0, .5, 1],
            'initial_conditions': {'r0': [i, 0], 'v0': [1, 0], 't0': 0, 'properties': {}},
            'r_obs': [[i, 0], [i+.5, 0], [i+1, 0]], 'v_obs': [[1, 0]]*3,
            'a_est_times': [.5], 'a_est': [[0, 0]]}
        rt.store.add('probe', record, record['probe_id'])
    return rt


def stub_service(monkeypatch, callback):
    module = ModuleType('shore_agent.symbolic_service')
    module.search_remote = callback
    monkeypatch.setitem(sys.modules, 'shore_agent.symbolic_service', module)


def fit(rt, ids):
    return rt.execute('fit_law_and_rollout', {'law_spec': {'ax': '0', 'ay': '0'},
                                            'parameter_spec': [], 'train_probe_ids': ids})


def test_search_provenance_cannot_be_laundered_through_disjoint_parameter_fit(runtime, monkeypatch):
    before = copy.deepcopy(runtime.store.records['probe'])
    def search(probes, seconds, **kwargs):
        assert [p['probe_id'] for p in probes] == ['p1']
        return {'status': 'completed', 'used_probe_ids': ['forged'], 'candidates': [
            {'law_spec': {'ax': '0', 'ay': '0'}, 'parameter_spec': []}]}
    stub_service(monkeypatch, search)
    found = runtime.execute('symbolic_regression', {'train_probe_ids': ['p1'], 'time_budget_seconds': 30})
    assert found['ok'] and found['data']['used_probe_ids'] == ['p1']
    assert found['budget']['energy_remaining'] == 10
    assert runtime.store.records['probe'] == before
    law = fit(runtime, ['p2'])['data']['law_id']
    assert runtime.store.get('law', law)['discovery_probe_ids'] == ['p1']
    bad = runtime.execute('validate_law', {'law_id': law, 'test_probe_ids': ['p1']})
    assert not bad['ok'] and 'overlap' in bad['error']['message']
    good = runtime.execute('validate_law', {'law_id': law, 'test_probe_ids': ['p3']})
    assert good['ok']
    assert any(path.startswith('analyses/sr_') for path in runtime.files.entries())


def test_later_search_also_excludes_data_from_independent_validation(runtime, monkeypatch):
    law = fit(runtime, ['p2'])['data']['law_id']
    def unavailable(*args, **kwargs):
        raise RuntimeError('private process details')
    stub_service(monkeypatch, unavailable)
    result = runtime.execute('symbolic_regression', {'train_probe_ids': ['p1'], 'time_budget_seconds': 20})
    assert not result['ok'] and result['error']['code'] == 'symbolic_service_unavailable'
    assert 'private process details' not in str(result)
    records = runtime.store.records['symbolic_search']
    assert len(records) == 1
    record = next(iter(records.values()))
    assert record['status'] == 'unavailable' and record['used_probe_ids'] == ['p1']
    assert record['discovery_probe_ids'] == ['p1']
    assert 'private process details' not in str(record)
    assert f"analyses/{record['search_id']}.json" in result['error']['message']
    assert (runtime.run_dir/'records/symbolic_search'/f"{record['search_id']}.json").is_file()
    assert not runtime.execute('validate_law', {'law_id': law, 'test_probe_ids': ['p1']})['ok']


@pytest.mark.parametrize('code', ['symbolic_service_busy', 'symbolic_service_unavailable',
    'symbolic_worker_failed', 'symbolic_search_failed', 'invalid_service_response',
    'invalid_worker_result', 'invalid_symbolic_endpoint'])
def test_service_failure_codes_are_preserved_without_backend_details(runtime, monkeypatch, code):
    class Failure(RuntimeError):
        pass
    def search(*args, **kwargs):
        error = Failure('private /host/worker.log traceback')
        error.code = code
        raise error
    stub_service(monkeypatch, search)
    result = runtime.execute('symbolic_regression', {'train_probe_ids': ['p1'], 'time_budget_seconds': 20})
    assert not result['ok'] and result['error']['code'] == code
    record = next(iter(runtime.store.records['symbolic_search'].values()))
    assert record['error']['code'] == code and record['used_probe_ids'] == ['p1']
    assert 'private' not in json.dumps([result, record])


def test_unknown_failure_codes_and_messages_are_not_public(runtime, monkeypatch):
    def search(*args, **kwargs):
        error = RuntimeError('private exception')
        error.code = '/host/private/worker.log'
        raise error
    stub_service(monkeypatch, search)
    result = runtime.execute('symbolic_regression', {'train_probe_ids': ['p1'], 'time_budget_seconds': 20})
    assert result['error']['code'] == 'symbolic_service_unavailable'
    assert 'private' not in json.dumps([result, runtime.store.records['symbolic_search']])


@pytest.mark.parametrize('status,candidates,expected_ok,code', [
    ('completed', [], True, None),
    ('timeout', [{'law_spec': {'ax': '0', 'ay': '0'}, 'parameter_spec': []}], True, None),
    ('partial', [{'law_spec': {'ax': '0', 'ay': '0'}, 'parameter_spec': []}], True, None),
    ('timeout', [], False, 'symbolic_search_timeout'),
    ('partial', [], False, 'symbolic_search_incomplete'),
])
def test_completed_empty_and_usable_partial_are_distinct_from_failed_searches(
        runtime, monkeypatch, status, candidates, expected_ok, code):
    stub_service(monkeypatch, lambda *args, **kwargs: {
        'status': status, 'candidates': copy.deepcopy(candidates), 'search_axes_completed': ['ax']})
    result = runtime.execute('symbolic_regression', {'train_probe_ids': ['p1'], 'time_budget_seconds': 20})
    assert result['ok'] is expected_ok
    record = next(iter(runtime.store.records['symbolic_search'].values()))
    assert record['status'] == status and record['search_axes_completed'] == ['ax']
    assert record['used_probe_ids'] == ['p1']
    if expected_ok:
        assert result['error'] is None
        for candidate in result['data']['candidates']:
            assert candidate['discovery_probe_ids'] == ['p1']
    else:
        assert result['error']['code'] == code


@pytest.mark.parametrize('response,code', [
    ({'status': 'failed', 'candidates': [], 'error': {
        'code': 'symbolic_worker_failed', 'message': 'private /host/worker.log'}}, 'symbolic_worker_failed'),
    ({'status': 'completed', 'candidates': [{'law_spec': {'ax': 'private()', 'ay': '0'},
                                         'parameter_spec': []}]}, 'invalid_service_response'),
    (None, 'invalid_service_response'),
])
def test_invalid_or_explicitly_failed_responses_are_archived_as_safe_failures(
        runtime, monkeypatch, response, code):
    stub_service(monkeypatch, lambda *args, **kwargs: copy.deepcopy(response))
    result = runtime.execute('symbolic_regression', {'train_probe_ids': ['p1'], 'time_budget_seconds': 20})
    assert not result['ok'] and result['error']['code'] == code
    record = next(iter(runtime.store.records['symbolic_search'].values()))
    assert record['used_probe_ids'] == ['p1'] and record['candidates'] == []
    assert 'private' not in json.dumps([result, record])


def test_real_runtime_search_failures_activate_agent_bounded_recovery(runtime, monkeypatch):
    from shore_agent.agent import Agent
    from shore_agent.model import ModelError

    calls = []
    def unavailable(*args, **kwargs):
        calls.append(1)
        raise RuntimeError('private process details')
    stub_service(monkeypatch, unavailable)
    monkeypatch.setattr(runtime, 'mission', lambda: {'ok': True, 'data': {}, 'budget': runtime.budget()})

    class Client:
        usage = {'calls': 0, 'completion_tokens': 0, 'total_tokens': 0}
        last_finish_reason = 'tool_calls'

        def remaining_seconds(self):
            return 100

        def complete(self, messages, tools=None, role='main'):
            if self.usage['calls'] >= 6:
                raise ModelError('test_exhausted')
            self.usage = {key: value + (1 if key == 'calls' else 50) for key, value in self.usage.items()}
            return {'role': 'assistant', 'content': None, 'tool_calls': [{
                'id': f"c{self.usage['calls']}", 'type': 'function', 'function': {
                    'name': 'symbolic_regression', 'arguments': json.dumps({
                        'train_probe_ids': ['p1'], 'time_budget_seconds': 20})}}]}

    client = Client()
    result = Agent(client, runtime, runtime.run_dir, {'loop_recovery': True}).run()
    assert result['reason'] == 'repeated_tool_failure_limit'
    assert result['status'] == 'incomplete' and client.usage['calls'] == 4
    assert len(calls) == len(runtime.store.records['symbolic_search']) == 2
    events = [json.loads(line) for line in (runtime.run_dir/'events.jsonl').read_text().splitlines()]
    feedback = [event for event in events if event['event'] == 'loop_recovery_feedback']
    assert [event['same_error_failures'] for event in feedback] == [1, 2]
    assert all(event['last_error']['code'] == 'symbolic_service_unavailable' for event in feedback)
    assert 'private process details' not in json.dumps(events)


def test_search_reserves_time_and_cannot_read_unknown_probes(runtime, monkeypatch):
    called = []
    def search(probes, seconds, **kwargs):
        called.append(seconds)
        return {'status': 'completed', 'candidates': []}
    stub_service(monkeypatch, search)
    runtime.environment.remaining = 45
    assert runtime.execute('symbolic_regression', {'train_probe_ids': ['p1'], 'time_budget_seconds': 30})['ok']
    assert called == [10]
    runtime.environment.remaining = 35
    assert not runtime.execute('symbolic_regression', {'train_probe_ids': ['p1'], 'time_budget_seconds': 30})['ok']
    assert not runtime.execute('symbolic_regression', {'train_probe_ids': ['other-session'], 'time_budget_seconds': 30})['ok']
    assert called == [10]


def test_disabled_tool_surface_and_scope_are_unchanged(tmp_path):
    rt = ToolRuntime(Environment(), tmp_path)
    assert rt.schemas == tool_schemas(ruleset='e5') and len(rt.schemas) == 9
    assert not rt.execute('symbolic_regression', {'train_probe_ids': ['p1'], 'time_budget_seconds': 1})['ok']
    assert len(tool_schemas(ruleset='e5', symbolic_enabled=True)) == 10
    with pytest.raises(ValueError, match='ruleset=e5'):
        tool_schemas(ruleset='e3', symbolic_enabled=True)


def test_search_delivery_keeps_executable_fields_complete_and_audit_in_file(runtime, monkeypatch):
    # Seven IDs/features cross the generic preview threshold. The result must
    # remain usable as scientific tool arguments, not {preview, truncated}.
    for i in range(5, 8):
        record = runtime.store.get('probe', 'p1')
        record['probe_id'] = f'p{i}'
        runtime.store.add('probe', record, record['probe_id'])
    ids = [f'p{i}' for i in range(1, 8)]
    law = {'ax': 'c1*x+c2*y+c3*vx+c4*vy+c5', 'ay': 'c1*y'}
    parameters = [{'name': f'c{i}', 'initial': i / 10} for i in range(1, 6)]
    features = ['t', 'x', 'y', 'vx', 'vy', 'mass', 'charge']
    audit = {'ax': [{'source': f'x*{i}.1', 'complexity': 3} for i in range(15)]}
    stub_service(monkeypatch, lambda *args, **kwargs: {
        'status': 'completed', 'candidates': [{'law_spec': law, 'parameter_spec': parameters}],
        'feature_names': features, 'axis_equations': audit,
        'rejection_counts': {'initial_domain_failure': 2}})
    reply = runtime.execute('symbolic_regression', {'train_probe_ids': ids, 'time_budget_seconds': 20})
    assert reply['ok']
    data = reply['data']
    assert data['used_probe_ids'] == data['discovery_probe_ids'] == ids
    assert data['feature_names'] == features
    assert data['candidates'][0]['law_spec'] == law
    assert data['candidates'][0]['parameter_spec'] == parameters
    assert data['candidates'][0]['discovery_probe_ids'] == ids
    assert 'axis_equations' not in data
    saved = runtime.store.get('symbolic_search', data['search_id'])
    assert saved['axis_equations'] == audit
    assert data['audit_path'] in runtime.files.entries()
    assert data['rejection_counts']['initial_domain_failure'] == 2
