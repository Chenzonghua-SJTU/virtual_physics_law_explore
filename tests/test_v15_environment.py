"""Adapter checks only: these are not autonomous-discovery results."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from shore_agent.environment import Environment
from shore_v15.simulator import Simulator
from shore_v15.source import DevelopmentSimulator, catalog, source_inputs


@pytest.mark.parametrize('number', range(1, 7))
def test_v15_first_light_matches_public_simulator_and_is_cached(number):
    sim = Simulator({'world_id': f'world_{number}'})
    mission = sim.request('mission')
    assert mission['ok']
    task = mission['data']['task']
    assert task['world_set'] == 'v15'
    assert task['physics_version'] == 'shore_v15'
    assert task['body_observation_protocol'] == 'time_series'
    assert task['limits']['initial_energy'] == 100
    assert task['limits']['wall_seconds'] == 3600
    direct = DevelopmentSimulator(str(number))
    first = catalog.first_light(str(number))
    truth = direct.launch(**first)
    light = mission['data']['first_light']
    for index, probe in enumerate(light['probes']):
        np.testing.assert_array_equal(probe['times'], truth['times'])
        np.testing.assert_array_equal(probe['r_obs'], truth['positions'][:, index])
        np.testing.assert_array_equal(probe['v_obs'], truth['velocities'][:, index])
        assert probe['a_est_method'] == 'velocity_nonuniform_centered_difference'
    background = direct.background(truth['times'])
    np.testing.assert_array_equal(light['body_observation']['positions_obs'], background['positions'])
    assert light['body_observation']['body_ids'] == background['ids']
    again = sim.request('mission')
    assert again['data'] == mission['data']
    assert again['budget']['energy_remaining'] == 100
    assert again['budget']['observations_remaining'] == 20


@pytest.mark.parametrize('number', range(1, 7))
def test_v15_ipc_launch_preserves_absolute_time_and_property_controls(number):
    props = {'mass': 1.3, 'charge': .7} if number in (1, 2, 4) else {'mass': 2.5}
    probe = {'r0': [2., .5], 'v0': [-.1, .3], 'properties': props}
    with Environment({'world_set': 'v15', 'world_id': f'world_{number}'}) as env:
        assert env.request('mission')['ok']
        result = env.request('insert_probe', probes=[probe], t0=4., dt=.25, n_samples=8)
        assert result['ok'], result
        record = result['data']['probes'][0]
        source, properties = source_inputs(str(number), props)
        truth = DevelopmentSimulator(str(number)).launch(
            [{'pos': probe['r0'], 'vel': probe['v0'], 'properties': properties}],
            4., np.arange(8)*.25, source)
        np.testing.assert_array_equal(record['times'], truth['times'])
        np.testing.assert_array_equal(record['r_obs'], truth['positions'][:, 0])
        np.testing.assert_array_equal(record['v_obs'], truth['velocities'][:, 0])
        assert record['initial_conditions']['properties'] == props
        assert result['budget']['energy_remaining'] == 99
        observed = env.request('observe_body', times=[0., 4., 5.])
        assert observed['ok'], observed
        assert observed['budget']['observations_remaining'] == 19


@pytest.mark.parametrize('number', range(1, 7))
def test_v15_noise_uses_world_scales_both_readouts_and_deterministic_cache(number):
    config = {'world_id': f'world_{number}', 'noise': True, 'seed': 123}
    a, b = Simulator(config), Simulator(config)
    ma, mb = a.request('mission'), b.request('mission')
    assert ma['data'] == mb['data']
    assert a.request('mission')['data'] == ma['data']
    clean = Simulator({'world_id': f'world_{number}'}).request('mission')['data']
    assert ma['data']['task']['position_noise_sigma'] == catalog.noise_sigma(str(number))
    assert ma['data']['task']['velocity_noise_sigma'] == 1e-4 * catalog.config(str(number))['initial_speed_max']
    assert ma['data']['task']['body_initial_states'] == clean['task']['body_initial_states']
    for noisy, exact in zip(ma['data']['first_light']['probes'], clean['first_light']['probes']):
        assert noisy['initial_conditions'] == exact['initial_conditions']
        assert noisy['r_obs'] != exact['r_obs']
        assert noisy['v_obs'] != exact['v_obs']
    first = a.request('observe_body', times=[.5, 1.])
    second = a.request('observe_body', times=[.5, 1.])
    assert first['data']['positions_obs'] != second['data']['positions_obs']


@pytest.mark.parametrize('changes,code', [
    ({'probes': [{'r0': [0., 0.], 'v0': [0., 0.], 'properties': {}}]}, 'initial_conditions'),
    ({'probes': [{'r0': [5., 5.], 'v0': [0., 0.], 'properties': {}}]}, 'initial_conditions'),
    ({'probes': [{'r0': [2., 0.], 'v0': [3., 3.], 'properties': {}}]}, 'initial_conditions'),
    ({'probes': [{'r0': [2., 0.], 'v0': [0., 0.], 'properties': {'mass': .1}}]}, 'probe_properties'),
    ({'probes': [{'r0': [2., 0.], 'v0': [0., 0.], 'properties': {'charge': 1.}}]}, 'probe_properties'),
    ({'dt': 1., 'n_samples': 26}, 'trajectory_duration'),
    ({'dt': .003}, 'time_grid'),
    ({'t0': 31., 'dt': 1., 'n_samples': 3}, 'time_range'),
])
def test_v15_invalid_requests_do_not_spend_energy(changes, code):
    sim = Simulator({'world_id': 'world_3'})
    sim.request('mission')
    request = dict(probes=[{'r0': [2., 0.], 'v0': [0., 0.], 'properties': {}}],
                   t0=0., dt=.2, n_samples=8)
    request.update(changes)
    result = sim.request('insert_probe', **request)
    assert not result['ok']
    assert result['error']['code'] == code
    assert result['budget']['energy_remaining'] == 100


def test_v15_defaults_are_explicit_and_per_probe_source_controls_remain_separate():
    sim = Simulator({'world_id': 'world_2'})
    sim.request('mission')
    result = sim.request('insert_probe', probes=[
        {'r0': [2., 0.], 'v0': [0., .3], 'properties': {}},
        {'r0': [2., 0.], 'v0': [0., .3], 'properties': {'charge': 2.}},
    ], t0=0., dt=.5, n_samples=8)
    assert result['ok']
    a, b = result['data']['probes']
    assert a['initial_conditions']['properties'] == {'mass': 1., 'charge': 1.}
    assert b['initial_conditions']['properties'] == {'mass': 1., 'charge': 2.}
    assert a['r_obs'] != b['r_obs']
    assert result['budget']['energy_remaining'] == 98


def test_v15_vendor_snapshot_hashes_are_unchanged():
    vendor = Path(__file__).resolve().parents[1] / 'shore_v15' / 'vendor'
    manifest = json.loads((vendor / 'SOURCE.json').read_text())
    for relative, digest in manifest['files'].items():
        assert hashlib.sha256((vendor / relative).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize('number', range(1, 7))
def test_e5_first_light_matches_clean_e3_data_with_ten_energy_and_300_seconds(number):
    config = {'world_id': f'world_{number}', 'seed': 42}
    clean = Simulator(config).request('mission')
    sim = Simulator(dict(config, ruleset='e5', noise=True))
    mission = sim.request('mission')
    assert mission['ok']
    assert mission['data']['first_light'] == clean['data']['first_light']
    task = mission['data']['task']
    assert task['position_noise_sigma'] == task['velocity_noise_sigma'] == 0
    assert task['limits']['initial_energy'] == 10
    assert task['limits']['wall_seconds'] == 300
    assert mission['budget']['energy_remaining'] == 10
    assert sim.config['noise'] is False


def test_e4_ten_energy_noisy_cached_first_light_and_atomic_probe_budget():
    sim = Simulator({'world_id': 'world_1', 'ruleset': 'e4', 'noise': False})
    mission = sim.request('mission')
    assert mission['budget']['energy_remaining'] == 10
    assert mission['data']['task']['limits']['wall_seconds'] == 300
    assert mission['data']['task']['limits']['initial_energy'] == 10
    assert mission['data']['task']['velocity_noise_sigma'] > 0
    assert mission['data'] == sim.request('mission')['data']
    probe = {'r0': [2., 0.], 'v0': [0., 0.], 'properties': {}}
    request = dict(t0=0., dt=.1, n_samples=3)
    assert sim.request('insert_probe', probes=[probe] * 8, **request)['budget']['energy_remaining'] == 2
    rejected = sim.request('insert_probe', probes=[probe] * 3, **request)
    assert not rejected['ok'] and rejected['budget']['energy_remaining'] == 2
    assert sim.request('insert_probe', probes=[probe] * 2, **request)['budget']['energy_remaining'] == 0
    assert not sim.request('insert_probe', probes=[probe], **request)['ok']


@pytest.mark.parametrize('override', [{'energy_budget': 100}, {'wall_seconds': 301}])
def test_e4_direct_simulator_rejects_budget_expansion(override):
    with pytest.raises(ValueError):
        Simulator({'ruleset': 'e4', **override})


@pytest.mark.parametrize('config', [{'world_id': 'world_7'}, {'physics_version': 'v4'},
                                     {'world_set': 'legacy'}, {'noise': 1}, {'seed': -1}])
def test_v15_rejects_wrong_worlds_versions_and_config(config):
    with pytest.raises(ValueError):
        Simulator(config)


def test_legacy_ipc_is_still_the_default_and_accepts_explicit_world_set():
    with Environment({}) as a, Environment({'world_set': 'legacy'}) as b:
        assert a.request('mission')['data'] == b.request('mission')['data']
    with pytest.raises(ValueError, match='disagree'):
        Environment({'world_set': 'legacy', 'physics_version': 'shore_v15'})


def test_v15_ipc_ignores_legacy_template_domain_overrides():
    with Environment({'world_set': 'v15', 'world_id': 'world_4',
                      'reference_length': 10., 'position_limit': 5.,
                      'velocity_limit': 3., 'time_max': 30.}) as env:
        response = env.request('mission')
        assert response['ok'], response
        task = response['data']['task']
        assert task['position_limit'] == 10.
        assert task['velocity_limit'] == 5.
        assert task['physical_time_range'] == [0, 40.]


@pytest.mark.parametrize('world_id', [f'world_{i}' for i in range(1, 7)])
def test_direct_legacy_simulator_rejects_v15_physics_label(world_id):
    from shore_sim.simulator import Simulator as LegacySimulator
    with pytest.raises(ValueError, match='Legacy simulator requires a legacy physics version'):
        LegacySimulator({'world_id': world_id, 'physics_version': 'shore_v15'})
