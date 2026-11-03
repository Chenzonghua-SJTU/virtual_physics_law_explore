"""Private checks for absolute-time source motion and force modulation.

The explicit mechanisms here are developer fixtures, never Agent inputs.
"""
import copy
import json
import math

import numpy as np
import pytest

from shore_sim import worlds
from shore_sim.simulator import Simulator


INITIAL_BODIES = np.array([[-2., 0.], [2., 0.], [0., 3.]])
DRIFT = np.array([.08, -.04])
TIME_WORLDS = ('world_6', 'world_7')


def moving_center_reference(r0, v0, times, t0):
    """Independent analytic solution in the uniformly translating frame."""
    times = np.asarray(times, dtype=float)
    frequency = math.sqrt(.3)
    phase = frequency * (times - t0)
    center0 = np.array([0., 1.]) + DRIFT * t0
    offset = np.asarray(r0) - center0
    relative_velocity = np.asarray(v0) - DRIFT
    centers = np.array([0., 1.]) + times[:, None] * DRIFT
    position = (centers + np.cos(phase)[:, None] * offset
                + np.sin(phase)[:, None] * relative_velocity / frequency)
    velocity = (DRIFT - frequency * np.sin(phase)[:, None] * offset
                + np.cos(phase)[:, None] * relative_velocity)
    return np.column_stack((position, velocity))


def launch(simulator, t0=4., n_samples=15):
    response = simulator.request('insert_probe',
                                 probes=[{'r0': [1.2, -.7], 'v0': [.3, -.4], 'properties': {}}],
                                 t0=t0, dt=.1, n_samples=n_samples)
    assert response['ok'], response
    return response['data']['probes'][0]


@pytest.mark.parametrize('world_id', TIME_WORLDS)
def test_body_position_helper_shapes_absolute_times_and_copy_ownership(world_id):
    expected_velocity = DRIFT if world_id == 'world_6' else np.zeros(2)
    at_ten = worlds.body_positions_at(10., world_id=world_id, physics_version='v4')
    np.testing.assert_allclose(at_ten, INITIAL_BODIES + 10 * expected_velocity, atol=1e-15)
    series = worlds.body_positions_at(np.array([0., 2., 10.]), world_id=world_id,
                                     physics_version='v4')
    assert series.shape == (3, 3, 2)
    np.testing.assert_allclose(series, INITIAL_BODIES[None, :, :]
                               + np.array([0., 2., 10.])[:, None, None] * expected_velocity,
                               atol=1e-15)
    at_ten[:] = 999
    series[:] = -999
    np.testing.assert_array_equal(worlds.body_positions_at(0., world_id=world_id,
                                                          physics_version='v4'), INITIAL_BODIES)


def test_world6_force_follows_sources_in_absolute_time():
    state = np.array([1.2, -.7, .3, -.4])
    initial = .1 * np.sum(INITIAL_BODIES - state[:2], axis=0)
    for time in [0., 2.5, 12., 30.]:
        actual = worlds.acceleration('world_6', time, state, physics_version='v4')
        np.testing.assert_allclose(actual, initial + .3 * DRIFT * time, atol=1e-14)
        translated = np.r_[state[:2] + DRIFT * time, state[2:] + DRIFT]
        np.testing.assert_allclose(worlds.acceleration('world_6', time, translated,
                                                      physics_version='v4'), initial, atol=1e-14)


def test_world7_force_modulates_even_though_source_positions_are_fixed():
    state = [1., -2., .5, -.4]
    baseline = np.array([-.3, .9])
    quarter_period = math.pi / 1.2
    for time, multiplier in [(0., 1.), (quarter_period, 1.5),
                             (3 * quarter_period, .5), (4 * quarter_period, 1.)]:
        np.testing.assert_allclose(worlds.acceleration('world_7', time, state,
                                                      physics_version='v4'),
                                   baseline * multiplier, rtol=0, atol=1e-14)
        np.testing.assert_array_equal(worlds.body_positions_at(time, world_id='world_7',
                                                              physics_version='v4'), INITIAL_BODIES)


@pytest.mark.parametrize('noise', [False, True])
@pytest.mark.parametrize('world_id', TIME_WORLDS)
def test_mission_declares_exact_initial_states_and_caches_free_time_series(world_id, noise):
    simulator = Simulator({'world_id': world_id, 'physics_version': 'v4', 'noise': noise, 'seed': 43})
    mission = simulator.request('mission')
    assert mission['ok']
    task, light = mission['data']['task'], mission['data']['first_light']
    assert task['physics_version'] == 'v4'
    assert task['body_observation_protocol'] == 'time_series'
    assert 'static_visible_bodies' not in task
    expected_velocity = DRIFT.tolist() if world_id == 'world_6' else [0., 0.]
    assert task['body_initial_states'] == [
        {'body_id': name, 'position': position.tolist(), 'velocity': expected_velocity}
        for name, position in zip(task['body_ids'], INITIAL_BODIES)]
    bodies = light['body_observation']
    assert len(bodies['times']) == 8 and bodies['times'][0] == 0
    assert np.shape(bodies['positions_obs']) == (8, 3, 2)
    assert len(light['probes']) == 2
    assert all(probe['times'] == bodies['times'] for probe in light['probes'])
    assert mission['budget']['energy_remaining'] == 100
    assert mission['budget']['observations_remaining'] == 20
    saved = copy.deepcopy(mission['data'])
    assert simulator.request('mission')['data'] == saved
    mission['data']['task']['body_initial_states'][0]['position'][0] = 999
    mission['data']['first_light']['body_observation']['positions_obs'][0][0][0] = 999
    assert simulator.request('mission')['data'] == saved
    if not noise:
        expected = INITIAL_BODIES[None, :, :] + np.asarray(bodies['times'])[:, None, None] * expected_velocity
        np.testing.assert_allclose(saved['first_light']['body_observation']['positions_obs'], expected,
                                   atol=1e-15)


def test_time_world_missions_do_not_declare_hidden_force_or_motion_laws():
    tasks = []
    for world_id in TIME_WORLDS:
        task = copy.deepcopy(Simulator({'world_id': world_id, 'physics_version': 'v4'})
                             .request('mission')['data']['task'])
        task.pop('world_id')
        task.pop('world_name')
        # Initial states are observed data; their future evolution is not supplied.
        for state in task['body_initial_states']:
            state.pop('velocity')
        tasks.append(task)
        serialized = json.dumps(task).lower()
        for hidden in ['truth_reference', 'acceleration', 'stiffness', 'modulation',
                       'sin(', 'radau', 'harmonic', 'uniformly translating']:
            assert hidden not in serialized
    assert tasks[0] == tasks[1]


@pytest.mark.parametrize('world_id', TIME_WORLDS)
def test_future_observation_does_not_advance_physics_and_launch_replays_at_nonzero_t0(
        monkeypatch, world_id):
    clock = [1000.]
    monkeypatch.setattr('shore_sim.simulator.time.monotonic', lambda: clock[0])
    simulator = Simulator({'world_id': world_id, 'physics_version': 'v4', 'noise': False})
    simulator.request('mission')
    original = launch(simulator)
    observed = simulator.request('observe_body', times=[20., 25., 30.])
    assert observed['ok']
    velocity = DRIFT if world_id == 'world_6' else np.zeros(2)
    np.testing.assert_allclose(observed['data']['positions_obs'],
                               INITIAL_BODIES[None, :, :] + np.array([20., 25., 30.])[:, None, None] * velocity,
                               atol=1e-15)
    clock[0] += 17
    replay = launch(simulator)
    assert replay['probe_id'] != original['probe_id']
    for field in ['times', 'initial_conditions', 'r_obs', 'v_obs', 'a_est']:
        assert replay[field] == original[field]
    assert simulator.budget()['wall_seconds_remaining'] == 3583
    assert simulator.budget()['energy_remaining'] == 98
    assert simulator.budget()['observations_remaining'] == 19
    # Resetting the launch time changes these explicitly time-dependent worlds.
    at_zero = launch(simulator, t0=0.)
    assert np.max(np.abs(np.asarray(at_zero['r_obs']) - original['r_obs'])) > 1e-3
    replay_observation = simulator.request('observe_body', times=[20., 25., 30.])
    assert replay_observation['data']['positions_obs'] == observed['data']['positions_obs']


@pytest.mark.parametrize('start', [0., 4., 17.])
def test_world6_observations_and_truth_match_independent_moving_frame_solution(start):
    simulator = Simulator({'world_id': 'world_6', 'physics_version': 'v4', 'noise': False})
    simulator.request('mission')
    record = launch(simulator, t0=start)
    initial = record['initial_conditions']
    expected = moving_center_reference(initial['r0'], initial['v0'], record['times'], start)
    observed = np.column_stack((record['r_obs'], record['v_obs']))
    np.testing.assert_allclose(observed, expected, atol=2e-9, rtol=2e-9)
    # Oracle may be asked for times strictly later than its initial state time.
    oracle = worlds.truth_trajectory(initial['r0'], initial['v0'], record['times'][2:], t0=start,
                                     world_id='world_6', physics_version='v4')
    np.testing.assert_allclose(oracle, expected[2:], atol=2e-10, rtol=2e-10)


@pytest.mark.parametrize('world_id', TIME_WORLDS)
def test_independent_time_oracles_never_call_simulator_rhs_or_body_helper(monkeypatch, world_id):
    simulator = Simulator({'world_id': world_id, 'physics_version': 'v4', 'noise': False})
    simulator.request('mission')
    record = launch(simulator, t0=7.)
    observed = np.column_stack((record['r_obs'], record['v_obs']))

    def forbidden(*_args, **_kwargs):
        pytest.fail('Independent truth reused simulator force/source path')

    for name in ['acceleration', 'make_dynamics', 'body_positions_at']:
        monkeypatch.setattr(worlds, name, forbidden)
    initial = record['initial_conditions']
    oracle = worlds.truth_trajectory(initial['r0'], initial['v0'], record['times'], t0=7.,
                                     world_id=world_id, physics_version='v4')
    np.testing.assert_allclose(oracle, observed, atol=2e-8, rtol=2e-8)
    single = worlds.truth_trajectory(initial['r0'], initial['v0'], [7.], t0=7.,
                                     world_id=world_id, physics_version='v4')
    np.testing.assert_array_equal(single, [initial['r0'] + initial['v0']])


@pytest.mark.parametrize('world_id', TIME_WORLDS)
@pytest.mark.parametrize('version', ['v1', 'v2', 'v3'])
def test_new_worlds_cannot_run_or_be_evaluated_under_historical_versions(world_id, version):
    with pytest.raises(ValueError):
        Simulator({'world_id': world_id, 'physics_version': version})
    with pytest.raises(ValueError):
        worlds.truth_trajectory([1., 0.], [0., 1.], [0., .1],
                                world_id=world_id, physics_version=version)
    with pytest.raises(ValueError):
        worlds.truth_reference(world_id, physics_version=version)


@pytest.mark.parametrize('world_id', ['world_1', 'world_2', 'world_3', 'world_4', 'world_5'])
def test_v4_preserves_all_existing_world_force_laws_and_trajectories(world_id):
    state = [1.2, -.7, .3, -.4]
    for time in [0., 7., 30.]:
        np.testing.assert_array_equal(worlds.acceleration(world_id, time, state, physics_version='v4'),
                                      worlds.acceleration(world_id, time, state, physics_version='v3'))
    versions = [worlds.truth_trajectory(state[:2], state[2:], [7., 7.1, 7.3], t0=7.,
                                       world_id=world_id, physics_version=version)
                for version in ['v3', 'v4']]
    np.testing.assert_allclose(*versions, atol=2e-12, rtol=2e-12)


@pytest.mark.parametrize('world_id', TIME_WORLDS)
def test_source_motion_and_dynamics_stay_pinned_after_config_mutation(world_id):
    config = {'world_id': world_id, 'physics_version': 'v4', 'noise': False}
    simulator = Simulator(config)
    mission = simulator.request('mission')['data']
    before = launch(simulator)
    bodies_before = simulator.request('observe_body', times=[10., 20.])['data']['positions_obs']
    config.update(world_id='world_1', physics_version='v1')
    simulator.config.update(world_id='world_1', physics_version='v1')
    after = launch(simulator)
    bodies_after = simulator.request('observe_body', times=[10., 20.])['data']['positions_obs']
    assert before['r_obs'] == after['r_obs'] and before['v_obs'] == after['v_obs']
    assert bodies_before == bodies_after
    assert simulator.request('mission')['data'] == mission
