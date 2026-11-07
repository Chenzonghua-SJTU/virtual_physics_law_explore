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


def test_search_provenance_preserved_when_parameter_holdout_is_allowed(runtime, monkeypatch):
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
    assert runtime.store.get('law', law)['discovery_probe_ids'] == ['p1','p2','p3','p4']
    assert runtime.store.get('law', law)['acquired_observation_consistency']['outside_training_probe_ids'] == ['p1','p3','p4']
    bad = runtime.execute('validate_law', {'law_id': law, 'test_probe_ids': ['p1']})
    assert bad['ok'] and bad['data']['validation_scope']=='parameter_holdout'
    assert not bad['data']['independent_of_discovery']
    assert bad['data']['discovery_overlap_probe_ids']==['p1']
    assert runtime.execute('validate_law', {'law_id':law,'test_probe_ids':['p3']})['ok']
    assert not runtime.execute('validate_law', {'law_id':law,'test_probe_ids':['p2']})['ok']
    fresh=copy.deepcopy(runtime.store.get('probe','p3')); fresh['probe_id']='fresh'
    runtime.store.add('probe',fresh,'fresh')
    good = runtime.execute('validate_law', {'law_id': law, 'test_probe_ids': ['fresh']})
    assert good['ok'] and good['data']['independent_of_discovery']
    assert good['data']['validation_scope']=='fresh_observations'
    assert any(path.startswith('analyses/sr_') for path in runtime.files.entries())


def test_later_failed_search_preserves_provenance_without_blocking_parameter_holdout(runtime, monkeypatch):
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
    assert record['discovery_probe_ids'] == ['p1','p2','p3','p4']
    assert 'private process details' not in str(record)
    assert f"analyses/{record['search_id']}.json" in result['error']['message']
    assert (runtime.run_dir/'records/symbolic_search'/f"{record['search_id']}.json").is_file()
    checked=runtime.execute('validate_law', {'law_id': law, 'test_probe_ids': ['p1']})
    assert checked['ok'] and not checked['data']['independent_of_discovery']


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
    assert len(tool_schemas(ruleset='e4', symbolic_enabled=True)) == 10
    with pytest.raises(ValueError, match='ruleset=e4 or e5'):
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


def test_model_feedback_omits_bulk_diagnostics_but_keeps_formulas_risks_and_full_archive(runtime, monkeypatch):
    candidate = {'law_spec': {'ax': '-c*x', 'ay': '-c*y'},
                 'parameter_spec': [{'name': 'c', 'initial': .2}],
                 'fitted_parameters': {'c': .2}, 'rank': 1,
                 'fit_stage': 'position_trajectory_discovery_refit',
                 'residuals': {
                     'trajectory_training': {'overall': {'position_rmse': .01, 'velocity_rmse': .02},
                         'per_probe': [{'probe_id': 'p1', 'position_rmse': .01}] * 100},
                     'observed_velocity_integral': {'complete': False, 'relative_increment_rmse': .3,
                         'domain_error_probe_ids': ['p2'], 'denominator_sign_change_probe_ids': ['p3'],
                         'per_probe': [{'probe_id': 'p1', 'relative_increment_rmse': .3}] * 100}},
                 'parameter_sharing': {'audit': ['full retained evidence'] * 1000}}
    raw = {'status': 'timeout', 'candidates': [candidate],
           'data_quality': {'per_sample': list(range(5000))},
           'search_stages': [{'debug': 'retain me'}], 'basis_diagnostics': {'audit': list(range(1000))}}
    stub_service(monkeypatch, lambda *args, **kwargs: copy.deepcopy(raw))
    reply = runtime.execute('symbolic_regression', {'train_probe_ids': ['p1'], 'time_budget_seconds': 20})
    assert reply['ok']
    data = reply['data']; delivered = data['candidates'][0]
    assert delivered['law_spec'] == candidate['law_spec']
    assert delivered['parameter_spec'] == candidate['parameter_spec']
    assert delivered['fitted_parameters'] == candidate['fitted_parameters']
    assert delivered['residuals']['observed_velocity_integral']['domain_error_probe_ids'] == ['p2']
    assert delivered['residuals']['observed_velocity_integral']['denominator_sign_change_probe_ids'] == ['p3']
    assert delivered['residuals']['observed_velocity_integral']['complete'] is False
    assert delivered['independent_validation'] is False
    assert not {'data_quality', 'search_stages', 'basis_diagnostics'} & data.keys()
    assert 'per_probe' not in delivered['residuals']['trajectory_training']
    assert len(json.dumps(reply)) < 7000
    stored = runtime.store.get('symbolic_search', data['search_id'])
    assert stored['data_quality'] == raw['data_quality']
    assert stored['candidates'][0]['residuals'] == candidate['residuals']
    assert stored['candidates'][0]['parameter_sharing'] == candidate['parameter_sharing']


def test_single_axis_over_joint_limit_is_delivered_without_becoming_a_force_law(runtime, monkeypatch):
    from shore_agent.symbolic_regression import export_candidate, FEATURES, PROPERTIES
    source = '0.11*x + 0.23*y + 0.37*vx + 0.41*vy + 0.53*t + 0.67*mass'
    axis = dict(export_candidate(source, '0', FEATURES+PROPERTIES, _parameter_limit=24),
                component='ax', source=source, parameter_count=6,
                joint_fit_ready=False, parameter_budget_compatible=False)
    stub_service(monkeypatch, lambda *args, **kwargs: {
        'status': 'timeout', 'candidates': [], 'axis_candidates': {'ax': [axis], 'ay': []}})
    result = runtime.execute('symbolic_regression', {'train_probe_ids': ['p1'], 'time_budget_seconds': 20})
    assert result['ok']
    data = result['data']
    assert data['outcome'] == 'budget_ended_with_candidates'
    assert data['axis_candidates']['ax'][0]['parameter_spec'] == axis['parameter_spec']
    assert data['axis_candidates']['ax'][0]['discovery_probe_ids'] == ['p1']
    assert data['candidates'] == []
    fit_result = runtime.execute('fit_law_and_rollout', {
        'law_spec': axis['law_spec'], 'parameter_spec': axis['parameter_spec'], 'train_probe_ids': ['p1']})
    assert not fit_result['ok']


def test_coverage_reports_omitted_property_controls_without_training_on_them(runtime, monkeypatch):
    runtime.store.records['probe']['p1']['initial_conditions']['properties'] = {'mass': 1, 'charge': 1}
    runtime.store.records['probe']['p2']['initial_conditions']['properties'] = {'mass': 2, 'charge': 1}
    runtime.store.records['probe']['p3']['initial_conditions']['properties'] = {'mass': 1, 'charge': 3}
    used = []
    def search(probes, seconds, **kwargs):
        used.extend(p['probe_id'] for p in probes)
        return {'status': 'completed', 'candidates': []}
    stub_service(monkeypatch, search)
    result = runtime.execute('symbolic_regression', {'train_probe_ids': ['p1'], 'time_budget_seconds': 20})
    coverage = result['data']['input_coverage']
    assert coverage['unselected_acquired_property_contrasts'] == {'mass': ['p2'], 'charge': ['p3']}
    assert used == ['p1'] and runtime.discovery_probe_ids == {'p1'}
    assert coverage['absolute_time_range'] == [0, 1]
    assert coverage['sample_interval_range'] == [.5, .5]


def test_forged_axis_ready_flag_is_not_accepted(runtime, monkeypatch):
    stub_service(monkeypatch, lambda *args, **kwargs: {
        'status': 'completed', 'candidates': [], 'axis_candidates': {'ax': [{'joint_fit_ready': True}]}})
    result = runtime.execute('symbolic_regression', {'train_probe_ids': ['p1'], 'time_budget_seconds': 20})
    assert not result['ok'] and result['error']['code'] == 'invalid_service_response'


def test_coverage_does_not_mask_failure_for_single_observation(runtime, monkeypatch):
    probe = runtime.store.records['probe']['p1']
    for key in ('times', 'r_obs', 'v_obs'):
        probe[key] = probe[key][:1]
    def failed(*args, **kwargs):
        raise ValueError('Insufficient derivative samples')
    stub_service(monkeypatch, failed)
    result = runtime.execute('symbolic_regression', {'train_probe_ids': ['p1'], 'time_budget_seconds': 20})
    assert result['error']['code'] == 'symbolic_service_unavailable'
    record = next(iter(runtime.store.records['symbolic_search'].values()))
    assert record['input_coverage']['sample_interval_range'] is None
    assert record['input_coverage']['insufficient_sample_probe_ids'] == ['p1']
    assert record['used_probe_ids'] == ['p1']


def test_compact_feedback_exposes_actionable_gaps_without_full_search_audit():
    from shore_agent.symbolic_feedback import search_feedback
    raw={'search_id':'sr_test','candidates':[],
         'basis_diagnostics':{'time_modulation':{'status':'unresolved',
             'reason':'frequency_minimum_at_resolution_boundary','observed_time_span':2.4,
             'temporal_alias_risk':True,'large_private_fit_table':list(range(10000))}},
         'input_coverage':{'unselected_acquired_property_contrasts':{'mass':['p8']}}}
    reply=search_feedback(raw)
    gaps=reply['research_gaps']
    assert gaps[0]['observed_time_span']==2.4 and gaps[0]['temporal_alias_risk'] is True
    assert gaps[0]['reason']=='frequency_minimum_at_resolution_boundary'
    assert 'longer continuous' in gaps[0]['action']
    assert gaps[1]['probe_ids']=={'mass':['p8']}
    assert 'large_private_fit_table' not in json.dumps(reply)
    assert 'basis_diagnostics' not in reply
