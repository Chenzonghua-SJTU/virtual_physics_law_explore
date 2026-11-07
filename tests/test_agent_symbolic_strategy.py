"""Agent SR review integration with scripted replies and saved synthetic observations."""
import copy
import json
from types import SimpleNamespace

import pytest

from shore_agent.agent import Agent
from shore_agent.schemas import tool_schemas
from test_agent_stagnation import Client, Runtime, call, reply


def observation(index):
    initial = [1. + index, 1.]
    return {'probe_id': f'p{index}',
            'initial_conditions': {'r0': initial, 'v0': [.1, .2], 't0': 0.,
                                   'properties': {'mass': 1.}},
            'times': [0., .1, .2], 'v_obs': [[.1, .2]]*3,
            'r_obs': [[initial[0]+t*.1, initial[1]+t*.2] for t in (0., .1, .2)]}


class StrategyRuntime(Runtime):
    def __init__(self, *, enabled=True, seconds=180., probes=4, searched=False,
                 fit_status='converged', validation_rmse=None, trained_probes=3):
        super().__init__()
        self.symbolic_enabled = enabled
        self.seconds = seconds
        self.task = {'allowed_properties': ['mass'], 'position_noise_sigma': 0.,
                     'reference_length': 1.}
        self.schemas = tool_schemas(ruleset='e5', symbolic_enabled=enabled)
        records = {'probe': {f'p{i}': observation(i) for i in range(probes)},
                   'body_observation': {}, 'law': {}, 'validation': {}, 'symbolic_search': {}}
        records['law']['chosen'] = {'fit_status': fit_status,
                                    'train_probe_ids': list(records['probe'])[:trained_probes]}
        if searched:
            records['symbolic_search']['previous_search'] = {'status': 'completed', 'candidates': []}
        if validation_rmse is not None:
            records['validation']['validation_1'] = {'law_id': 'chosen',
                'errors': {'per_probe': [{'probe_id': 'p3', 'position_rmse': validation_rmse}]}}
        self.store = SimpleNamespace(records=records)

    def budget(self):
        return {'wall_seconds_remaining': self.seconds, 'energy_remaining': 6, 'session_ended': False}

    def execute(self, name, args):
        if name != 'insert_probe':
            return super().execute(name, args)
        self.calls.append((name, copy.deepcopy(args)))
        created = []
        for _ in args.get('probes', [{}]):
            index = len(self.store.records['probe'])
            record = observation(index)
            self.store.records['probe'][record['probe_id']] = record
            created.append(record)
        return {'ok': True, 'data': {'probes': created}, 'budget': self.budget()}


def events(directory, kind):
    return [row for row in map(json.loads, (directory/'events.jsonl').read_text().splitlines())
            if row['event'] == kind]


def scripted_agent(tmp_path, runtime, replies):
    client = Client(replies)
    agent = Agent(client, runtime, tmp_path, {'loop_recovery': True})
    result = agent.run()
    return agent, client, result


def test_symbolic_disabled_never_triggers_plan_or_submission_review(tmp_path):
    runtime = StrategyRuntime(enabled=False, fit_status='not_converged', validation_rmse=.1)
    _, client, result = scripted_agent(tmp_path, runtime, [
        reply(call('insert_probe', {'probes': [{}]}, ident='insert')),
        reply(call('submit', {'law_id': 'chosen'}, ident='submit'))])
    assert result['status'] == 'submitted'
    assert [name for name, _ in runtime.calls] == ['insert_probe', 'submit']
    assert events(tmp_path, 'symbolic_experiment_review') == []
    assert events(tmp_path, 'symbolic_submission_review') == []
    assert len(client.requests) == 2


@pytest.mark.parametrize('seconds', [100., 180.])
def test_planning_review_arrives_once_after_enough_acquired_probes(tmp_path, seconds):
    runtime = StrategyRuntime(seconds=seconds, probes=2)
    agent, client, result = scripted_agent(tmp_path, runtime, [
        reply(call('insert_probe', {'probes': [{}, {}]}, ident='first_batch')),
        reply(call('insert_probe', {'probes': [{}]}, ident='next_batch'))])
    assert result['reason'] == 'test_exhausted'
    assert [name for name, _ in runtime.calls] == ['insert_probe', 'insert_probe']
    reviews = events(tmp_path, 'symbolic_experiment_review')
    assert len(reviews) == 1 and agent._symbolic_plan_reviewed
    audit = reviews[0]['review']
    assert audit['one_time_only'] and audit['advisory_only'] and not audit['tool_executed']
    assert audit['recommended_search_seconds'] == 47
    assert audit['reviewed_probe_ids'] == ['p0', 'p1', 'p2', 'p3']
    for request in client.requests[1:]:
        feedback = [message for message in request['messages'] if message['role'] == 'user'
                    and 'symbolic_experiment_review' in message.get('content', '')]
        assert len(feedback) == 1
    # Successful observations remain successful and preserve tool protocol IDs.
    tool_messages = [message for message in agent.messages if message['role'] == 'tool']
    assert [message['tool_call_id'] for message in tool_messages] == ['first_batch', 'next_batch']
    assert all(json.loads(message['content'])['ok'] for message in tool_messages)


@pytest.mark.parametrize('options', [
    {'seconds': 99., 'probes': 2},
    {'seconds': 180., 'probes': 1},
    {'seconds': 180., 'probes': 3, 'searched': True},
])
def test_late_insufficient_or_already_searched_plans_do_not_interrupt_tools(tmp_path, options):
    runtime = StrategyRuntime(**options)
    agent, _, _ = scripted_agent(tmp_path, runtime, [
        reply(call('insert_probe', {'probes': [{}]}, ident='insert'))])
    assert len(runtime.calls) == 1
    assert not agent._symbolic_plan_reviewed
    assert events(tmp_path, 'symbolic_experiment_review') == []
    response = next(message for message in agent.messages if message['role'] == 'tool')
    assert json.loads(response['content'])['ok']


def test_failed_probe_and_unrelated_tool_do_not_consume_plan_reminder(tmp_path):
    runtime = StrategyRuntime()
    agent = Agent(Client([]), runtime, tmp_path, {})
    agent.last_budget = runtime.budget()
    assert agent._symbolic_plan_review('insert_probe', {'ok': False}) is None
    assert agent._symbolic_plan_review('read_file', {'ok': True}) is None
    assert not agent._symbolic_plan_reviewed
    assert agent._symbolic_plan_review('insert_probe', {'ok': True}) is not None


@pytest.mark.parametrize('options,reason', [
    ({'searched': False}, 'symbolic_search_not_attempted_with_available_training_data'),
    ({'searched': False, 'trained_probes': 2}, 'symbolic_search_not_attempted_with_available_training_data'),
    ({'searched': True, 'fit_status': 'not_converged'}, 'selected_fit_not_converged'),
    ({'searched': True, 'validation_rmse': .03}, 'selected_law_large_relative_validation_residual'),
])
def test_critical_submission_evidence_defers_once_then_allows_same_submission(tmp_path, options, reason):
    runtime = StrategyRuntime(**options)
    agent, client, result = scripted_agent(tmp_path, runtime, [
        reply(call('submit', {'law_id': 'chosen'}, ident='first_submit')),
        reply(call('submit', {'law_id': 'chosen'}, ident='second_submit'))])
    assert result['status'] == 'submitted'
    assert [name for name, _ in runtime.calls] == ['submit']
    reviews = events(tmp_path, 'symbolic_submission_review')
    assert len(reviews) == 1 and reviews[0]['reasons'] == [reason]
    assert reviews[0]['one_time_only'] and not reviews[0]['tool_executed']
    assert agent._symbolic_submission_reviewed
    first = next(message for message in client.requests[1]['messages'] if message['role'] == 'tool')
    result_data = json.loads(first['content'])
    assert first['tool_call_id'] == 'first_submit'
    assert not result_data['ok'] and result_data['error']['code'] == 'scientific_review_needed'
    assert result_data['error']['research_review']['law_id'] == 'chosen'
    if reason == 'selected_law_large_relative_validation_residual':
        evidence = reviews[0]['evidence']['validation_evidence']
        assert evidence[0]['validation_id'] == 'validation_1'
        assert evidence[0]['position_rmse'] == .03


@pytest.mark.parametrize('options', [
    {'seconds': 99., 'searched': False, 'fit_status': 'not_converged', 'validation_rmse': .1},
    {'seconds': 20., 'searched': False, 'fit_status': 'not_converged', 'validation_rmse': .1},
    {'probes': 2, 'searched': False},
    {'searched': True, 'validation_rmse': 1e-8},
])
def test_late_insufficient_search_data_and_low_residual_submissions_are_not_blocked(tmp_path, options):
    runtime = StrategyRuntime(**options)
    agent, client, result = scripted_agent(tmp_path, runtime, [
        reply(call('submit', {'law_id': 'chosen'}, ident='submit'))])
    assert result['status'] == 'submitted'
    assert len(runtime.calls) == len(client.requests) == 1
    assert not agent._symbolic_submission_reviewed
    assert events(tmp_path, 'symbolic_submission_review') == []


def test_plan_advice_does_not_consume_later_critical_submission_review(tmp_path):
    runtime = StrategyRuntime(probes=2, fit_status='not_converged')
    agent, _, result = scripted_agent(tmp_path, runtime, [
        reply(call('insert_probe', {'probes': [{}, {}]}, ident='insert')),
        reply(call('submit', {'law_id': 'chosen'}, ident='first_submit')),
        reply(call('submit', {'law_id': 'chosen'}, ident='second_submit'))])
    assert result['status'] == 'submitted'
    assert len(events(tmp_path, 'symbolic_experiment_review')) == 1
    assert agent._symbolic_plan_reviewed
    assert len(events(tmp_path, 'symbolic_submission_review')) == 1
    assert agent._symbolic_submission_reviewed
    assert [name for name, _ in runtime.calls] == ['insert_probe', 'submit']
