"""Offline diagnostic plumbing only; no real world simulation or symbolic search."""
import copy

import numpy as np
import pytest

from deployment.check_symbolic_trajectory_data import (
    ROOT, N_SAMPLES, SAMPLE_INTERVAL, TIME_CONTROLS, build_dataset, sampling_plan, write_new_bundle,
)


def test_plan_preserves_independent_property_and_absolute_time_controls():
    plan = sampling_plan()
    assert len(plan['train']) == 24 and len(plan['heldout']) == 8
    for item in plan['train'][6:10]:
        original = plan['train'][item['control_anchor']]['initial_conditions']
        modified = copy.deepcopy(item['initial_conditions'])
        name = item['changed_property']
        assert modified['properties'][name] != original['properties'][name]
        modified['properties'][name] = original['properties'][name]
        assert modified == original
    for anchor in (0, 2):
        controls = [item for item in plan['train'] if item['design_role'] == 'absolute_time_control'
                    and item['control_anchor'] == anchor]
        assert [item['initial_conditions']['t0'] for item in controls] == list(TIME_CONTROLS)
        for item in controls:
            restored = copy.deepcopy(item['initial_conditions'])
            restored['t0'] = 0.
            assert restored == plan['train'][anchor]['initial_conditions']
    assert all(item['initial_conditions']['t0'] + (N_SAMPLES-1)*SAMPLE_INTERVAL <= 32
               for items in plan.values() for item in items)


class FakeVendor:
    """Marker labels deliberately differ from linear motion's derivative."""
    instances = []

    def __init__(self, world):
        self.world, self.calls = world, []
        self.instances.append(self)

    def launch(self, probes, t0, readout, source):
        self.calls.append((copy.deepcopy(probes), copy.deepcopy(source)))
        offsets = np.asarray(readout)
        probe = probes[0]
        velocity = np.asarray(probe['vel'])
        positions = np.asarray(probe['pos']) + offsets[:, None] * velocity
        return {'times': t0 + offsets, 'positions': positions[:, None, :],
                'velocities': np.tile(velocity, (len(offsets), 1, 1))}

    def acceleration(self, t, positions, *, source_properties, probe_properties):
        return np.tile([7., 11.], (len(positions), 1))


def test_exact_labels_are_separate_and_interior_aligned_for_same_observations():
    scalar = build_dataset('world_1', simulator_factory=FakeVendor)
    other = build_dataset('world_3', simulator_factory=FakeVendor)
    for split in ('train', 'heldout'):
        assert scalar[f'{split}_probes'] == other[f'{split}_probes']
        for probe in scalar[f'{split}_probes']:
            assert set(probe) == {'probe_id', 'initial_conditions', 'times', 'r_obs', 'v_obs'}
            exact = scalar['exact_acceleration'][split][probe['probe_id']]
            assert exact['times'] == probe['times'][1:-1]
            assert len(exact['values']) == 48
            assert exact['values'] == [[7., 11.]] * 48
            velocity_difference = np.gradient(probe['v_obs'], probe['times'], axis=0)[1:-1]
            np.testing.assert_allclose(velocity_difference, 0., atol=1e-12)
    scalar_sim, other_sim = FakeVendor.instances[-2:]
    assert scalar_sim.calls[0][1] == {'p1': 1.}
    assert scalar_sim.calls[0][0][0]['properties'] == {'p2': 1.}
    assert other_sim.calls[0][1] == {}
    assert other_sim.calls[0][0][0]['properties'] == {'mass': 1.}
    assert scalar_sim.calls[7][1] == {'p1': 2.}
    assert other_sim.calls[7][1] == {}


def test_oracle_archive_cannot_overwrite_or_enter_agent_records(tmp_path):
    with pytest.raises(ValueError, match='outside Agent'):
        write_new_bundle(ROOT/'runs/forbidden-diagnostic/labels.json', {'diagnostic_only': True})
    output = tmp_path/'labels.json'
    write_new_bundle(output, {'diagnostic_only': True})
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        write_new_bundle(output, {'diagnostic_only': False})
    assert output.read_bytes() == original
