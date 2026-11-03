"""Truth is allowed in tests only, never in a runtime tool or model prompt."""
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from shore_agent.environment import Environment
from shore_sim.simulator import Simulator, analytic_trajectory
from shore_worlds import PHYSICS_VERSIONS


def started_simulator(config=None):
    simulator = Simulator(config)
    simulator.request("mission")
    return simulator


def probe(r0=None, v0=None):
    return {"r0": r0 or [-1.5, 1.8], "v0": v0 or [0.7, -0.4], "properties": {}}


def insert(simulator, **overrides):
    arguments = {"probes": [probe()], "t0": 2.0, "dt": 0.1, "n_samples": 30}
    arguments.update(overrides)
    return simulator.request("insert_probe", **arguments)


def test_numerical_trajectory_matches_independent_analytic_solution():
    sim = started_simulator()
    result = insert(sim)
    assert result["ok"]
    record = result["data"]["probes"][0]
    initial = record["initial_conditions"]
    expected = analytic_trajectory(initial["r0"], initial["v0"], record["times"], initial["t0"])
    np.testing.assert_allclose(record["r_obs"], expected[:, :2], atol=1e-8)
    np.testing.assert_allclose(record["v_obs"], expected[:, 2:], atol=1e-8)
    assert record["times"][0] == 2.0
    np.testing.assert_array_equal(record["r_obs"][0], initial["r0"])
    np.testing.assert_array_equal(record["v_obs"][0], initial["v0"])
    assert np.shape(record["r_obs"]) == (30, 2)
    assert np.shape(record["a_est"]) == (28, 2)


def test_acceleration_is_centered_difference_not_backend_derivative():
    record = insert(started_simulator(), dt=0.5)["data"]["probes"][0]
    velocity = np.asarray(record["v_obs"])
    np.testing.assert_array_equal(record["a_est"], (velocity[2:] - velocity[:-2]) / 1.0)
    assert record["a_est_times"] == record["times"][1:-1]
    # The coarse finite-difference result is deliberately not the exact derivative.
    truth_acceleration = -0.3 * (np.asarray(record["r_obs"])[1:-1] - [0, 1])
    assert np.max(np.abs(truth_acceleration - record["a_est"])) > 0.001
    assert "a_true" not in record


@pytest.mark.parametrize("count", [1, 2])
def test_short_trajectories_do_not_invent_acceleration(count):
    record = insert(started_simulator(), n_samples=count)["data"]["probes"][0]
    assert record["a_est"] == []
    assert record["a_est_times"] == []
    assert record["a_est_method"] == "unavailable_fewer_than_3_samples"
    assert len(record["times"]) == count


@pytest.mark.parametrize('version', PHYSICS_VERSIONS)
def test_first_light_is_free_cached_and_has_full_time_axes(version):
    sim = started_simulator({"noise": True, 'physics_version': version})
    one = sim.request("mission")
    two = sim.request("mission")
    assert one["data"] == two["data"]
    assert two["budget"]["energy_remaining"] == 100
    assert two["budget"]["observations_remaining"] == 20
    assert two["budget"]["wall_seconds_remaining"] < one["budget"]["wall_seconds_remaining"]
    free = one["data"]["first_light"]
    assert len(free["probes"]) == 2
    body = free["body_observation"]
    assert np.shape(body["positions_obs"]) == (8, 3, 2)
    for record in free["probes"]:
        assert len(record["times"]) == 8
        assert record["times"] == body["times"]
        assert record["times"][0] == 0
    assert 'visible_bodies' not in one['data']['task']
    assert not any(key in one['data']['task'] for key in ('positions', 'body_positions', 'known_bodies'))
    task = one['data']['task']
    if version == 'v4':
        assert 'static_visible_bodies' not in task
        assert task['body_observation_protocol'] == 'time_series'
        assert task['body_initial_states'] == [
            {'body_id': 'b1', 'position': [-2., 0.], 'velocity': [0., 0.]},
            {'body_id': 'b2', 'position': [2., 0.], 'velocity': [0., 0.]},
            {'body_id': 'b3', 'position': [0., 3.], 'velocity': [0., 0.]},
        ]
        assert body['positions_obs'][0] != [state['position'] for state in task['body_initial_states']]
    else:
        assert task['static_visible_bodies'] is True
        assert 'body_initial_states' not in task
        assert 'body_observation_protocol' not in task
        assert task['body_position_source'] == (
            'Only positions_obs in acquired body observations provide coordinates. '
            'No exact body positions are supplied separately.')
    one["data"]["task"]["body_ids"].clear()
    assert len(sim.request("mission")["data"]["task"]["body_ids"]) == 3


def test_observation_noise_is_new_per_experiment_and_only_on_positions():
    noisy = started_simulator({"noise": True, "seed": 123})
    noiseless = started_simulator({"noise": False, "seed": 123})
    one = insert(noisy)["data"]["probes"][0]
    two = insert(noisy)["data"]["probes"][0]
    clean = insert(noiseless)["data"]["probes"][0]
    assert one["probe_id"] != two["probe_id"]
    assert one["r_obs"] != two["r_obs"]
    assert one["v_obs"] == two["v_obs"] == clean["v_obs"]
    assert one["a_est"] == clean["a_est"]
    assert noisy.request("mission")["data"]["task"]["position_noise_sigma"] == 0.1
    # A seeded batch large enough to check the published noise scale.
    records = insert(noisy, probes=[probe()] * 8, n_samples=50)["data"]["probes"]
    deviations = []
    for record in records:
        expected = analytic_trajectory(probe()["r0"], probe()["v0"], record["times"])
        deviations.extend((np.asarray(record["r_obs"]) - expected[:, :2]).ravel())
    assert abs(np.mean(deviations)) < 0.015
    assert 0.085 < np.std(deviations) < 0.115


@pytest.mark.parametrize("overrides,code", [
    ({"t0": 0.001}, "time_grid"),
    ({"dt": 0.001}, "time_grid"),
    ({"dt": 0}, "time_interval"),
    ({"t0": -0.005}, "time_range"),
    ({"t0": 29.0, "dt": 0.1, "n_samples": 12}, "time_range"),
    ({"n_samples": 51}, "sample_limit"),
    ({"n_samples": True}, "sample_limit"),
    ({"probes": [probe()] * 9}, "batch_limit"),
    ({"probes": [probe([5.01, 0])]}, "initial_conditions"),
    ({"probes": [probe(v0=[0, -3.1])]}, "initial_conditions"),
    ({"probes": [{"r0": [0, 0], "v0": [0, 0], "properties": {"arbitrary": 2}}]}, "probe_properties"),
    ({"probes": [{"r0": [float("nan"), 0], "v0": [0, 0], "properties": {}}]}, "invalid_arguments"),
])
def test_invalid_probe_requests_do_not_consume_budget(overrides, code):
    sim = started_simulator()
    result = insert(sim, **overrides)
    assert not result["ok"]
    assert result["error"]["code"] == code
    assert result["budget"]["energy_remaining"] == 100


@pytest.mark.parametrize("times,code", [
    ([0, 0], "time_order"), ([1, 0], "time_order"), ([], "sample_limit"),
    (list(np.arange(51) * 0.005), "sample_limit"), ([0.001], "time_grid"),
    ([30.005], "time_range"), ([True], "invalid_arguments"),
])
def test_invalid_observation_requests_do_not_consume_budget(times, code):
    result = started_simulator().request("observe_body", times=times)
    assert not result["ok"]
    assert result["error"]["code"] == code
    assert result["budget"]["observations_remaining"] == 20


def test_energy_and_observation_limits_are_enforced_across_mission_reads():
    sim = started_simulator()
    for _ in range(12):
        assert insert(sim, probes=[probe()] * 8, n_samples=1)["ok"]
    assert insert(sim, probes=[probe()] * 5, n_samples=1)["error"]["code"] == "energy_budget"
    assert sim.request("mission")["budget"]["energy_remaining"] == 4
    assert insert(sim, probes=[probe()] * 4, n_samples=1)["ok"]
    assert insert(sim, n_samples=1)["error"]["code"] == "energy_budget"
    for _ in range(20):
        assert sim.request("observe_body", times=[0, 1])["ok"]
    assert sim.request("observe_body", times=[0])["error"]["code"] == "observation_budget"
    assert sim.request("mission")["budget"]["observations_remaining"] == 0


def test_wall_time_and_physical_time_are_independent_and_session_end_is_final():
    sim = started_simulator()
    before = sim.request("budget")["budget"]
    assert insert(sim, t0=29.5, dt=0.5, n_samples=2)["ok"]
    assert insert(sim, t0=0, n_samples=1)["ok"]
    # The simulator has no advancing global physical clock; each record has its own times.
    after = sim.request("budget")["budget"]
    assert before["wall_seconds_remaining"] - after["wall_seconds_remaining"] < 5
    sim.started_at -= 3601
    assert insert(sim)["error"]["code"] == "session_ended"
    assert sim.request("mission")["budget"]["session_ended"]
    sim2 = started_simulator()
    assert sim2.request("end_session")["budget"]["session_ended"]
    assert insert(sim2)["error"]["code"] == "session_ended"


def test_wall_clock_starts_only_on_first_successful_mission(monkeypatch):
    import shore_sim.simulator as module
    clock = [100.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    sim = Simulator({"wall_seconds": 10})
    clock[0] = 120.0
    assert sim.request("budget")["budget"]["wall_seconds_remaining"] == 10
    assert not sim.request("budget")["budget"]["session_ended"]
    assert insert(sim)["error"]["code"] == "mission_required"
    assert not sim.request("mission", reset=True)["ok"]
    assert sim.started_at is None
    one = sim.request("mission")
    assert sim.started_at == 120.0
    assert one["budget"]["wall_seconds_remaining"] == 10
    clock[0] = 124.0
    two = sim.request("mission")
    assert two["data"] == one["data"]
    assert two["budget"]["wall_seconds_remaining"] == 6
    assert sim.started_at == 120.0
    clock[0] = 131.0
    assert sim.request("mission")["budget"]["session_ended"]
    assert sim.started_at == 120.0


def test_rpc_process_boundary_and_white_list(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-secret-should-not-reach-worker")
    with Environment({"noise": True, "seed": 9}) as env:
        assert env._process.pid != os.getpid()
        mission = env.request("mission")
        assert mission["ok"]
        assert env.request("mission")["data"] == mission["data"]
        record = env.request("insert_probe", probes=[probe()], t0=0, dt=0.1, n_samples=3)
        assert record["ok"]
        assert record["budget"]["energy_remaining"] == 99
        for forbidden in ("_dynamics", "analytic_trajectory", "__dict__", "eval", "config"):
            result = env.request(forbidden)
            assert not result["ok"]
            assert result["error"]["code"] == "unknown_method"
        assert env.request("end_session")["ok"]
        assert env.request("observe_body", times=[0])["error"]["code"] == "session_ended"
    assert env._process.poll() is not None
    assert not env.request("mission")["ok"]


def test_adapter_strips_model_api_key_before_process_start(monkeypatch):
    import shore_agent.environment as module
    original = module.subprocess.Popen
    captured = {}

    def capture(*args, **kwargs):
        captured.update(kwargs["env"])
        return original(*args, **kwargs)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "private-test-value")
    monkeypatch.setattr(module.subprocess, "Popen", capture)
    with Environment() as env:
        assert env.request("budget")["ok"]
    assert "DEEPSEEK_API_KEY" not in captured


def test_worker_invalid_json_recovers_and_outputs_only_protocol():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-m", "shore_sim.worker"], cwd=root,
                            input='not json\n{"method":"mission","kwargs":{}}\n',
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(responses) == 2
    assert responses[0]["error"]["code"] == "invalid_request"
    assert responses[1]["ok"]
    assert not result.stderr
