"""Hard submission gate uses saved selected-law fit error, never evaluation truth."""
import copy
import json
import time

import pytest

from shore_agent.agent import Agent
from shore_agent.model import ModelError
from shore_agent.runtime import SubmissionFitGateError, ToolRuntime
from test_agent_stagnation import Client, call, reply


CLAIMS = {'dynamics_order': 2, 'hidden_matter': False, 'time_dependence': False}


class Console:
    ruleset = 'e5'

    def __init__(self):
        self.remaining, self.ended, self.end_calls = 180., False, 0

    def request(self, name):
        if name == 'budget':
            return {'ok': True, 'budget': {'energy_remaining': 0, 'observations_remaining': 20,
                                          'wall_seconds_remaining': self.remaining, 'session_ended': self.ended}}
        assert name == 'end_session'
        self.ended = True
        self.end_calls += 1
        return {'ok': True, 'data': {'session_ended': True}}


def make_runtime(tmp_path, *, error=.01, symbolic=True):
    runtime = ToolRuntime(Console(), tmp_path, {'symbolic_regression_enabled': symbolic})
    runtime.task = {'position_noise_sigma': 0, 'reference_length': 1, 'allowed_properties': []}
    probe = {'probe_id': 'p1', 'times': [0., .1, .2], 'r_obs': [[1., 0.]]*3, 'v_obs': [[0., 0.]]*3,
             'initial_conditions': {'r0': [1., 0.], 'v0': [0., 0.], 't0': 0., 'properties': {}}}
    runtime.store.add('probe', probe, 'p1')
    law = {'law_id': 'selected', 'law_spec': {'ax': '0', 'ay': '0'}, 'parameter_spec': [],
           'fitted_parameters': {}, 'train_probe_ids': ['p1'], 'known_bodies': [],
           'fit_status': 'converged', 'errors': {'overall': {'position_rmse': error}}}
    runtime.store.add('law', law, 'selected')
    runtime.mission = lambda: {'ok': True, 'data': {}, 'budget': runtime.budget()}
    return runtime


def arguments():
    return {'law_id': 'selected', 'claims': dict(CLAIMS),
            'physical_explanation': 'Synthetic gate fixture; no claim about any real universe.'}


@pytest.mark.parametrize('error,remaining,allowed', [
    (0., 180., True), (9.999e-6, 180., True), (1e-5, 180., False),
    (.01, 40., False), (1e-5, 40., False), (.01, 39.999, True), (.01, 39., True),
])
def test_runtime_enforces_strict_or_boundaries(tmp_path, error, remaining, allowed):
    runtime = make_runtime(tmp_path, error=error)
    runtime.environment.remaining = remaining
    response = runtime.execute('submit', arguments())
    assert response['ok'] is allowed
    assert runtime.session_ended is allowed
    assert runtime.environment.end_calls == int(allowed)
    assert response['budget']['energy_remaining'] == 0
    if allowed:
        gate = response['data']['submission_gate']
        assert response['data']['status'] == 'accepted'
        assert gate['allowed'] and (gate['fit_condition_met'] or gate['time_condition_met'])
    else:
        assert response['error']['code'] == 'submission_fit_gate_not_met'
        assert response['error']['submission_gate']['fit_position_rmse'] == error
        assert response['error']['submission_gate']['wall_seconds_remaining'] == remaining
        assert response['error']['temporary_rejection']
        assert runtime.store.records['submission'] == {}
        assert not (tmp_path/'submissions').exists()


@pytest.mark.parametrize('error', [None, -1., float('nan'), float('inf'), True, '0.000001'])
def test_invalid_or_missing_fit_error_cannot_pass_fit_branch(tmp_path, error):
    runtime = make_runtime(tmp_path)
    law = {'law_id': 'selected', 'errors': {'overall': {'position_rmse': error}}}
    report = runtime.submission_eligibility(law)
    assert not report['allowed'] and not report['fit_error_valid']
    assert not report['fit_condition_met']
    json.dumps(report, allow_nan=False)
    runtime.environment.remaining = 39.
    assert runtime.submission_eligibility(law)['allowed']


def test_selected_law_only_and_direct_entry_cannot_bypass_gate(tmp_path):
    runtime = make_runtime(tmp_path)
    other = copy.deepcopy(runtime.store.get('law', 'selected'))
    other.update(law_id='other', errors={'overall': {'position_rmse': 0.}})
    runtime.store.add('law', other, 'other')
    with pytest.raises(SubmissionFitGateError):
        runtime.submit(**arguments())
    assert not runtime.session_ended
    assert runtime.submission_eligibility(other)['allowed']


def test_save_draft_allowed_but_early_fallback_cannot_bypass(tmp_path):
    runtime = make_runtime(tmp_path)
    saved = runtime.execute('save_draft', arguments())
    assert saved['ok'] and saved['data']['status'] == 'saved'
    assert runtime.finalize_draft('api_timeout') is None
    assert not runtime.session_ended and runtime.environment.end_calls == 0
    assert not (tmp_path/'submissions').exists()
    assert runtime.last_draft_finalization_gate['allowed'] is False
    runtime.environment.remaining = 39.
    sealed = runtime.finalize_draft('deadline_reserve')
    assert sealed['status'] == 'accepted'
    assert sealed['submission_gate']['time_condition_met']
    assert sealed['draft_id'] == saved['data']['draft_id']


def test_expired_timely_draft_keeps_original_bytes(tmp_path, monkeypatch):
    runtime = make_runtime(tmp_path)
    saved = runtime.execute('save_draft', arguments())['data']
    source = tmp_path/'drafts'/saved['draft_id']/'law.py'
    original = source.read_bytes()
    runtime.environment.remaining = 0.
    from shore_agent import submission
    monkeypatch.setattr(submission, 'export_submission', lambda *a, **k: pytest.fail('no new checks at expiry'))
    sealed = runtime.finalize_draft('wall_time_exhausted')
    assert sealed['status'] == 'accepted'
    assert (tmp_path/'submissions'/sealed['submission_id']/'law.py').read_bytes() == original


def test_unavailable_budget_is_not_assumed_deadline(tmp_path):
    runtime = make_runtime(tmp_path)
    unknown = {'wall_seconds_remaining': 0., 'budget_available': False, 'session_ended': True}
    law = runtime.store.get('law', 'selected')
    assert not runtime.submission_eligibility(law, unknown)['allowed']
    runtime.exploration_deadline_monotonic = time.monotonic()+200
    assert not runtime.submission_eligibility(law, unknown)['allowed']
    runtime.exploration_deadline_monotonic = time.monotonic()-1
    assert runtime.submission_eligibility(law, unknown)['time_condition_met']


def test_baseline_default_off_and_agent_configuration_can_opt_in(tmp_path):
    runtime = make_runtime(tmp_path, symbolic=False)
    assert not runtime.submission_gate_policy()['enabled']
    Agent(Client([]), runtime, tmp_path, {'submission_fit_rmse_threshold':1e-5,
                                         'submission_time_remaining_seconds':40})
    assert runtime.submission_gate_policy()['enabled']
    assert not runtime.execute('submit', arguments())['ok']


@pytest.mark.parametrize('config', [{'submission_fit_rmse_threshold':True},
                                  {'submission_fit_rmse_threshold':-1},
                                  {'submission_time_remaining_seconds':float('nan')}])
def test_invalid_configuration_fails_before_exploration(tmp_path, config):
    runtime = make_runtime(tmp_path)
    with pytest.raises(ValueError):
        Agent(Client([]), runtime, tmp_path, config)


class FailedClient:
    usage = {'calls':1,'completion_tokens':0,'total_tokens':0}
    def remaining_seconds(self): return 180
    def complete(self,*a,**k): raise ModelError('api_timeout')


def test_agent_early_model_failure_with_bad_draft_remains_incomplete(tmp_path):
    runtime = make_runtime(tmp_path)
    assert runtime.execute('save_draft', arguments())['ok']
    result = Agent(FailedClient(), runtime, tmp_path, {}).run()
    assert result['status'] == 'incomplete' and result['submission'] is None
    assert result['reason'] == 'api_timeout'
    assert not result['draft_finalization_blocked_by_submission_gate']['allowed']
    assert not runtime.session_ended


def test_agent_final_30_seconds_seals_draft_without_more_model_calls(tmp_path):
    runtime = make_runtime(tmp_path)
    assert runtime.execute('save_draft', arguments())['ok']
    runtime.environment.remaining = 30.
    result = Agent(FailedClient(), runtime, tmp_path, {}).run()
    assert result['status'] == 'submitted' and result['reason'] == 'deadline_saved_draft'


def test_repeated_ineligible_submit_is_bounded_and_never_seals_early(tmp_path):
    runtime = make_runtime(tmp_path)
    assert runtime.execute('save_draft', arguments())['ok']
    client = Client([reply(call('submit', arguments(), ident=f'submit-{i}')) for i in range(8)])
    agent = Agent(client, runtime, tmp_path, {'loop_recovery':True})
    result = agent.run()
    assert result['status'] == 'incomplete' and result['submission'] is None
    assert client.usage['calls'] == 4
    assert runtime.environment.end_calls == 0
    assert not (tmp_path/'submissions').exists()
    events = [json.loads(line) for line in (tmp_path/'events.jsonl').read_text().splitlines()]
    feedback = [event for event in events if event['event']=='loop_recovery_feedback']
    assert any(event.get('temporary_submission_gate_rejection') for event in feedback)


def test_crossing_time_threshold_releases_previous_repeat_rejections(tmp_path):
    runtime = make_runtime(tmp_path)
    class CrossingClient(Client):
        def complete(self, *args, **kwargs):
            if self.usage['calls'] == 2:
                runtime.environment.remaining = 39.
            return super().complete(*args, **kwargs)
    client = CrossingClient([reply(call('submit', arguments(), ident=f'c{i}')) for i in range(3)])
    result = Agent(client, runtime, tmp_path, {'loop_recovery':True}).run()
    assert result['status'] == 'submitted'
    assert client.usage['calls'] == 3
    assert result['submission']['submission_gate']['time_condition_met']


def test_satisfied_fit_or_does_not_gain_validation_or_candidate_adoption_gate(tmp_path):
    runtime = make_runtime(tmp_path, error=1e-6)
    runtime.store.add('validation', {'law_id':'selected', 'errors':{
        'per_probe':[{'probe_id':'p1', 'position_rmse':10.}]}}, 'diagnostic_only')
    runtime.store.add('symbolic_search', {'candidates':[{'law_spec':{'ax':'-c*x','ay':'-c*y'},
        'parameter_spec':[{'name':'c','initial':1.}]}]}, 'unused_candidate')
    client = Client([reply(call('submit', arguments()))])
    agent = Agent(client, runtime, tmp_path, {'loop_recovery':True})
    result = agent.run()
    assert result['status'] == 'submitted' and client.usage['calls'] == 1
    assert result['submission']['submission_gate']['fit_condition_met']
    assert not agent._symbolic_submission_reviewed
