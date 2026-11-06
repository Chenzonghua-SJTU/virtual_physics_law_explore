"""Private physics and legal observation boundary for local virtual worlds.

Only this process and the independent evaluator may access physical truth.
"""
import copy
import math
import time

import numpy as np
from scipy.integrate import solve_ivp

from shore_worlds import (CURRENT_PHYSICS_VERSION, DEFAULT_WORLD_ID, PHYSICS_VERSIONS,
                          validate_physics_version, validate_world_id, world_name)
from .worlds import (analytic_trajectory, body_initial_states, body_positions_at,
                     make_dynamics, truth_reference, truth_trajectory)

GRID = 0.005
ALLOWED_PROPERTIES = ("mass", "charge")


class InvalidRequest(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class Simulator:
    METHODS = frozenset(("mission", "observe_body", "insert_probe", "budget", "end_session"))

    def __init__(self, config=None):
        config = dict(config or {})
        allowed = {"world_id", "physics_version", "noise", "seed", "reference_length", "position_limit", "velocity_limit", "time_max", "wall_seconds"}
        if set(config) - allowed:
            raise ValueError("Unknown local environment configuration fields: " + ", ".join(sorted(set(config) - allowed)))
        self.config = {"world_id": DEFAULT_WORLD_ID, "physics_version": CURRENT_PHYSICS_VERSION,
                       "noise": False, "seed": 7, "reference_length": 10.0, "position_limit": 5.0,
                       "velocity_limit": 3.0, "time_max": 30.0, "wall_seconds": 3600.0}
        self.config.update(config)
        self._world_id = validate_world_id(self.config["world_id"])
        self._physics_version = validate_physics_version(self.config["physics_version"])
        if self._physics_version not in PHYSICS_VERSIONS:
            raise ValueError("Legacy simulator requires a legacy physics version")
        self._dynamics = make_dynamics(self._world_id, physics_version=self._physics_version)
        if type(self.config["noise"]) is not bool:
            raise ValueError("noise must be boolean")
        if type(self.config["seed"]) is not int or self.config["seed"] < 0:
            raise ValueError("seed must be a nonnegative integer")
        for field in ("reference_length", "position_limit", "velocity_limit", "time_max", "wall_seconds"):
            value = self.config[field]
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
                raise ValueError(field + " must be a positive finite number")
        if self.config["time_max"] < 7 * GRID:
            raise ValueError("time_max must allow at least eight first-light grid samples")
        if self.config["wall_seconds"] > 3600:
            raise ValueError("wall_seconds cannot exceed the 60-minute session limit")
        # Constructing a local worker is not beginning the scientific session.
        # The first successful mission call starts its one immutable wall clock.
        self.started_at = None
        self.energy = 100
        self.observations = 20
        self.ended = False
        self.end_reason = None
        self.rng = np.random.default_rng(self.config["seed"])
        self.probe_counter = 0
        self.observation_counter = 0
        self.position_sigma = self.config["reference_length"] * 0.01 if self.config["noise"] else 0.0
        self._mission = self._make_mission()

    def budget(self):
        elapsed = 0.0 if self.started_at is None else time.monotonic() - self.started_at
        remaining = max(0.0, self.config["wall_seconds"] - elapsed)
        if remaining == 0:
            self.ended = True
            self.end_reason = self.end_reason or "wall_time_exhausted"
        return {"energy_remaining": self.energy, "observations_remaining": self.observations,
                "wall_seconds_remaining": remaining, "session_ended": self.ended}

    def _ensure_active(self):
        if self.started_at is None:
            raise InvalidRequest("mission_required", "Initialize the session with mission before conducting experiments")
        if self.budget()["session_ended"]:
            raise InvalidRequest("session_ended", "The session has ended: " + str(self.end_reason))

    def _envelope(self, ok, data=None, error=None):
        return {"ok": ok, "data": data, "error": error, "budget": self.budget()}

    def request(self, method, **kwargs):
        try:
            if method not in self.METHODS:
                raise InvalidRequest("unknown_method", "Method is not exposed by the observation service")
            if method not in ("mission", "budget", "end_session"):
                self._ensure_active()
            if method == "mission":
                if kwargs:
                    raise InvalidRequest("invalid_arguments", "mission takes no arguments")
                data = copy.deepcopy(self._mission)
                if self.started_at is None and not self.ended:
                    self.started_at = time.monotonic()
            elif method == "budget":
                if kwargs:
                    raise InvalidRequest("invalid_arguments", "budget takes no arguments")
                data = self.budget()
            elif method == "end_session":
                if kwargs:
                    raise InvalidRequest("invalid_arguments", "end_session takes no arguments")
                self.ended, self.end_reason = True, "explicit_end"
                data = {"session_ended": True}
            elif method == "observe_body":
                data = self.observe_body(**kwargs)
            else:
                data = self.insert_probe(**kwargs)
            return self._envelope(True, data=data)
        except InvalidRequest as exc:
            return self._envelope(False, error={"code": exc.code, "message": str(exc)})
        except (TypeError, ValueError, OverflowError) as exc:
            return self._envelope(False, error={"code": "invalid_arguments", "message": str(exc)})
        except Exception:
            # Never leak backend source, stack traces, or true derivative values.
            return self._envelope(False, error={"code": "simulation_failed", "message": "The numerical observation request failed"})

    @staticmethod
    def _number(value, name):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise InvalidRequest("invalid_arguments", name + " must be a finite number")
        return float(value)

    def _physical_time(self, value, name):
        value = self._number(value, name)
        if value < 0 or value > self.config["time_max"] + 1e-10:
            raise InvalidRequest("time_range", name + " is outside the published local physical-time range")
        if not math.isclose(value / GRID, round(value / GRID), rel_tol=0, abs_tol=1e-7):
            raise InvalidRequest("time_grid", name + " must align with the 0.005 physical-time grid")
        return round(value / GRID) * GRID

    def _times(self, times):
        if not isinstance(times, list) or not 1 <= len(times) <= 50:
            raise InvalidRequest("sample_limit", "times must contain between 1 and 50 times")
        parsed = [self._physical_time(value, "times") for value in times]
        if any(b <= a for a, b in zip(parsed, parsed[1:])):
            raise InvalidRequest("time_order", "times must be strictly increasing")
        return np.asarray(parsed)

    def _vector(self, value, name, limit):
        if not isinstance(value, list) or len(value) != 2:
            raise InvalidRequest("initial_conditions", name + " must be a 2-component list")
        vector = [self._number(element, name) for element in value]
        if any(abs(element) > limit for element in vector):
            raise InvalidRequest("initial_conditions", name + " exceeds the published local per-coordinate bound")
        return vector

    def _probe_input(self, probe):
        if not isinstance(probe, dict) or set(probe) != {"r0", "v0", "properties"}:
            raise InvalidRequest("initial_conditions", "Each probe requires exactly r0, v0, properties")
        r0 = self._vector(probe["r0"], "r0", self.config["position_limit"])
        v0 = self._vector(probe["v0"], "v0", self.config["velocity_limit"])
        properties = probe["properties"]
        if not isinstance(properties, dict) or set(properties) - set(ALLOWED_PROPERTIES):
            raise InvalidRequest("probe_properties", "Allowed local properties are mass and charge")
        properties = {name: self._number(value, name) for name, value in properties.items()}
        return {"r0": r0, "v0": v0, "properties": properties}

    def _noisy_positions(self, positions):
        if self.position_sigma:
            return positions + self.rng.normal(0.0, self.position_sigma, size=positions.shape)
        return positions.copy()

    def _body_record(self, times):
        self.observation_counter += 1
        return {"observation_id": "body_%04d" % self.observation_counter,
                "times": times.tolist(), "body_ids": ["b1", "b2", "b3"],
                "positions_obs": self._noisy_positions(body_positions_at(
                    times, self._world_id, self._physics_version)).tolist()}

    def observe_body(self, times):
        parsed = self._times(times)
        if self.observations <= 0:
            raise InvalidRequest("observation_budget", "No body-observation calls remain")
        record = self._body_record(parsed)
        self.observations -= 1
        return record

    def _probe_record(self, probe, times, t0, dt):
        state0 = np.array(probe["r0"] + probe["v0"], dtype=float)
        if len(times) == 1:
            states = state0[None, :]
        else:
            result = solve_ivp(self._dynamics, (t0, float(times[-1])), state0, t_eval=times,
                               method="DOP853", rtol=1e-10, atol=1e-12)
            if not result.success or result.y.shape != (4, len(times)) or not np.isfinite(result.y).all():
                raise RuntimeError("Integration failed")
            states = result.y.T
        v_obs = states[:, 2:]
        enough = len(times) >= 3
        self.probe_counter += 1
        return {"probe_id": "probe_%04d" % self.probe_counter,
                "initial_conditions": dict(probe, t0=t0), "times": times.tolist(),
                "r_obs": self._noisy_positions(states[:, :2]).tolist(), "v_obs": v_obs.tolist(),
                "a_est_times": times[1:-1].tolist() if enough else [],
                "a_est": ((v_obs[2:] - v_obs[:-2]) / (2 * dt)).tolist() if enough else [],
                "a_est_method": "velocity_centered_difference" if enough else "unavailable_fewer_than_3_samples"}

    def insert_probe(self, probes, t0, dt, n_samples):
        if not isinstance(probes, list) or not 1 <= len(probes) <= 8:
            raise InvalidRequest("batch_limit", "Each batch must contain 1 to 8 probes")
        if type(n_samples) is not int or not 1 <= n_samples <= 50:
            raise InvalidRequest("sample_limit", "n_samples must be an integer from 1 to 50 (including the initial sample)")
        t0 = self._physical_time(t0, "t0")
        dt = self._physical_time(dt, "dt")
        if dt <= 0:
            raise InvalidRequest("time_interval", "dt must be positive")
        final_time = self._physical_time(t0 + (n_samples - 1) * dt, "last sample")
        parsed = [self._probe_input(probe) for probe in probes]
        if len(parsed) > self.energy:
            raise InvalidRequest("energy_budget", "Not enough energy for this batch")
        times = t0 + np.arange(n_samples) * dt
        times[-1] = final_time
        # Reserve energy after full input validation but before numerical work.
        # An internal numerical failure refunds the whole batch.
        self.energy -= len(parsed)
        try:
            return {"probes": [self._probe_record(probe, times, t0, dt) for probe in parsed]}
        except Exception:
            self.energy += len(parsed)
            raise

    def _make_mission(self):
        dt = min(0.5, math.floor((self.config["time_max"] / 7 + 1e-12) / GRID) * GRID)
        times = np.arange(8) * dt
        x = min(1.0, self.config["position_limit"] / 2)
        v = min(0.5, self.config["velocity_limit"] / 2)
        initial = [{"r0": [-x, 0.0], "v0": [v, 0.0], "properties": {}},
                   {"r0": [x, x], "v0": [0.0, -v], "properties": {}}]
        task = {
            "name": "Local physics discovery prototype", "dimension": 2,
            "world_id": self._world_id, "world_name": world_name(self._world_id),
            "physics_version": self._physics_version,
            "units": {"position": "local_length", "time": "local_time", "velocity": "local_length/local_time"},
            "body_ids": ["b1", "b2", "b3"], "static_visible_bodies": True,
            "body_position_source": "Only positions_obs in acquired body observations provide coordinates. No exact body positions are supplied separately.",
            "allowed_properties": list(ALLOWED_PROPERTIES),
            "reference_length": self.config["reference_length"], "position_noise_sigma": self.position_sigma,
            "velocity_noise_sigma": 0.0,
            "noise_note": "Independent zero-mean Gaussian position noise per coordinate for each new observation; cached records are immutable.",
            "local_config_notice": "Launch ranges, physical-time range, units, reference length and probe-property names are local prototype settings, not official competition parameters.",
            "position_limit": self.config["position_limit"], "velocity_limit": self.config["velocity_limit"],
            "physical_time_range": [0, self.config["time_max"]], "time_grid": GRID,
            "limits": {"initial_energy": 100, "probe_energy": 1, "max_batch_probes": 8,
                       "max_probe_samples": 50, "max_observe_calls": 20, "max_observe_times": 50,
                       "wall_seconds": self.config["wall_seconds"]},
            "sampling_note": "All times are absolute physical times. K includes t0; dt is a sampling interval. Model thinking consumes wall time without advancing physical time.",
            "first_light_note": "One free body observation and two free standard probe trajectories, all sharing eight absolute times including t0. Repeated mission reads return the same data without resetting the session.",
        }
        if self._physics_version == 'v4':
            del task['static_visible_bodies']
            task['body_initial_states'] = body_initial_states(self._world_id, self._physics_version)
            task['body_observation_protocol'] = 'time_series'
            task['body_position_source'] = (
                'body_initial_states supplies exact positions and velocities only at absolute t=0. '
                'At other times, use positions_obs from acquired body observations; '
                'initial velocities alone do not specify later motion.')
        return {"task": task, "first_light": {"body_observation": self._body_record(times),
                "probes": [self._probe_record(probe, times, 0.0, dt) for probe in initial]}}
