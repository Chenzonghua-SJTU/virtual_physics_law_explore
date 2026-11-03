"""Engineering checks of time-resolved observation inputs, not Agent discoveries."""
import copy
import json

import numpy as np
import pytest

from evaluate import evaluate_run
from shore_agent.environment import Environment
from shore_agent.observations import estimate_body_trajectories
from shore_agent.runtime import ToolRuntime


def call(runtime, name, **arguments):
    reply = runtime.execute(name, arguments)
    assert reply['ok'], reply
    return reply['data']


def test_trajectory_estimate_aligns_ids_and_epochs_and_honors_known_initial_state():
    first = {'observation_id': 'o1', 'times': [0, 1], 'body_ids': ['a', 'b'],
             'positions_obs': [[[9, 9], [99, 99]], [[1, 2], [11, 22]]]}
    second = {'observation_id': 'o2', 'times': [1, 3], 'body_ids': ['b', 'a'],
              'positions_obs': [[[13, 24], [3, 4]], [[15, 26], [5, 6]]]}
    initial = [{'body_id': 'a', 'position': [0, 0]}, {'body_id': 'b', 'position': [10, 20]}]
    context = estimate_body_trajectories([first, second, copy.deepcopy(first)], initial, .1)
    assert context['observation_ids'] == ['o1', 'o2']
    assert context['times'] == [0, 1, 3]
    assert context['positions'] == [[[0, 0], [10, 20]], [[2, 3], [12, 23]], [[5, 6], [15, 26]]]
    assert context['sample_counts'] == [[0, 0], [2, 2], [1, 1]]
    assert context['bodies'][0]['position'] == [5, 6]
    assert context['bodies'][0]['position_time'] == 3


def test_moving_sources_observation_extension_validates_frozen_force_without_rewriting_law(tmp_path):
    config = {'world_id': 'world_6', 'physics_version': 'v4', 'noise': False, 'seed': 43}
    (tmp_path/'config.json').write_text(json.dumps({'environment': config}))
    with Environment(config) as env:
        rt = ToolRuntime(env, tmp_path)
        mission = rt.mission()['data']
        assert set(mission['first_light']) == {'body_observation', 'probes'}
        assert len(mission['first_light']['body_observation']['times']) == 8
        assert len(rt.store.records['body_observation']) == 1
        assert rt.budget()['observations_remaining'] == 20
        assert rt.budget()['energy_remaining'] == 100
        original = copy.deepcopy(rt.store.records)
        assert rt.mission()['data'] == mission
        assert rt.store.records == original
        assert rt.body_position_estimate['positions'][0] != rt.body_position_estimate['positions'][-1]
        law = call(rt, 'fit_law_and_rollout',
                   law_spec={'ax': 'k*sum_b(bx-x)', 'ay': 'k*sum_b(by-y)'},
                   parameter_spec=[{'name': 'k', 'initial': .08, 'lower': .01, 'upper': .5}],
                   train_probe_ids=list(rt.store.records['probe']))
        law_id = law['law_id']
        frozen = rt.store.get('law', law_id)
        assert frozen['fitted_parameters']['k'] == pytest.approx(.1, abs=1e-7)
        fresh = call(rt, 'insert_probe', probes=[{'r0': [3, -2], 'v0': [.6, -.3], 'properties': {}}],
                     t0=12, dt=.1, n_samples=30)['probes'][0]['probe_id']
        missing = rt.execute('validate_law', {'law_id': law_id, 'test_probe_ids': [fresh]})
        assert not missing['ok'] and missing['error']['code'] == 'body_time_coverage'
        assert not rt.store.records['validation']
        call(rt, 'observe_body', times=[10, 15, 30])
        validation = call(rt, 'validate_law', law_id=law_id, test_probe_ids=[fresh])
        full = rt.store.get('validation', validation['validation_id'])
        assert full['errors']['overall']['position_rmse'] < 1e-6
        assert full['body_context']['time_range'] == [0, 30]
        assert len(full['body_context']['observation_ids']) == 2
        assert frozen['body_context']['time_range'] == [0, 3.5]
        assert rt.store.get('law', law_id) == frozen
        call(rt, 'observe_body', times=[20, 25])
        assert rt.store.get('validation', full['validation_id']) == full
        assert rt.store.get('law', law_id) == frozen
        residual = call(rt, 'analyze_residual', law_id=law_id, probe_ids=[fresh])
        assert len(rt.store.get('residual', residual['residual_id'])['body_context']['observation_ids']) == 3
        submitted = call(rt, 'submit', law_id=law_id,
                         claims={'dynamics_order': 2, 'hidden_matter': False, 'time_dependence': False},
                         physical_explanation='工程检查：固定瞬时源位置后没有显式时间项，移动源状态是外部输入。')
        assert submitted['status'] == 'accepted'
    evaluated = evaluate_run(tmp_path, n_probes=3)
    assert evaluated['complete'] and evaluated['overall']['position_rmse'] < 1e-5


def test_time_modulation_fit_and_new_absolute_launch_time(tmp_path):
    config = {'world_id': 'world_7', 'physics_version': 'v4', 'noise': False, 'seed': 43}
    (tmp_path/'config.json').write_text(json.dumps({'environment': config}))
    with Environment(config) as env:
        rt = ToolRuntime(env, tmp_path)
        rt.mission()
        call(rt, 'observe_body', times=[0, 5, 10, 15, 20, 25, 30])
        training = list(rt.store.records['probe'])
        training += [p['probe_id'] for p in call(rt, 'insert_probe',
                     probes=[{'r0': [2, -1], 'v0': [.5, .2], 'properties': {}}],
                     t0=8, dt=.2, n_samples=35)['probes']]
        fitted = call(rt, 'fit_law_and_rollout',
                      law_spec={'ax': '(k+c*sin(w*t))*sum_b(bx-x)',
                                'ay': '(k+c*sin(w*t))*sum_b(by-y)'},
                      parameter_spec=[{'name': 'k', 'initial': .09, 'lower': .01, 'upper': .3},
                                      {'name': 'c', 'initial': .04, 'lower': -.1, 'upper': .1},
                                      {'name': 'w', 'initial': .55, 'lower': .1, 'upper': 1.}],
                      train_probe_ids=training)
        law_id = fitted['law_id']
        assert fitted['fitted_parameters'] == pytest.approx({'k': .1, 'c': .05, 'w': .6}, rel=1e-5)
        fresh = [p['probe_id'] for p in call(rt, 'insert_probe',
                 probes=[{'r0': [-2, 3], 'v0': [.3, -.4], 'properties': {}}],
                 t0=21, dt=.2, n_samples=40)['probes']]
        result = call(rt, 'validate_law', law_id=law_id, test_probe_ids=fresh)
        assert result['errors']['overall']['position_rmse'] < 1e-5
        submission = call(rt, 'submit', law_id=law_id,
                          claims={'dynamics_order': 2, 'hidden_matter': False, 'time_dependence': True},
                          physical_explanation='工程检查：源位置固定，系数依赖共同原点定义的绝对时间，属于显式时间依赖。')
        assert submission['status'] == 'accepted'
    evaluated = evaluate_run(tmp_path, n_probes=3)
    assert evaluated['complete'] and evaluated['overall']['position_rmse'] < 1e-5
