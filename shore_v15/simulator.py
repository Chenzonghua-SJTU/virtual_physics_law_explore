"""v15 physics through the unchanged local Agent observation protocol.

The scientific Agent, tool schemas and fitting/integration tools are unchanged.
The true field, background, first-light request and clean trajectory integrator
come from the vendored public simulator. E3 retains 100 energy/3600 seconds;
E4/E5 use 10 energy/300 seconds; E5 disables observation noise. This is not the standard contest Console.
"""
import math

import numpy as np
from shore_rules import rules_for

from shore_sim.simulator import Simulator as LocalProtocol, InvalidRequest
from shore_worlds import V15_PHYSICS_VERSION, validate_world_id, world_name
from .source import (DevelopmentSimulator, SINGLE_CENTER, catalog, DT,
                     NUMERICS_VERSION, source_inputs, agent_properties)


class Simulator(LocalProtocol):
    def __init__(self, config=None):
        config = dict(config or {})
        allowed = {'world_id', 'world_set', 'physics_version', 'noise', 'seed', 'wall_seconds', 'ruleset', 'energy_budget'}
        if set(config) - allowed:
            raise ValueError('Unknown v15 environment configuration fields')
        if config.get('world_set', 'v15') != 'v15':
            raise ValueError('world_set must be v15')
        if config.get('physics_version', V15_PHYSICS_VERSION) != V15_PHYSICS_VERSION:
            raise ValueError('physics_version must be shore_v15')
        self._world_id = validate_world_id(config.get('world_id', 'world_1'), 'v15')
        self._physics_version = V15_PHYSICS_VERSION
        self._world = self._world_id.removeprefix('world_')
        self._catalog = catalog.config(self._world)
        region = self._catalog['launch_region']
        reference_length = math.sqrt((region['radius_min']**2 + region['radius_max']**2) / 2)
        rules = rules_for(config)
        self.config = {
            'world_set': 'v15', 'world_id': self._world_id, 'physics_version': V15_PHYSICS_VERSION,
            'noise': False, 'seed': 7, 'wall_seconds': float(rules['wall_seconds']),
            'reference_length': reference_length, 'position_limit': region['radius_max'],
            'velocity_limit': self._catalog['initial_speed_max'],
            'time_max': self._catalog['maximum_physical_time'],
        }
        self.config.update(config)
        self.config['ruleset'] = rules['ruleset']
        if 'energy_budget' in config and (type(config['energy_budget']) is not int
                                          or config['energy_budget'] != rules['energy_budget']):
            raise ValueError('energy_budget must match ruleset')
        self.config['energy_budget'] = rules['energy_budget']
        if rules['ruleset'] in ('e4', 'e5'):
            self.config['noise'] = rules['ruleset'] == 'e4'
        if type(self.config['noise']) is not bool:
            raise ValueError('noise must be boolean')
        if type(self.config['seed']) is not int or self.config['seed'] < 0:
            raise ValueError('seed must be a nonnegative integer')
        wall = self._number(self.config['wall_seconds'], 'wall_seconds')
        if not 0 < wall <= rules['wall_seconds']:
            raise ValueError(f"wall_seconds must be positive and at most {rules['wall_seconds']}")
        self._sim = DevelopmentSimulator(self._world)
        self.started_at = None
        self.energy, self.observations = rules['energy_budget'], 20
        self.ended, self.end_reason = False, None
        self.rng = np.random.default_rng(self.config['seed'])
        self._velocity_rng = np.random.default_rng(np.random.SeedSequence(
            [self.config['seed'], 0x56454C]))
        self.probe_counter, self.observation_counter = 0, 0
        self.position_sigma = catalog.noise_sigma(self._world) if self.config['noise'] else 0.
        self.velocity_sigma = 1e-4 * self.config['velocity_limit'] if self.config['noise'] else 0.
        self._mission = self._make_mission()

    def _body_record(self, times):
        truth = self._sim.background(times)
        self.observation_counter += 1
        return {'observation_id': f'body_{self.observation_counter:04d}',
                'times': truth['times'].tolist(), 'body_ids': list(truth['ids']),
                'positions_obs': self._noisy_positions(truth['positions']).tolist()}

    def _probe_input(self, probe):
        parsed = super()._probe_input(probe)
        region = self._catalog['launch_region']
        radius = float(np.linalg.norm(np.asarray(parsed['r0']) - region['center']))
        if not region['radius_min'] - 1e-12 <= radius <= region['radius_max'] + 1e-12:
            raise InvalidRequest('initial_conditions', 'r0 must lie in the published launch annulus')
        if np.linalg.norm(parsed['v0']) > self.config['velocity_limit'] + 1e-12:
            raise InvalidRequest('initial_conditions', 'v0 magnitude exceeds initial_speed_max')
        scalar = self._world in SINGLE_CENTER
        allowed = {'mass', 'charge'} if scalar else {'mass'}
        if set(parsed['properties']) - allowed:
            raise InvalidRequest('probe_properties', 'Allowed properties: ' + ', '.join(sorted(allowed)))
        props = {name: parsed['properties'].get(name, 1.) for name in sorted(allowed)}
        upper = 2. if scalar else 4.
        if any(not .5 <= value <= upper for value in props.values()):
            raise InvalidRequest('probe_properties', f'Properties must lie in [0.5, {upper}]')
        parsed['properties'] = props
        return parsed

    def _probe_record(self, probe, times, t0, dt):
        source, properties = source_inputs(self._world, probe['properties'])
        truth = self._sim.launch(
            [{'pos': probe['r0'], 'vel': probe['v0'], 'properties': properties}],
            t0, (np.asarray(times) - t0).tolist(), source)
        positions = self._noisy_positions(truth['positions'][:, 0])
        velocities = truth['velocities'][:, 0].copy()
        if self.velocity_sigma:
            velocities += self._velocity_rng.normal(0., self.velocity_sigma, velocities.shape)
        enough = len(times) >= 3
        uniform = len(times) < 3 or np.allclose(np.diff(times), np.diff(times)[0], rtol=0, atol=1e-10)
        if enough and uniform:
            derivative = (velocities[2:] - velocities[:-2]) / (2 * dt)
            method = 'velocity_centered_difference'
        elif enough:
            derivative = np.gradient(velocities, times, axis=0)[1:-1]
            method = 'velocity_nonuniform_centered_difference'
        else:
            derivative, method = np.empty((0, 2)), 'unavailable_fewer_than_3_samples'
        self.probe_counter += 1
        return {'probe_id': f'probe_{self.probe_counter:04d}',
                'initial_conditions': dict(probe, t0=t0), 'times': truth['times'].tolist(),
                'r_obs': positions.tolist(), 'v_obs': velocities.tolist(),
                'a_est_times': truth['times'][1:-1].tolist() if enough else [],
                'a_est': derivative.tolist(), 'a_est_method': method}

    def insert_probe(self, probes, t0, dt, n_samples):
        # Validate these before computing the duration, without spending energy.
        if type(n_samples) is not int or not 1 <= n_samples <= 50:
            raise InvalidRequest('sample_limit', 'n_samples must be an integer from 1 to 50')
        spacing = self._physical_time(dt, 'dt')
        if (n_samples - 1) * spacing > self._catalog['maximum_single_trajectory_duration'] + 1e-10:
            raise InvalidRequest('trajectory_duration', 'Trajectory exceeds maximum_single_trajectory_duration')
        return super().insert_probe(probes, t0, dt, n_samples)

    def _make_mission(self):
        first = self._catalog['first_light']
        times = np.asarray(first['readout']) + first['t_launch']
        initial = [{'r0': item['pos'], 'v0': item['vel'],
                    'properties': agent_properties(self._world, first['source_properties'], item['properties'])}
                   for item in first['probes']]
        background = self._sim.background_initial_state()
        scalar = self._world in SINGLE_CENTER
        controls = {'mass': {'min': .5, 'max': 2. if scalar else 4., 'default': 1.}}
        if scalar:
            controls['charge'] = {'min': .5, 'max': 2., 'default': 1.}
        task = {
            'name': 'Local physics discovery · v15 public worlds', 'dimension': 2,
            'world_set': 'v15', 'world_id': self._world_id, 'world_name': world_name(self._world_id, 'v15'),
            'physics_version': V15_PHYSICS_VERSION, 'numerics_version': NUMERICS_VERSION,
            'ruleset': self.config['ruleset'],
            'units': {'position': 'local_length', 'time': 'local_time', 'velocity': 'local_length/local_time'},
            'body_ids': list(background['ids']), 'body_observation_protocol': 'time_series',
            'body_initial_states': [{'body_id': name, 'position': pos.tolist(), 'velocity': vel.tolist()}
                                    for name, pos, vel in zip(background['ids'], background['positions'], background['velocities'])],
            'body_position_source': 'body_initial_states gives exact states only at absolute t=0. At later times use acquired body observations.',
            'allowed_properties': list(controls), 'property_controls': controls,
            'property_mapping': ({'mass': 'public probe control p2', 'charge': 'public source control p1 for this probe experiment'}
                                 if scalar else {'mass': 'public probe control mass'}),
            'property_note': ('Each probe in a batch is an independent experiment. Its mass maps to p2 and charge maps to source p1; omitted values default to 1. The names are compatibility aliases, not claims about their physical effects.'
                              if scalar else 'mass is the public probe control; an omitted value defaults to 1.'),
            'reference_length': self.config['reference_length'], 'position_noise_sigma': self.position_sigma,
            'velocity_noise_sigma': self.velocity_sigma,
            'noise_note': 'Independent Gaussian position and probe-velocity noise on each new measurement when noise is enabled; cached records are immutable. Controlled initial states are exact.',
            'local_config_notice': f"v15 public physical domains with {self.config['ruleset']} local rules: {self.config['energy_budget']} energy, {self.config['wall_seconds']:g} seconds. This remains a compatibility adapter, not the standard contest Console.",
            'position_limit': self.config['position_limit'], 'velocity_limit': self.config['velocity_limit'],
            'launch_region': self._catalog['launch_region'], 'initial_speed_max': self.config['velocity_limit'],
            'maximum_single_trajectory_duration': self._catalog['maximum_single_trajectory_duration'],
            'physical_time_range': [0, self.config['time_max']], 'time_grid': DT,
            'limits': {'initial_energy': self.config['energy_budget'], 'energy_budget': self.config['energy_budget'], 'probe_energy': 1, 'max_batch_probes': 8,
                       'max_probe_samples': 50, 'max_observe_calls': 20, 'max_observe_times': 50,
                       'wall_seconds': self.config['wall_seconds']},
            'sampling_note': 'Absolute t0 plus uniform dt for insert_probe; n_samples includes t0. Thinking does not advance physical time. The supplied first-light times are nonuniform.',
            'first_light_note': 'Two free eight-sample public first-light probes plus background positions at matching times. Repeated mission reads return cached data and do not reset the session.',
        }
        return {'task': task, 'first_light': {'body_observation': self._body_record(times),
                'probes': [self._probe_record(probe, times, first['t_launch'], None) for probe in initial]}}
