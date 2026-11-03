"""Private development checks; these force/energy definitions never reach agents."""
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from shore_agent.environment import Environment
from shore_sim.simulator import Simulator, analytic_trajectory, truth_reference, truth_trajectory
from shore_worlds import (DEFAULT_WORLD_ID, WORLD_IDS, public_worlds,
                          CURRENT_PHYSICS_VERSION, LEGACY_PHYSICS_VERSION, PHYSICS_VERSIONS)


def simulator(world_id, noise=False, seed=91, physics_version=CURRENT_PHYSICS_VERSION):
    sim = Simulator({"world_id": world_id, "noise": noise, "seed": seed,
                     "physics_version": physics_version})
    assert sim.request("mission")["ok"]
    return sim


def experiment(sim, r0=None, v0=None, **kwargs):
    parameters = {"probes": [{"r0": [1.4, -1.1] if r0 is None else r0,
                              "v0": [0.7, -0.4] if v0 is None else v0,
                              "properties": {}}],
                  "t0": 0.6, "dt": 0.6, "n_samples": 50}
    parameters.update(kwargs)
    response = sim.request("insert_probe", **parameters)
    assert response["ok"], response
    return response["data"]["probes"][0]


def energy(world_id, states, physics_version=CURRENT_PHYSICS_VERSION):
    """Independent invariant definitions, without calling the force dispatcher."""
    r, v = states[:, :2], states[:, 2:]
    d = r - [0, 1]
    offset = r[:, None, :] - [[-2, 0], [2, 0], [0, 3]]
    squared_distance = np.sum(offset*offset, axis=2)
    kinetic = 0.5 * np.sum(v*v, axis=1)
    if world_id == "world_5" and physics_version != LEGACY_PHYSICS_VERSION:
        potential = 0.05 * np.sum(squared_distance, axis=1)
    elif world_id in ("world_1", "world_5"):
        potential = 0.15 * np.sum(d*d, axis=1)
    elif world_id == "world_2":
        potential = 0.175*d[:, 0]**2 + 0.08*d[:, 0]*d[:, 1] + 0.1*d[:, 1]**2
    elif world_id == "world_3":
        if physics_version == LEGACY_PHYSICS_VERSION:
            potential = 0.1*np.sum(d*d, axis=1) + 0.00375*np.sum(d**4, axis=1)
        else:
            potential = np.sum(0.03*squared_distance + 0.001*squared_distance**2, axis=1)
    else:
        potential = -0.8*np.sum(1/np.sqrt(squared_distance + 0.64), axis=1)
    return kinetic + potential


@pytest.mark.parametrize("world_id", WORLD_IDS[:5])
@pytest.mark.parametrize("physics_version", PHYSICS_VERSIONS)
@pytest.mark.parametrize("r0,v0", [([1.4, -1.1], [0.7, -0.4]), ([-5, -5], [3, 3])])
def test_autonomous_worlds_match_independent_reference_and_conserve_energy(world_id, physics_version, r0, v0):
    record = experiment(simulator(world_id, physics_version=physics_version), r0, v0)
    states = np.column_stack((record["r_obs"], record["v_obs"]))
    reference = truth_trajectory(r0, v0, record["times"], t0=0.6, world_id=world_id,
                                properties={}, physics_version=physics_version)
    assert states.shape == reference.shape == (50, 4)
    assert np.isfinite(states).all() and np.isfinite(reference).all()
    assert np.max(np.abs(states)) < 200
    np.testing.assert_array_equal(states[0], r0 + v0)
    np.testing.assert_allclose(states, reference, rtol=2e-7, atol=2e-7)
    invariant = energy(world_id, states, physics_version)
    assert np.max(np.abs(invariant - invariant[0])) / max(1, abs(invariant[0])) < 2e-8
    velocity = states[:, 2:]
    np.testing.assert_array_equal(record["a_est"], (velocity[2:] - velocity[:-2]) / 1.2)
    assert record["a_est_times"] == record["times"][1:-1]


def test_old_configuration_and_analytic_interface_still_mean_world_1():
    legacy = Simulator({"seed": 91})
    explicit = Simulator({"seed": 91, "world_id": "world_1"})
    assert DEFAULT_WORLD_ID == "world_1"
    assert legacy.request("mission")["data"] == explicit.request("mission")["data"]
    times = np.array([2.0, 2.7, 3.4])
    np.testing.assert_array_equal(analytic_trajectory([1, 2], [0.2, -0.4], times),
                                  truth_trajectory([1, 2], [0.2, -0.4], times))


def test_reference_descriptions_do_not_claim_nonlinear_analytic_truth():
    assert "analytic trajectory" in truth_reference("world_1")
    assert "matrix-exponential" in truth_reference("world_2")
    assert "matrix-exponential" in truth_reference("world_5", LEGACY_PHYSICS_VERSION)
    for version in PHYSICS_VERSIONS:
        for world_id in ("world_3", "world_4", "world_5"):
            if world_id == 'world_5' and version == LEGACY_PHYSICS_VERSION:
                continue
            assert "Radau" in truth_reference(world_id, version)
            assert "not analytic" in truth_reference(world_id, version)


@pytest.mark.parametrize("world_id", WORLD_IDS)
def test_noise_cache_budget_and_observation_rules_are_world_independent(world_id):
    clean = simulator(world_id)
    noisy = simulator(world_id, noise=True)
    mission = noisy.request("mission")
    assert mission["budget"]["energy_remaining"] == 100
    assert mission["budget"]["observations_remaining"] == 20
    assert noisy.request("mission")["data"] == mission["data"]
    light = mission["data"]["first_light"]
    assert len(light["probes"]) == 2
    assert np.shape(light["body_observation"]["positions_obs"]) == (8, 3, 2)
    for p in light["probes"]:
        assert p["times"] == light["body_observation"]["times"]
    assert mission["data"]["task"]["position_noise_sigma"] == 0.1

    clean_record = experiment(clean)
    first = experiment(noisy)
    second = experiment(noisy)
    assert first["probe_id"] != second["probe_id"]
    assert first["r_obs"] != second["r_obs"]
    assert first["v_obs"] == second["v_obs"] == clean_record["v_obs"]
    assert first["a_est"] == clean_record["a_est"]
    assert noisy.request("budget")["budget"]["energy_remaining"] == 98
    observed = noisy.request("observe_body", times=[0, 0.005, 30])
    assert observed["ok"]
    assert observed["budget"]["observations_remaining"] == 19
    assert np.shape(observed["data"]["positions_obs"]) == (3, 3, 2)
    assert not noisy.request("observe_body", times=[0.001])["ok"]
    assert noisy.request("budget")["budget"]["observations_remaining"] == 19


@pytest.mark.parametrize("world_id", WORLD_IDS)
def test_resource_exhaustion_and_clock_apply_in_all_worlds(world_id):
    sim = simulator(world_id)
    p = {"r0": [0, 0], "v0": [0, 0], "properties": {}}
    for count in [8]*12 + [4]:
        assert sim.request("insert_probe", probes=[p]*count, t0=0, dt=0.1, n_samples=1)["ok"]
    failure = sim.request("insert_probe", probes=[p], t0=0, dt=0.1, n_samples=1)
    assert failure["error"]["code"] == "energy_budget"
    for _ in range(20):
        assert sim.request("observe_body", times=[0])["ok"]
    assert sim.request("observe_body", times=[0])["error"]["code"] == "observation_budget"
    assert sim.request("mission")["budget"]["energy_remaining"] == 0
    sim.started_at -= 3601
    assert sim.request("observe_body", times=[0])["error"]["code"] == "session_ended"


def test_only_neutral_identity_and_legal_initial_states_change_in_the_public_task():
    baseline = None
    public_fields = {"probe_id", "initial_conditions", "times", "r_obs", "v_obs", "a_est_times", "a_est", "a_est_method"}
    for world_id in WORLD_IDS:
        data = simulator(world_id).request("mission")["data"]
        task = data["task"]
        assert task.pop("world_id") == world_id
        assert task.pop("world_name") == next(w["name"] for w in public_worlds() if w["id"] == world_id)
        initial_states = task.pop('body_initial_states')
        assert len(initial_states) == 3
        assert all(set(state) == {'body_id', 'position', 'velocity'} for state in initial_states)
        assert 'static_visible_bodies' not in task
        assert task['body_observation_protocol'] == 'time_series'
        if baseline is None:
            baseline = task
        else:
            assert task == baseline
        for record in data["first_light"]["probes"]:
            assert set(record) == public_fields
        assert set(data) == {"task", "first_light"}
        serialized = json.dumps(task).lower()
        for private_hint in ("stiffness", "quartic", "gyroscopic", "radau", "matrix-exponential", "truth_reference"):
            assert private_hint not in serialized


def test_force_fields_produce_seven_distinct_observed_trajectories():
    trajectories = [np.asarray(experiment(simulator(w))["r_obs"]) for w in WORLD_IDS]
    for i in range(len(trajectories)):
        for j in range(i):
            assert np.max(np.abs(trajectories[i] - trajectories[j])) > 0.05


@pytest.mark.parametrize("value", [None, "world_0", "world_8", "WORLD_1", "world_1/../x", 1, True, []])
def test_unknown_world_ids_are_rejected_before_a_session(value):
    with pytest.raises(ValueError, match="invalid_world_id"):
        Simulator({"world_id": value})
    with pytest.raises(ValueError, match="invalid_world_id"):
        truth_trajectory([0, 0], [0, 0], [0], world_id=value)


@pytest.mark.parametrize("world_id", WORLD_IDS)
def test_each_process_has_one_fixed_world_and_no_truth_rpc(world_id):
    with Environment({"world_id": world_id}) as env:
        mission = env.request("mission")
        assert mission["ok"]
        assert mission["data"]["task"]["world_id"] == world_id
        for forbidden in ("truth_trajectory", "truth_reference", "body_positions_at", "body_initial_states",
                          "acceleration", "make_dynamics", "set_world", "configure"):
            assert env.request(forbidden, world_id="world_1")["error"]["code"] == "unknown_method"
        assert env.request("mission", world_id="world_1")["error"]["code"] == "invalid_arguments"
        assert not env.request("insert_probe", world_id="world_1", probes=[], t0=0, dt=1, n_samples=1)["ok"]
        assert env.request("mission")["data"] == mission["data"]


def test_selection_is_bound_even_if_original_configuration_is_changed():
    config = {"world_id": "world_5"}
    sim = Simulator(config)
    config["world_id"] = "world_2"
    sim.request("mission")
    original = experiment(sim)
    # A host caller mutating its config dictionary cannot change the closed RHS.
    sim.config["world_id"] = "world_3"
    repeated = experiment(sim)
    assert original["r_obs"] == repeated["r_obs"]
    assert sim.request("mission")["data"]["task"]["world_id"] == "world_5"


def test_invalid_world_worker_fails_without_dumping_private_details():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-m", "shore_sim.worker", '{"world_id":"missing"}'],
                            cwd=root, input='', capture_output=True, text=True, timeout=30)
    assert result.returncode == 2
    response = json.loads(result.stdout)
    assert not response["ok"] and response["error"]["code"] == "startup_failed"
    assert response["data"] is None
    assert not result.stderr


@pytest.mark.parametrize("world_id", WORLD_IDS[:5])
@pytest.mark.parametrize("version", PHYSICS_VERSIONS)
def test_truth_reference_single_sample_and_absolute_initial_time(world_id, version):
    initial = [1.1, -0.4, -0.8, 0.3]
    np.testing.assert_allclose(truth_trajectory(initial[:2], initial[2:], [2], t0=2, world_id=world_id,
                                               physics_version=version),
                               [initial], rtol=0, atol=2e-15)
    relative = truth_trajectory(initial[:2], initial[2:], [0, 0.2, 0.4], world_id=world_id,
                                physics_version=version)
    shifted = truth_trajectory(initial[:2], initial[2:], [4, 4.2, 4.4], t0=4, world_id=world_id,
                               physics_version=version)
    np.testing.assert_allclose(shifted, relative, atol=2e-12, rtol=2e-12)


@pytest.mark.parametrize("position", [[-2, 0], [2, 0], [0, 3]])
@pytest.mark.parametrize("world_id", ['world_4', 'world_5'])
@pytest.mark.parametrize("version", ['v2', 'v3', 'v4'])
def test_softened_world_is_finite_at_each_visible_body(position, world_id, version):
    record = experiment(simulator(world_id, physics_version=version),
                        r0=position, v0=[.3, -.2], t0=0, dt=0.1, n_samples=20)
    states = np.column_stack((record["r_obs"], record["v_obs"]))
    reference = truth_trajectory(position, [.3, -.2], record["times"], world_id=world_id,
                                 physics_version=version)
    assert np.isfinite(states).all()
    np.testing.assert_allclose(states, reference, atol=2e-8, rtol=2e-8)
