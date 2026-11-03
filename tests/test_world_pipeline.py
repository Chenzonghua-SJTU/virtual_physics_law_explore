"""Developer-chosen structures check expressiveness, never autonomous discovery.

These private fixtures are not imported by runtime code or sent to a model.
"""
import copy

import pytest

from shore_agent.environment import Environment
from shore_agent.runtime import ToolRuntime
from shore_worlds import CURRENT_PHYSICS_VERSION


DENOMINATOR = '((bx-x)**2+(by-y)**2+s)'
CASES = [
    ('world_1', {'ax': '-k*x', 'ay': '-k*(y-c)'},
     [('k', .27, .01, 1), ('c', .9, -2, 2)]),
    ('world_2', {'ax': '-kx*x-b*(y-c)', 'ay': '-b*x-ky*(y-c)'},
     [('kx', .32, .1, 1), ('b', .06, -.2, .2), ('ky', .22, .1, 1), ('c', .9, -2, 2)]),
    ('world_3', {'ax': 'sum_b((k+g*((bx-x)**2+(by-y)**2))*(bx-x))',
                 'ay': 'sum_b((k+g*((bx-x)**2+(by-y)**2))*(by-y))'},
     [('k', .05, .01, 1), ('g', .003, .0001, .1)]),
    ('world_4', {'ax': f'g*sum_b((bx-x)/sqrt({DENOMINATOR})**3)',
                 'ay': f'g*sum_b((by-y)/sqrt({DENOMINATOR})**3)'},
     [('g', .7, .1, 2), ('s', .7, .1, 2)]),
    ('world_5', {'ax': f'sum_b(k*(bx-x)+g*vy/{DENOMINATOR})',
                 'ay': f'sum_b(k*(by-y)-g*vx/{DENOMINATOR})'},
     [('k', .09, .01, 1), ('g', .9, .1, 3), ('s', .8, .5, 10)]),
]


PIPELINE_CASES = [(None, *case) for case in CASES] + [
    ('v2', CASES[-1][0], CASES[-1][1],
     [('k', .09, .01, 1), ('g', 1., .1, 3), ('s', 3.5, .5, 10)]),
    ('v3', *CASES[-1]),
]


@pytest.mark.parametrize('physics_version,world_id,law_spec,parameters', PIPELINE_CASES)
def test_existing_tools_can_fit_and_validate_each_world(
        tmp_path, physics_version, world_id, law_spec, parameters):
    configuration = {'world_id': world_id, 'noise': False, 'seed': 42}
    if physics_version is not None:
        configuration['physics_version'] = physics_version
    effective_version = physics_version or CURRENT_PHYSICS_VERSION
    with Environment(configuration) as environment:
        runtime = ToolRuntime(environment, tmp_path)
        mission = runtime.mission()
        assert mission['ok']
        assert mission['data']['task']['physics_version'] == effective_version
        modern = effective_version == 'v4'
        assert set(mission['data']['first_light']) == ({'probes', 'body_observation'} if modern else {'probes'})
        assert bool(runtime.known_bodies) == modern
        # The acquisition change must not alter the original probe data/RNG.
        backend = environment.request('mission')['data']
        assert mission['data']['first_light']['probes'] == backend['first_light']['probes']
        fit_args = {
            'law_spec': law_spec,
            'parameter_spec': [{'name': n, 'initial': v, 'lower': lo, 'upper': hi}
                               for n, v, lo, hi in parameters],
            'train_probe_ids': list(runtime.store.records['probe']),
        }
        uses_bodies = any('sum_b' in source for source in law_spec.values())
        if uses_bodies and not modern:
            blocked = runtime.execute('fit_law_and_rollout', fit_args)
            assert not blocked['ok'] and 'observe_body' in blocked['error']['message']
            assert not runtime.store.records['law']
            observed = runtime.execute('observe_body', {'times': [0]})
            assert observed['ok']
            assert runtime.budget()['observations_remaining'] == 19
        fitted = runtime.execute('fit_law_and_rollout', fit_args)
        assert fitted['ok'], fitted
        law_id = fitted['data']['law_id']
        frozen = copy.deepcopy(runtime.store.get('law', law_id))
        if world_id == 'world_5':
            expected = {'k': .1, 'g': 1.2, 's': 4} if effective_version == 'v2' else {
                'k': .1, 'g': 1, 's': 1}
            assert frozen['fitted_parameters'] == pytest.approx(expected, rel=1e-4, abs=1e-6)
        if not uses_bodies and not modern:
            assert frozen['known_bodies'] == [] and frozen['body_position_estimate'] is None
            assert runtime.execute('observe_body', {'times': [0]})['ok']
            assert runtime.known_bodies
        experiment = runtime.execute('insert_probe', {
            'probes': [{'r0': r, 'v0': v, 'properties': {}}
                       for r, v in [([4, -2], [-.8, 1]), ([-4, 3], [1, -.5])]],
            't0': 2, 'dt': .05, 'n_samples': 20,
        })
        assert experiment['ok'], experiment
        validation = runtime.execute('validate_law', {
            'law_id': law_id,
            'test_probe_ids': [p['probe_id'] for p in experiment['data']['probes']],
        })
        assert validation['ok'], validation
        assert validation['data']['errors']['overall']['position_rmse'] < 1e-4
        assert runtime.store.get('law', law_id) == frozen
        assert runtime.budget()['energy_remaining'] == 98
