"""Mock request schemas reflect public budgets; execution remains authoritative."""
import copy
import json

import pytest

from shore_agent.agent import Agent
from shore_agent.store import append_event
from test_e5_length_recovery import Runtime, client_for, tool_message


class BudgetRuntime(Runtime):
    def __init__(self, directory, ruleset='e5'):
        super().__init__(ruleset)
        self.directory = directory
        self.energy = 2
        self.observations = 1
        self.results = []

    def budget(self):
        return {**super().budget(), 'observations_remaining': self.observations}

    def execute(self, name, args):
        self.executed.append((name, copy.deepcopy(args)))
        error = None
        if name == 'insert_probe':
            if len(args['probes']) > self.energy:
                error = {'code': 'energy_budget', 'message': 'Not enough energy for this batch'}
            else:
                self.energy -= len(args['probes'])
        if name == 'observe_body':
            if self.observations <= 0:
                error = {'code': 'observation_budget', 'message': 'No observations remaining'}
            else:
                self.observations -= 1
        data = ({'status': 'accepted', 'session_ended': True} if name == 'submit'
                else {'synthetic': True})
        result = {'ok': error is None, 'data': None if error else data,
                  'error': error, 'budget': self.budget()}
        self.results.append(copy.deepcopy(result))
        append_event(self.directory / 'tools.jsonl',
                     {'tool': name, 'arguments': args, 'result': result})
        return result


def invoke(tmp_path, runtime, responses, config=None):
    client, requests = client_for(tmp_path, runtime,
                                 [(response, 'tool_calls', 1, 20) for response in responses])
    try:
        result = Agent(client, runtime, tmp_path,
                       {'guidance_profile': 'e3', **(config or {})}).run()
    finally:
        client.close()
    return result, requests


def functions(request):
    return {schema['function']['name']: schema['function'] for schema in request['tools']}


def test_each_request_uses_latest_budget_but_runtime_executes_unadvertised_calls(tmp_path):
    runtime = BudgetRuntime(tmp_path)
    original = copy.deepcopy(runtime.schemas)
    probe_args = {'probes': [{'r0': [1, 0], 'v0': [0, 0]}], 't0': 0, 'dt': .1, 'n_samples': 2}
    probe = lambda call_id: tool_message('insert_probe', call_id, json.dumps(probe_args))
    observe = lambda call_id: tool_message('observe_body', call_id, '{"times":[0]}')
    result, requests = invoke(tmp_path, runtime, [
        probe('first'), observe('only-observation'), probe('last-energy'),
        probe('unadvertised-probe'), observe('unadvertised-observation'), tool_message(),
    ], {'budget_aware_tools': True})

    assert result['status'] == 'submitted'
    assert functions(requests[0])['insert_probe']['parameters']['properties']['probes']['maxItems'] == 2
    assert functions(requests[1])['insert_probe']['parameters']['properties']['probes']['maxItems'] == 1
    assert 'observe_body' in functions(requests[1])
    assert functions(requests[2])['insert_probe']['parameters']['properties']['probes']['maxItems'] == 1
    assert 'observe_body' not in functions(requests[2])
    for request in requests[3:]:
        advertised = functions(request)
        assert 'insert_probe' not in advertised and 'observe_body' not in advertised
        assert {'fit_law_and_rollout', 'validate_law', 'list_files', 'read_file',
                'analyze_residual', 'save_draft', 'submit'} <= set(advertised)
    assert runtime.schemas == original  # Original schemas still validate actual calls.
    assert [name for name, _ in runtime.executed] == ['insert_probe', 'observe_body', 'insert_probe',
                                                     'insert_probe', 'observe_body', 'submit']
    assert runtime.results[3]['error']['code'] == 'energy_budget'
    assert runtime.results[4]['error']['code'] == 'observation_budget'
    assert runtime.energy == runtime.observations == 0
    logged = [json.loads(line) for line in (tmp_path / 'tools.jsonl').read_text().splitlines()]
    saved = json.loads((tmp_path / 'messages.json').read_text())
    assert [row['result'] for row in logged] == runtime.results
    assert [json.loads(m['content']) for m in saved if m['role'] == 'tool'] == runtime.results
    assert len(requests) == result['model_usage']['calls'] == 6
    assert result['budget']['wall_seconds_remaining'] == 294
    assert all(request['max_tokens'] == 4096 for request in requests)


@pytest.mark.parametrize('ruleset,flag', [('e5', None), ('e5', False), ('e3', True), ('e4', True)])
def test_default_and_previous_rulesets_keep_all_original_tools(tmp_path, ruleset, flag):
    runtime = BudgetRuntime(tmp_path, ruleset)
    runtime.energy = runtime.observations = 0
    original = copy.deepcopy(runtime.schemas)
    config = {} if flag is None else {'budget_aware_tools': flag}
    result, requests = invoke(tmp_path, runtime, [tool_message()], config)
    assert result['status'] == 'submitted'
    assert requests[0]['tools'] == original == runtime.schemas
    assert functions(requests[0])['insert_probe']['parameters']['properties']['probes']['maxItems'] == 8
    assert 'observe_body' in functions(requests[0])


@pytest.mark.parametrize('energy,observations,expected_max,has_probe,has_observe', [
    (100, 20, 8, True, True), (1, 1, 1, True, True),
    (0.0, 0.0, None, False, False),
    (None, None, 8, True, True), (-1, -1, 8, True, True),
    (True, False, 8, True, True), (1.5, 1, 8, True, True),
])
def test_only_known_zero_and_positive_integer_budgets_change_advertised_limits(
        tmp_path, energy, observations, expected_max, has_probe, has_observe):
    runtime = BudgetRuntime(tmp_path)
    original = copy.deepcopy(runtime.schemas)
    agent = Agent(None, runtime, tmp_path, {'budget_aware_tools': True})
    offered = agent._model_tools({'energy_remaining': energy, 'observations_remaining': observations})
    advertised = functions({'tools': offered})
    assert ('insert_probe' in advertised) == has_probe
    assert ('observe_body' in advertised) == has_observe
    if has_probe:
        assert advertised['insert_probe']['parameters']['properties']['probes']['maxItems'] == expected_max
    offered[-1]['function']['description'] = 'mutated request copy'
    assert runtime.schemas == original


@pytest.mark.parametrize('flag', [None, 0, 1, 'true'])
def test_budget_aware_flag_requires_boolean(tmp_path, flag):
    with pytest.raises(ValueError, match='budget_aware_tools must be boolean'):
        Agent(None, Runtime(), tmp_path, {'budget_aware_tools': flag})
