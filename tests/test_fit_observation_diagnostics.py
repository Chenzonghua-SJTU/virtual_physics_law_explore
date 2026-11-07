"""Opt-in diagnostic integration preserves completed laws and mission boundaries."""
import copy
import json
import time
from types import SimpleNamespace

import pytest

from shore_agent import diagnostics, harmonic_candidates, harmonic_diagnostics, numerics
from shore_agent.runtime import ToolRuntime
from shore_agent.schemas import tool_schemas
from test_dynamics_diagnostic_tool import Environment, probe


ARGS = {'law_spec': {'ax': '-k*x', 'ay': '-k*y'},
        'parameter_spec': [{'name': 'k', 'initial': .2}], 'train_probe_ids': ['train_a', 'train_b']}


def runtime(tmp_path, *, ruleset='e5', **flags):
    rt = ToolRuntime(Environment(ruleset), tmp_path, config={'diagnostics_enabled': True, **flags})
    rt.task = {'allowed_properties': ['mass'], 'property_controls': {'mass': {'default': 1.}},
               'position_noise_sigma': 0., 'velocity_noise_sigma': 0.,
               'reference_length': 1., 'velocity_limit': 1.}
    for pid in ('train_a', 'train_b', 'held_out'):
        rt.store.add('probe', probe(pid), pid)
    return rt


def fake_fit(monkeypatch, *, warning=True, fit_status='converged'):
    def fit(*args, **kwargs):
        return {'fit_status': fit_status, 'fitted_parameters': {'k': .2}, 'rollouts': [],
                'errors': {'overall': {'position_rmse': .1 if warning else 0., 'velocity_rmse': .1 if warning else 0.}}}
    monkeypatch.setattr(numerics, 'fit', fit)


def base_diagnostic(monkeypatch, seen=None, callback=None):
    def diagnose(probes, task, **kwargs):
        if seen is not None:
            seen.append([p['probe_id'] for p in probes])
        if callback:
            callback()
        return {'status': 'synthetic_observation_only', 'selected': [p['probe_id'] for p in probes]}
    monkeypatch.setattr(diagnostics, 'diagnose', diagnose)
    monkeypatch.setattr(diagnostics, 'summarize', lambda d: {'selected': d['selected']})


def harmonic_stub(monkeypatch, seen=None, callback=None):
    def diagnose(probes, task, *, max_seconds):
        if seen is not None:
            seen.append({'probe_ids': [p['probe_id'] for p in probes], 'max_seconds': max_seconds,
                         'task': copy.deepcopy(task)})
        if callback:
            callback()
        return {'method_version': 'harmonic_observation_diagnostics_v1', 'status': 'descriptive_comparison',
                'synthetic_coefficients': list(range(9)), 'probe_ids': [p['probe_id'] for p in probes]}
    monkeypatch.setattr(harmonic_diagnostics, 'diagnose_harmonic', diagnose)
    monkeypatch.setattr(harmonic_diagnostics, 'summarize_harmonic',
                        lambda d: {'coefficients_by_term': {f'b{i}': {'ax': i, 'ay': -i} for i in d['synthetic_coefficients']}})
    monkeypatch.setattr(harmonic_candidates, 'propose_harmonic_candidate', lambda d, t: {
        'candidate': {'law_spec': {'ax': '-k*x', 'ay': '-k*y'}, 'parameter_spec': [{'name': 'k', 'initial': .2}],
                      'evidence': {'source_errors_are_not_candidate_errors': True}}, 'reason': None})


def test_default_and_explicit_false_responses_and_archives_are_byte_identical(tmp_path, monkeypatch):
    fake_fit(monkeypatch)
    base_diagnostic(monkeypatch)
    monkeypatch.setattr('shore_agent.runtime.uuid.uuid4', lambda: SimpleNamespace(hex='a'*32))
    default = runtime(tmp_path/'default')
    explicit = runtime(tmp_path/'false', diagnostics_harmonic=False, diagnostics_on_fit=False)
    assert default.diagnostics_harmonic is default.diagnostics_on_fit is False
    for name, args in (('fit_law_and_rollout', ARGS), ('diagnose_dynamics', {'probe_ids': ['train_a']})):
        left, right = default.execute(name, copy.deepcopy(args)), explicit.execute(name, copy.deepcopy(args))
        assert left['ok'] and right['ok']
        assert json.dumps(left) == json.dumps(right)
    for kind in ('law', 'diagnostic'):
        a, b = list((default.store.directory/kind).glob('*.json')), list((explicit.store.directory/kind).glob('*.json'))
        assert len(a) == len(b) == 1
        assert a[0].read_bytes() == b[0].read_bytes()
    assert 'training_observation_diagnostic' not in default.store.get('law', 'law_1')
    assert not default._observation_diagnostic_cache


@pytest.mark.parametrize('ruleset', ['e3', 'e4', 'e5'])
def test_new_flags_off_preserve_schema_bytes_and_prior_profiles_ignore_flags(ruleset):
    before = tool_schemas(ruleset=ruleset, diagnostics_enabled=True)
    assert json.dumps(before) == json.dumps(tool_schemas(ruleset=ruleset, diagnostics_enabled=True,
                                                       diagnostics_harmonic=False, diagnostics_on_fit=False))
    if ruleset != 'e5':
        assert before == tool_schemas(ruleset=ruleset, diagnostics_enabled=True,
                                      diagnostics_harmonic=True, diagnostics_on_fit=True)


@pytest.mark.parametrize('flag', ['diagnostics_harmonic', 'diagnostics_on_fit'])
def test_flags_are_boolean(tmp_path, flag):
    with pytest.raises(ValueError, match=f'numerics.{flag} must be boolean'):
        runtime(tmp_path, **{flag: 'true'})


def test_on_fit_requires_enabled_diagnostics_in_e5(tmp_path):
    with pytest.raises(ValueError, match='requires diagnostics_enabled'):
        ToolRuntime(Environment(), tmp_path, config={'diagnostics_on_fit': True})


def test_harmonic_full_archive_and_compact_candidates_are_separate(tmp_path, monkeypatch):
    base_diagnostic(monkeypatch)
    calls = []
    harmonic_stub(monkeypatch, calls)
    rt = runtime(tmp_path, diagnostics_harmonic=True, diagnostics_compact=True)
    before = copy.deepcopy(rt.store.records['probe'])
    reply = rt.execute('diagnose_dynamics', {'probe_ids': ['train_b']})
    assert reply['ok'], reply
    data = reply['data']
    assert calls[0]['probe_ids'] == ['train_b'] and calls[0]['max_seconds'] == 2.
    assert 'harmonic_diagnostics' not in data and len(data['harmonic_summary']['coefficients_by_term']) == 9
    assert data['harmonic_candidate']['candidate']['evidence']['source_errors_are_not_candidate_errors']
    saved = rt.store.get('diagnostic', data['diagnostic_id'])
    assert saved['harmonic_diagnostics']['synthetic_coefficients'] == list(range(9))
    assert saved['diagnostics']['selected'] == ['train_b']
    assert json.loads(rt.read_file(data['full_evidence'])['content']) == saved
    assert rt.store.records['probe'] == before and not rt.store.records['law']
    assert set(rt.environment.requests) == {'budget'}


def test_harmonic_failure_does_not_swallow_base_diagnostic(tmp_path, monkeypatch):
    base_diagnostic(monkeypatch)
    monkeypatch.setattr(harmonic_diagnostics, 'diagnose_harmonic', lambda *a, **k: (_ for _ in ()).throw(ValueError('synthetic failure')))
    rt = runtime(tmp_path, diagnostics_harmonic=True, diagnostics_compact=True)
    reply = rt.execute('diagnose_dynamics', {'probe_ids': ['train_a']})
    assert reply['ok']
    assert reply['data']['diagnostic_summary']['selected'] == ['train_a']
    assert reply['data']['harmonic_summary']['status'] == 'unavailable'
    assert reply['data']['harmonic_candidate']['candidate'] is None


@pytest.mark.parametrize('stage', ['candidate', 'summary'])
def test_harmonic_translation_failure_preserves_completed_mathematical_evidence(tmp_path, monkeypatch, stage):
    base_diagnostic(monkeypatch)
    harmonic_stub(monkeypatch)
    def fail(*args, **kwargs): raise ValueError('synthetic translation failure')
    if stage == 'candidate':
        monkeypatch.setattr(harmonic_candidates, 'propose_harmonic_candidate', fail)
    else:
        monkeypatch.setattr(harmonic_diagnostics, 'summarize_harmonic', fail)
    rt = runtime(tmp_path, diagnostics_harmonic=True, diagnostics_compact=True)
    reply = rt.execute('diagnose_dynamics', {'probe_ids': ['train_a']})
    assert reply['ok']
    saved = rt.store.get('diagnostic', reply['data']['diagnostic_id'])
    assert saved['harmonic_diagnostics']['status'] == 'descriptive_comparison'
    assert saved['harmonic_diagnostics']['synthetic_coefficients'] == list(range(9))
    assert reply['data']['diagnostic_summary']['selected'] == ['train_a']
    assert reply['data'][f'harmonic_{stage}']['reason'] == f'harmonic_{stage}_failed'


def test_harmonic_wall_limit_respects_budget_and_exploration_deadline(tmp_path, monkeypatch):
    base_diagnostic(monkeypatch)
    calls = []
    harmonic_stub(monkeypatch, calls)
    rt = runtime(tmp_path, diagnostics_harmonic=True)
    rt.environment.remaining = .8
    rt.exploration_deadline_monotonic = time.monotonic()+.4
    reply = rt.execute('diagnose_dynamics', {'probe_ids': ['train_a']})
    assert reply['ok']
    assert 0 < calls[0]['max_seconds'] <= .3


def test_no_harmonic_call_when_reserve_would_exhaust_remaining_time(tmp_path, monkeypatch):
    base_diagnostic(monkeypatch)
    monkeypatch.setattr(harmonic_diagnostics, 'diagnose_harmonic', lambda *a, **k: pytest.fail('must reserve remaining wall time'))
    rt = runtime(tmp_path, diagnostics_harmonic=True)
    rt.environment.remaining = .11
    reply = rt.execute('diagnose_dynamics', {'probe_ids': ['train_a']})
    assert reply['ok']
    assert reply['data']['harmonic_diagnostics']['reason'] == 'insufficient_remaining_time_for_harmonic_diagnostic'


def test_bad_fit_uses_only_training_ids_and_preserves_immutable_law(tmp_path, monkeypatch):
    fake_fit(monkeypatch)
    seen = []
    base_diagnostic(monkeypatch, seen)
    rt = runtime(tmp_path, diagnostics_on_fit=True, diagnostics_compact=True)
    # No filesystem scans can leak an unregistered or independent evaluation file.
    (tmp_path/'evaluation.json').write_text('DO NOT READ')
    original = copy.deepcopy(rt.store.records['probe'])
    reply = rt.execute('fit_law_and_rollout', copy.deepcopy(ARGS))
    assert reply['ok'], reply
    assert seen == [ARGS['train_probe_ids']]
    data = reply['data']; evidence = data['training_observation_diagnostic']
    assert evidence['source_law_id'] == data['law_id'] and evidence['probe_ids'] == ARGS['train_probe_ids']
    assert evidence['source'] == 'completed_law_train_probe_ids_only' and evidence['status'] == 'available'
    assert evidence['observation_diagnostic']['diagnostic_summary']['selected'] == ARGS['train_probe_ids']
    law = rt.store.get('law', data['law_id'])
    assert law['fitted_parameters'] == {'k': .2} and law['fit_status'] == 'converged'
    assert 'training_observation_diagnostic' not in law
    assert json.loads((rt.store.directory/'law'/f"{data['law_id']}.json").read_text()) == law
    assert rt.store.get('diagnostic', evidence['diagnostic_id']) == evidence
    assert rt.store.records['probe'] == original and not rt.store.records['validation']


def test_explicit_and_auto_diagnostics_cache_exact_ordered_training_tuple(tmp_path, monkeypatch):
    fake_fit(monkeypatch); seen = []
    base_diagnostic(monkeypatch, seen)
    rt = runtime(tmp_path, diagnostics_on_fit=True)
    explicit = rt.execute('diagnose_dynamics', {'probe_ids': ARGS['train_probe_ids']})['data']
    first = rt.execute('fit_law_and_rollout', copy.deepcopy(ARGS))['data']
    second = rt.execute('fit_law_and_rollout', copy.deepcopy(ARGS))['data']
    assert seen == [ARGS['train_probe_ids']]
    one, two = [r['training_observation_diagnostic'] for r in (first, second)]
    assert one['cache_hit'] and two['cache_hit']
    assert one['linked_diagnostic_id'] == two['linked_diagnostic_id'] == explicit['diagnostic_id']
    assert one['diagnostic_id'] != two['diagnostic_id'] and one['source_law_id'] != two['source_law_id']
    args = dict(ARGS, train_probe_ids=list(reversed(ARGS['train_probe_ids'])))
    third = rt.execute('fit_law_and_rollout', args)
    assert third['ok'] and len(seen) == 2
    assert third['data']['training_observation_diagnostic']['cache_hit'] is False
    assert len(rt.store.records['law']) == 3
    assert len(rt._observation_diagnostic_cache) == 2


def test_cache_is_not_shared_between_runtime_sessions(tmp_path, monkeypatch):
    fake_fit(monkeypatch); seen = []
    base_diagnostic(monkeypatch, seen)
    first, second = [runtime(tmp_path/name, diagnostics_on_fit=True) for name in ('a', 'b')]
    for rt in (first, second):
        assert rt.execute('fit_law_and_rollout', copy.deepcopy(ARGS))['ok']
    assert len(seen) == 2
    assert first._observation_diagnostic_cache is not second._observation_diagnostic_cache


@pytest.mark.parametrize('warning,status', [(False, 'converged'), (True, 'failed'), (True, 'error')])
def test_no_auto_diagnostic_for_no_warning_or_failed_fit(tmp_path, monkeypatch, warning, status):
    fake_fit(monkeypatch, warning=warning, fit_status=status)
    monkeypatch.setattr(diagnostics, 'diagnose', lambda *a, **k: pytest.fail('must not diagnose this fit'))
    rt = runtime(tmp_path, diagnostics_on_fit=True)
    reply = rt.execute('fit_law_and_rollout', copy.deepcopy(ARGS))
    assert reply['ok'] and 'training_observation_diagnostic' not in reply['data']
    assert not rt.store.records['diagnostic']


@pytest.mark.parametrize('ruleset', ['e3', 'e4'])
def test_prior_profiles_do_not_run_auto_diagnostics(tmp_path, monkeypatch, ruleset):
    fake_fit(monkeypatch)
    monkeypatch.setattr(diagnostics, 'diagnose', lambda *a, **k: pytest.fail('prior profiles must not diagnose'))
    rt = runtime(tmp_path, ruleset=ruleset, diagnostics_on_fit=True, diagnostics_harmonic=True)
    reply = rt.execute('fit_law_and_rollout', copy.deepcopy(ARGS))
    assert reply['ok'] and 'training_observation_diagnostic' not in reply['data']
    assert not rt.store.records['diagnostic']


@pytest.mark.parametrize('mode', ['failure', 'insufficient_time'])
def test_unavailable_auto_diagnostic_keeps_completed_fit(tmp_path, monkeypatch, mode):
    fake_fit(monkeypatch)
    rt = runtime(tmp_path, diagnostics_on_fit=True)
    if mode == 'failure':
        monkeypatch.setattr(diagnostics, 'diagnose', lambda *a, **k: (_ for _ in ()).throw(ValueError('synthetic failure')))
    else:
        rt.environment.remaining = .11
        monkeypatch.setattr(diagnostics, 'diagnose', lambda *a, **k: pytest.fail('not enough time'))
    reply = rt.execute('fit_law_and_rollout', copy.deepcopy(ARGS))
    assert reply['ok']
    assert reply['data']['training_observation_diagnostic']['status'] == 'unavailable'
    assert rt.store.get('law', reply['data']['law_id'])['fitted_parameters'] == {'k': .2}


def test_auto_diagnostic_deadline_overrun_still_rejects_tool_but_saves_original_law(tmp_path, monkeypatch):
    fake_fit(monkeypatch)
    rt = runtime(tmp_path, diagnostics_on_fit=True)
    def expire(): rt.environment.remaining = 0.
    base_diagnostic(monkeypatch, callback=expire)
    reply = rt.execute('fit_law_and_rollout', copy.deepcopy(ARGS))
    assert not reply['ok'] and 'wall time exhausted' in reply['error']['message']
    assert rt.store.get('law', 'law_1')['fitted_parameters'] == {'k': .2}
    association = next(r for r in rt.store.records['diagnostic'].values() if r['diagnostic_kind'] == 'training_observation_diagnostic')
    assert association['status'] == 'unavailable'
    assert not rt._observation_diagnostic_cache


def test_harmonic_overrun_and_expired_cache_do_not_bypass_execute_deadline(tmp_path, monkeypatch):
    base_diagnostic(monkeypatch)
    rt = runtime(tmp_path, diagnostics_on_fit=True, diagnostics_harmonic=True)
    harmonic_stub(monkeypatch)
    assert rt.execute('diagnose_dynamics', {'probe_ids': ['train_a']})['ok']
    rt.environment.remaining = 0.
    assert not rt.execute('diagnose_dynamics', {'probe_ids': ['train_a']})['ok']
    with pytest.raises(ValueError, match='wall time exhausted'):
        rt.diagnose_dynamics(['train_a'])
    rt.environment.remaining = 1.
    def expire(): rt.environment.remaining = 0.
    harmonic_stub(monkeypatch, callback=expire)
    reply = rt.execute('diagnose_dynamics', {'probe_ids': ['train_b']})
    assert not reply['ok'] and 'wall time exhausted' in reply['error']['message']
    assert ('train_b',) not in rt._observation_diagnostic_cache


def test_fit_itself_exhausting_budget_still_fails_before_optional_math(tmp_path, monkeypatch):
    rt = runtime(tmp_path, diagnostics_on_fit=True, diagnostics_harmonic=True)
    def expired_fit(*args, **kwargs):
        rt.environment.remaining = 0.
        return {'fit_status': 'converged', 'fitted_parameters': {'k': .2}, 'rollouts': [],
                'errors': {'overall': {'position_rmse': .1, 'velocity_rmse': .1}}}
    monkeypatch.setattr(numerics, 'fit', expired_fit)
    monkeypatch.setattr(diagnostics, 'diagnose', lambda *a, **k: pytest.fail('fit already exhausted wall budget'))
    reply = rt.execute('fit_law_and_rollout', copy.deepcopy(ARGS))
    assert not reply['ok'] and 'wall time exhausted' in reply['error']['message']
    assert not rt._observation_diagnostic_cache


def test_actual_harmonic_math_and_candidate_module_integrate_without_auto_fitting(tmp_path, monkeypatch):
    from test_harmonic_diagnostics import synthetic
    probes, _, _ = synthetic()
    fake_fit(monkeypatch)
    rt = runtime(tmp_path, diagnostics_on_fit=True, diagnostics_harmonic=True, diagnostics_compact=True)
    for p in probes:
        rt.store.add('probe', p, p['probe_id'])
    args = dict(ARGS, train_probe_ids=[p['probe_id'] for p in probes])
    result = rt.execute('fit_law_and_rollout', args)
    assert result['ok'], result
    evidence = result['data']['training_observation_diagnostic']
    response = evidence['observation_diagnostic']
    assert response['harmonic_summary']['status'] == 'descriptive_comparison'
    assert len(response['harmonic_summary']['harmonic_model']['coefficients_by_term']) == 9
    assert set(response['harmonic_candidate']) >= {'candidate', 'reason'}
    saved = rt.store.get('diagnostic', response['diagnostic_id'])
    assert saved['probe_ids'] == args['train_probe_ids']
    assert saved['harmonic_diagnostics']['probe_ids'] == args['train_probe_ids']
    assert len(rt.store.records['law']) == 1 and not rt.store.records['validation'] and not rt.store.records['submission']
    assert '"held_out"' not in json.dumps(saved)
    # Exact-tuple automatic reuse does not execute another harmonic search.
    monkeypatch.setattr(harmonic_diagnostics, 'diagnose_harmonic', lambda *a, **k: pytest.fail('must reuse exact training tuple'))
    repeated = rt.execute('fit_law_and_rollout', args)
    assert repeated['ok'] and repeated['data']['training_observation_diagnostic']['cache_hit']
