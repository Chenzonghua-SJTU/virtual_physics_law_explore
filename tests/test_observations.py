"""Tests of evidence provenance, aggregation and frozen scientific versions."""
import copy
import json

import numpy as np

from shore_agent.environment import Environment
from shore_agent.observations import estimate_static_bodies
from shore_agent.runtime import ToolRuntime


def test_estimation_weights_samples_and_matches_body_ids_not_array_order():
    first = {'observation_id': 'o1', 'times': [0, 1], 'body_ids': ['a', 'b'],
             'positions_obs': [[[0, 0], [10, 20]], [[0, 0], [10, 20]]]}
    second = {'observation_id': 'o2', 'times': [0], 'body_ids': ['b', 'a'],
              'positions_obs': [[[16, 29], [6, 9]]]}
    estimate = estimate_static_bodies([first, second, copy.deepcopy(first)], 0.3)
    assert estimate['observation_ids'] == ['o1', 'o2']
    assert estimate['sample_count_per_body'] == {'a': 3, 'b': 3}
    assert estimate['version'] == 'body_estimate_2'
    assert [b['position'] for b in estimate['bodies']] == [[2, 3], [12, 23]]
    np.testing.assert_allclose(estimate['bodies'][0]['position_standard_error'], 0.3 / np.sqrt(3))


def test_noisy_observations_are_the_only_positions_and_freeze_with_each_law(tmp_path):
    from evaluate import evaluate_run
    with Environment({'noise': True, 'seed': 123, 'physics_version': 'v3'}) as env:
        runtime = ToolRuntime(env, tmp_path)
        mission = runtime.mission()['data']
        assert 'visible_bodies' not in mission['task']
        assert 'body_observation' not in mission['first_light']
        assert 'body_position_estimate' not in mission
        assert runtime.known_bodies == [] and runtime.body_position_estimate is None
        archived_mission = json.loads((tmp_path / 'mission.json').read_text())
        assert archived_mission == {k: v for k, v in mission.items() if k != 'expression_syntax'}

        def execute(name, **args):
            response = runtime.execute(name, args)
            assert response['ok'], response
            return response['data']

        acquired = execute('observe_body', times=[i * .5 for i in range(8)])
        first = runtime.store.get('body_observation', acquired['observation_id'])
        initial_positions = np.mean(first['positions_obs'], axis=0)
        np.testing.assert_array_equal([b['position'] for b in runtime.known_bodies], initial_positions)
        # Private fixture truth is used only to detect accidental perfect-coordinate leakage.
        assert not np.array_equal(initial_positions, [[-2, 0], [2, 0], [0, 3]])
        assert first['body_position_estimate']['observation_ids'] == [first['observation_id']]

        def fit():
            # Engineering fixture, not an autonomous discovery or a model prompt.
            return execute('fit_law_and_rollout',
                           law_spec={'ax': 'k*sum_b(bx-x)', 'ay': 'k*sum_b(by-y)'},
                           parameter_spec=[{'name': 'k', 'initial': .1, 'lower': .01, 'upper': 1}],
                           train_probe_ids=list(runtime.store.records['probe'])[:2])

        law_id = fit()['law_id']
        frozen = runtime.store.get('law', law_id)
        assert frozen['known_bodies'] == runtime.known_bodies
        assert frozen['body_position_estimate'] == first['body_position_estimate']
        pid = execute('insert_probe', probes=[{'r0': [3, -2], 'v0': [.5, 1], 'properties': {}}],
                      t0=2, dt=.1, n_samples=15)['probes'][0]['probe_id']
        before = execute('validate_law', law_id=law_id, test_probe_ids=[pid])
        obs = execute('observe_body', times=[0, 1])
        combined = np.concatenate([first['positions_obs'], obs['positions_obs']], axis=0)
        np.testing.assert_array_equal([b['position'] for b in runtime.known_bodies], combined.mean(axis=0))
        estimate = obs['body_position_estimate']
        assert estimate['version'] == 'body_estimate_2'
        assert estimate['sample_count_per_body'] == {'b1': 10, 'b2': 10, 'b3': 10}
        np.testing.assert_allclose(estimate['bodies'][0]['position_standard_error'], .1 / np.sqrt(10))
        assert runtime.known_bodies != frozen['known_bodies']
        current = copy.deepcopy(runtime.body_position_estimate)
        # Re-reading cached first light never re-weights samples or resets the current estimate.
        assert runtime.mission()['data'] == mission
        execute('call_back', record_type='body_observation', record_ids=[first['observation_id']], detail='full')
        assert runtime.body_position_estimate == current
        assert runtime.budget()['observations_remaining'] == 18
        after = execute('validate_law', law_id=law_id, test_probe_ids=[pid])
        assert before['errors'] == after['errors']
        old_rollouts = runtime.store.get('validation', before['validation_id'])['rollouts']
        assert old_rollouts == runtime.store.get('validation', after['validation_id'])['rollouts']
        assert runtime.store.get('law', law_id) == frozen
        new_id = fit()['law_id']
        assert runtime.store.get('law', new_id)['body_position_estimate'] == current
        submitted = execute('submit', law_id=law_id,
                            claims={'dynamics_order': 2, 'hidden_matter': False, 'time_dependence': False},
                            physical_explanation='工程测试：仅验证带噪天体位置估计被冻结，不声称识别了真实机制。')
        assert submitted['status'] == 'accepted'
        exported = tmp_path / 'submissions' / submitted['submission_id'] / 'law.json'
        assert json.loads(exported.read_text()) == frozen

    # The existing same-world hidden-initial-state evaluation must also retain the
    # submitted observed positions; observing more bodies cannot improve an old law.
    import evaluate as evaluator
    original_rollout = evaluator.rollout
    used_positions = []
    def audited_rollout(spec, params, probe, bodies, *args, **kwargs):
        used_positions.append(copy.deepcopy(bodies))
        return original_rollout(spec, params, probe, bodies, *args, **kwargs)
    from unittest.mock import patch
    with patch.object(evaluator, 'rollout', audited_rollout):
        result = evaluate_run(tmp_path, n_probes=2)
    assert result['complete']
    assert len(used_positions) == 2 and all(b == frozen['known_bodies'] for b in used_positions)
