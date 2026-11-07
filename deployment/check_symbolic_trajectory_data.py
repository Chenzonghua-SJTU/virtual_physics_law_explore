"""Build isolated A/B identifiability data; never an Agent mission or baseline.

Only this offline generator can call the public vendor acceleration oracle.
Exact labels are kept beside, never inside, the ordinary probe observations.
The A/B runners must share the same interior states, properties, and weights;
A replaces derivative targets with these labels, B only receives probe records.
No world-specific force formula or parameter is encoded in this module.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WORLD_IDS = tuple(f'world_{i}' for i in range(1, 7))
N_SAMPLES = 50
SAMPLE_INTERVAL = .02
TIME_CONTROLS = (3., 7., 11., 17., 23., 29., 31.)


def _initial(radius, angle_degrees, speed, velocity_degrees, *, t0=0., mass=1., charge=1.):
    angle, velocity_angle = map(math.radians, (angle_degrees, velocity_degrees))
    return {'r0': [radius * math.cos(angle), radius * math.sin(angle)],
            'v0': [speed * math.cos(velocity_angle), speed * math.sin(velocity_angle)],
            'properties': {'mass': float(mass), 'charge': float(charge)}, 't0': float(t0)}


def sampling_plan():
    """Identical, deterministic controls for all worlds; contains no force queries."""
    training = [dict(initial_conditions=_initial(radius, angle, speed, direction),
                     design_role='spatial_velocity_coverage')
                for radius, angle, speed, direction in zip(
                    (1.5, 2., 2.5, 3., 3.5, 4.), (15., 75., 135., 195., 255., 315.),
                    (.12, .18, .15, .10, .20, .16), (80., 190., 320., 40., 155., 265.))]
    # Two nonparallel initial position vectors support independent controls.
    for anchor, property_name, value in ((0, 'mass', .5), (0, 'charge', 2.),
                                         (2, 'mass', 2.), (2, 'charge', .5)):
        initial = copy.deepcopy(training[anchor]['initial_conditions'])
        initial['properties'][property_name] = value
        training.append({'initial_conditions': initial, 'design_role': 'property_control',
                         'control_anchor': anchor, 'changed_property': property_name})
    for anchor in (0, 2):
        for t0 in TIME_CONTROLS:
            initial = copy.deepcopy(training[anchor]['initial_conditions'])
            initial['t0'] = t0
            training.append({'initial_conditions': initial, 'design_role': 'absolute_time_control',
                             'control_anchor': anchor})
    heldout = [dict(initial_conditions=_initial(radius, angle, speed, direction,
                        t0=t0, mass=mass, charge=charge), design_role='heldout_only')
               for radius, angle, speed, direction, t0, mass, charge in zip(
                   (1.7, 2.2, 2.7, 3.2, 3.7, 1.9, 2.9, 3.9),
                   (40., 85., 130., 175., 220., 265., 310., 355.),
                   (.11, .17, .13, .19, .14, .16, .12, .18),
                   (25., 145., 255., 345., 75., 205., 295., 115.),
                   (2., 6., 10., 14., 18., 22., 26., 30.),
                   (.75, 1.5, 1.25, .6, 1.8, .9, 1.4, 1.1),
                   (1.5, .75, 1.2, 1.8, .6, 1.4, 1.1, .9))]
    return {'train': training, 'heldout': heldout}


def _validate_initial(initial, public_config, time_grid):
    radius = float(np.linalg.norm(initial['r0']))
    region = public_config['launch_region']
    if not region['radius_min'] <= radius <= region['radius_max']:
        raise ValueError('Planned initial radius is outside the public domain')
    if np.linalg.norm(initial['v0']) > public_config['initial_speed_max']:
        raise ValueError('Planned speed is outside the public domain')
    duration = (N_SAMPLES - 1) * SAMPLE_INTERVAL
    if duration > public_config['maximum_single_trajectory_duration']:
        raise ValueError('Planned duration is outside the public domain')
    if initial['t0'] < 0 or initial['t0'] + duration > public_config['maximum_physical_time']:
        raise ValueError('Planned absolute times are outside the public domain')
    if any(abs(value / time_grid - round(value / time_grid)) > 1e-8
           for value in (initial['t0'], SAMPLE_INTERVAL)):
        raise ValueError('Planned sampling must follow the public time grid')


def build_dataset(world_id, *, simulator_factory=None):
    """Return one isolated dataset. Actual simulation occurs only when called.

    ``simulator_factory`` is a test seam; normal use loads the unchanged public
    simulator. The returned train/heldout probe lists contain no oracle labels.
    """
    if world_id not in WORLD_IDS:
        raise ValueError('Choose an explicit public world_1 through world_6')
    from shore_v15.source import DevelopmentSimulator, SINGLE_CENTER, catalog, DT, source_inputs

    world = world_id.removeprefix('world_')
    simulator = (simulator_factory or DevelopmentSimulator)(world)
    public_config = catalog.config(world)
    plan = sampling_plan()
    record = {'world_id': world_id, 'diagnostic_only': True,
              'train_probes': [], 'heldout_probes': [],
              'exact_acceleration': {'train': {}, 'heldout': {}}, 'design': plan,
              'feature_property_note': (
                  'Both mass and charge vary in every world. For single-center public worlds, '
                  'charge maps to source p1 and mass to probe p2; elsewhere mass is passed to '
                  'the vendor and charge is an inert diagnostic nuisance feature. This is '
                  'offline identifiability data, not the Agent allowed-property surface.'),
              'vendor_property_mapping': ('charge->source.p1,mass->probe.p2'
                                          if world in SINGLE_CENTER else 'mass->probe.mass;charge->unused')}
    for split, items in plan.items():
        for index, item in enumerate(items):
            initial = copy.deepcopy(item['initial_conditions'])
            _validate_initial(initial, public_config, DT)
            source, properties = source_inputs(world, initial['properties'])
            offsets = (np.arange(N_SAMPLES) * SAMPLE_INTERVAL).tolist()
            trajectory = simulator.launch(
                [{'pos': initial['r0'], 'vel': initial['v0'], 'properties': properties}],
                initial['t0'], offsets, source)
            times = np.asarray(trajectory['times'], dtype=float)
            positions = np.asarray(trajectory['positions'], dtype=float)[:, 0]
            velocities = np.asarray(trajectory['velocities'], dtype=float)[:, 0]
            exact = np.asarray([simulator.acceleration(float(t), r[None, :],
                    source_properties=source, probe_properties=properties)[0]
                    for t, r in zip(times[1:-1], positions[1:-1])], dtype=float)
            if (times.shape != (N_SAMPLES,) or positions.shape != (N_SAMPLES, 2)
                    or velocities.shape != positions.shape or exact.shape != (N_SAMPLES-2, 2)
                    or not all(np.isfinite(a).all() for a in (times, positions, velocities, exact))):
                raise ValueError('Vendor returned invalid diagnostic arrays')
            probe_id = f'diagnostic_{split}_{index+1:04d}'
            probe = {'probe_id': probe_id, 'initial_conditions': initial,
                     'times': times.tolist(), 'r_obs': positions.tolist(), 'v_obs': velocities.tolist()}
            record[f'{split}_probes'].append(probe)
            record['exact_acceleration'][split][probe_id] = {
                'times': times[1:-1].tolist(), 'values': exact.tolist()}
    return record


def generate_dataset_bundle(world_ids=WORLD_IDS, *, simulator_factory=None):
    worlds = list(world_ids)
    if not worlds or len(worlds) != len(set(worlds)) or set(worlds) - set(WORLD_IDS):
        raise ValueError('Provide distinct public world ids')
    return {'schema_version': 1, 'kind': 'offline_pysr_identifiability_not_agent_result',
            'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'diagnostic_only': True, 'agent_access': False,
            'sampling_protocol': {
                'worlds': worlds, 'train_probe_count': 24, 'heldout_probe_count': 8,
                'samples_per_probe': N_SAMPLES, 'dt': SAMPLE_INTERVAL,
                'trajectory_duration': (N_SAMPLES-1)*SAMPLE_INTERVAL,
                'interior_rows_per_training_probe': N_SAMPLES-2,
                'absolute_time_controls': list(TIME_CONTROLS),
                'noise': False, 'input_features': ['t', 'x', 'y', 'vx', 'vy', 'mass', 'charge'],
                'weighting': 'Each training probe has equal total weight; its interior states have equal weight.',
                'A_target': 'Exact vendor acceleration at the same interior states used by B.',
                'B_target': 'Velocity difference recomputed exclusively from train_probes r_obs/v_obs/times.',
                'heldout_policy': 'Score only after training selection. Never search, fit, tune or select using heldout.',
                'budget_note': '32 probes per world intentionally exceeds one Agent energy budget; this is an offline capability diagnostic.',
                'formula_is_search_input': False, 'hidden_evaluation_used': False},
            'source_sha256': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (Path(__file__).resolve(), ROOT/'shore_v15/source.py',
                             ROOT/'shore_v15/vendor/development_worlds/worlds.py',
                             ROOT/'shore_v15/vendor/development_worlds/catalog.py',
                             ROOT/'shore_v15/vendor/rift_numerics/rollout.py')},
            'datasets': [build_dataset(world, simulator_factory=simulator_factory) for world in worlds]}


def write_new_bundle(output, bundle):
    output = Path(output).resolve()
    for forbidden in ('runs', 'shore_agent', 'shore_sim', 'shore_v15'):
        if output == ROOT/forbidden or ROOT/forbidden in output.parents:
            raise ValueError('Oracle-label diagnostics must stay outside Agent records and source packages')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as handle:
        json.dump(bundle, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worlds', nargs='+', choices=WORLD_IDS, default=WORLD_IDS)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Diagnostic output already exists; will not overwrite')
    bundle = generate_dataset_bundle(args.worlds)
    write_new_bundle(args.output, bundle)
    print(json.dumps({'status': 'prepared', 'path': str(args.output),
                      'world_count': len(bundle['datasets']), 'train_per_world': 24,
                      'heldout_per_world': 8, 'agent_experiments_started': 0}))


if __name__ == '__main__':
    main()
