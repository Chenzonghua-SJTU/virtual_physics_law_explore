"""Private force fields and post-session truth references.

Nothing in this module is exposed by the observation RPC or model tools. The
linear-world references use independent analytic constructions. Nonlinear
references use a different integration method and tighter tolerances than the
observation simulator, not an analytic oracle. Legacy physics remains available
only by explicit version so historical submissions keep their original truth.
"""
import math

import numpy as np
from scipy.integrate import solve_ivp
from scipy.linalg import expm

from shore_worlds import (DEFAULT_WORLD_ID, CURRENT_PHYSICS_VERSION,
                          LEGACY_PHYSICS_VERSION, validate_world_physics)


_BODIES = np.array([[-2.0, 0.0], [2.0, 0.0], [0.0, 3.0]])
_CENTER = np.array([0.0, 1.0])
_STIFFNESS_2 = np.array([[0.35, 0.08], [0.08, 0.2]])
_DRIFT_VELOCITY = np.array([0.08, -0.04])


def truth_claims(world_id=DEFAULT_WORLD_ID, physics_version=CURRENT_PHYSICS_VERSION):
    """Private declaration answers, used only after an accepted session ends."""
    world_id, _ = validate_world_physics(world_id, physics_version)
    return {'dynamics_order': 2, 'hidden_matter': False,
            'time_dependence': world_id == 'world_7'}


def body_positions_at(t, world_id=DEFAULT_WORLD_ID, physics_version=CURRENT_PHYSICS_VERSION):
    """Private exact body positions at scalar or one-dimensional absolute times.

    The observation service adds noise to these values; they are not an RPC.
    A scalar returns (n_bodies, 2), an array returns (n_times, n_bodies, 2).
    """
    world_id, _ = validate_world_physics(world_id, physics_version)
    times = np.asarray(t, dtype=float)
    if times.ndim > 1 or not np.isfinite(times).all():
        raise ValueError('Body reference times must be finite scalars or one-dimensional arrays')
    positions = np.broadcast_to(_BODIES, times.shape + _BODIES.shape).copy()
    if world_id == 'world_6':
        positions += times[..., None, None] * _DRIFT_VELOCITY
    return positions


def body_initial_states(world_id=DEFAULT_WORLD_ID, physics_version=CURRENT_PHYSICS_VERSION):
    """The exact initial conditions explicitly permitted by the v4 protocol."""
    positions = body_positions_at(0.0, world_id, physics_version)
    velocity = _DRIFT_VELOCITY if world_id == 'world_6' else np.zeros(2)
    return [{'body_id': f'b{index + 1}', 'position': position.tolist(), 'velocity': velocity.tolist()}
            for index, position in enumerate(positions)]


def acceleration(world_id, _t, state, properties=None, physics_version=CURRENT_PHYSICS_VERSION):
    """Simulator-only force dispatch; the selected ID is fixed per process."""
    world_id, physics_version = validate_world_physics(world_id, physics_version)
    r = np.asarray(state[:2], dtype=float)
    v = np.asarray(state[2:], dtype=float)
    offsets = body_positions_at(_t, world_id, physics_version) - r
    if world_id in ("world_1", "world_6"):
        return 0.1 * np.sum(offsets, axis=0)
    if world_id == "world_7":
        return (1.0 + 0.5 * math.sin(0.6 * _t)) * 0.1 * np.sum(offsets, axis=0)
    if world_id == "world_4":
        denominators = (np.sum(offsets**2, axis=1) + 0.64)**1.5
        return np.sum(0.8 * offsets / denominators[:, None], axis=0)
    if physics_version == LEGACY_PHYSICS_VERSION:
        d = r - _CENTER
        if world_id == "world_2":
            return -_STIFFNESS_2 @ d
        if world_id == "world_3":
            return -0.2 * d - 0.015 * d**3
        return -0.3 * d + 0.45 * np.array([v[1], -v[0]])
    if world_id == "world_2":
        # Each source has the same fixed anisotropic response. The divisor is
        # a coefficient choice, not normalization by a changing source count.
        return np.sum(offsets @ (_STIFFNESS_2 / 3).T, axis=0)
    squared_distances = np.sum(offsets**2, axis=1)
    if world_id == "world_3":
        return np.sum((0.06 + 0.004 * squared_distances)[:, None] * offsets, axis=0)
    perpendicular_velocity = np.array([v[1], -v[0]])
    coupling, softening = (1.2, 4.0) if physics_version == 'v2' else (1.0, 1.0)
    return np.sum(0.1 * offsets + (coupling / (squared_distances + softening))[:, None]
                  * perpendicular_velocity, axis=0)


def make_dynamics(world_id, properties=None, physics_version=CURRENT_PHYSICS_VERSION):
    """Close over the validated selection, without exposing a reconfiguration API."""
    selected, version = validate_world_physics(world_id, physics_version)

    def dynamics(t, state):
        return np.concatenate((state[2:], acceleration(selected, t, state, properties, version)))

    return dynamics


def _oracle_input(r0, v0, times, t0):
    r0, v0, times = np.asarray(r0, dtype=float), np.asarray(v0, dtype=float), np.asarray(times, dtype=float)
    if r0.shape != (2,) or v0.shape != (2,) or not np.isfinite(r0).all() or not np.isfinite(v0).all():
        raise ValueError("Truth reference requires finite two-component initial conditions")
    if times.ndim != 1 or len(times) == 0 or not np.isfinite(times).all() or np.any(np.diff(times) <= 0):
        raise ValueError("Truth reference requires nonempty finite strictly increasing times")
    t0 = float(times[0]) if t0 is None else float(t0)
    if not math.isfinite(t0) or times[0] < t0:
        raise ValueError("Truth reference times must not precede finite t0")
    return r0, v0, times, t0


def analytic_trajectory(r0, v0, times, t0=None):
    """Backward-compatible analytic reference for world_1 only."""
    r0, v0, times, t0 = _oracle_input(r0, v0, times, t0)
    phase = math.sqrt(0.3) * (times - t0)
    offset = r0 - _CENTER
    r = _CENTER + np.cos(phase)[:, None] * offset + np.sin(phase)[:, None] * v0 / math.sqrt(0.3)
    v = -math.sqrt(0.3) * np.sin(phase)[:, None] * offset + np.cos(phase)[:, None] * v0
    return np.column_stack((r, v))


def truth_reference(world_id=DEFAULT_WORLD_ID, physics_version=CURRENT_PHYSICS_VERSION):
    """Developer/evaluator metadata. Never include it in a runtime mission."""
    world_id, physics_version = validate_world_physics(world_id, physics_version)
    if world_id == "world_1":
        return "analytic trajectory; no observation noise"
    if world_id == "world_2" or (world_id == "world_5" and physics_version == LEGACY_PHYSICS_VERSION):
        return "independent matrix-exponential solution; no observation noise"
    return "independent Radau numerical reference (rtol=1e-12, atol=1e-14), not analytic; no observation noise"


def truth_trajectory(r0, v0, times, t0=None, world_id=DEFAULT_WORLD_ID, properties=None,
                     physics_version=CURRENT_PHYSICS_VERSION):
    """Return [x,y,vx,vy] at absolute times for post-session evaluation only.

    world_1 uses an analytic expression; world_2 and legacy world_5 use matrix
    exponentials constructed independently of force dispatch. Other worlds use
    a separate RHS with Radau, rather than the simulator's DOP853 method.
    Properties are accepted for interface compatibility; these worlds do not
    couple to probe properties. No observation noise is applied.
    """
    world_id, physics_version = validate_world_physics(world_id, physics_version)
    r0, v0, times, t0 = _oracle_input(r0, v0, times, t0)
    if properties is not None and not isinstance(properties, dict):
        raise ValueError("properties must be an object or None")
    if world_id == "world_1":
        return analytic_trajectory(r0, v0, times, t0)
    if world_id == "world_2" or (world_id == "world_5" and physics_version == LEGACY_PHYSICS_VERSION):
        matrix = np.zeros((4, 4))
        matrix[:2, 2:] = np.eye(2)
        if world_id == "world_2":
            matrix[2:, :2] = [[-0.35, -0.08], [-0.08, -0.2]]
        else:
            matrix[2:, :2] = [[-0.3, 0.0], [0.0, -0.3]]
            matrix[2:, 2:] = [[0.0, 0.45], [-0.45, 0.0]]
        initial = np.r_[r0 - [0.0, 1.0], v0]
        states = np.asarray([expm(matrix * (t - t0)) @ initial for t in times])
        states[:, :2] += [0.0, 1.0]
        return states

    initial = np.r_[r0, v0]
    if times[-1] == t0:
        return initial[None, :]

    # Keep reference implementations separate from the simulated RHS so that
    # method comparisons also catch dispatch and component/sign mistakes.
    def reference_rhs(_t, state):
        x, y, vx, vy = state
        if world_id == "world_6":
            # Independently reduce the three translating sources to their
            # moving centroid; do not reuse the simulated source positions.
            ax = -0.3 * x + 0.024 * _t
            ay = 0.3 - 0.3 * y - 0.012 * _t
        elif world_id == "world_7":
            strength = 0.3 + 0.15 * math.sin(0.6 * _t)
            ax = -strength * x
            ay = strength * (1.0 - y)
        elif world_id == "world_3" and physics_version == LEGACY_PHYSICS_VERSION:
            ax = -0.2 * x - 0.015 * x*x*x
            shifted_y = y - 1.0
            ay = -0.2 * shifted_y - 0.015 * shifted_y*shifted_y*shifted_y
        else:
            ax, ay = 0.0, 0.0
            for bx, by in ((-2.0, 0.0), (2.0, 0.0), (0.0, 3.0)):
                dx, dy = bx - x, by - y
                squared_distance = dx*dx + dy*dy
                if world_id == "world_3":
                    ax += 0.06 * dx + 0.004 * squared_distance * dx
                    ay += 0.06 * dy + 0.004 * squared_distance * dy
                elif world_id == "world_4":
                    scale = 0.8 / math.pow(squared_distance + 0.64, 1.5)
                    ax += scale * dx
                    ay += scale * dy
                elif physics_version == 'v2':
                    ax += 0.1 * dx + 1.2 * vy / (squared_distance + 4)
                    ay += 0.1 * dy - 1.2 * vx / (squared_distance + 4)
                else:
                    ax += 0.1 * dx + vy / (squared_distance + 1)
                    ay += 0.1 * dy - vx / (squared_distance + 1)
        return [vx, vy, ax, ay]

    result = solve_ivp(reference_rhs, (t0, float(times[-1])), initial, t_eval=times,
                       method="Radau", rtol=1e-12, atol=1e-14)
    if not result.success or result.y.shape != (4, len(times)) or not np.isfinite(result.y).all():
        raise ValueError("Independent numerical truth reference failed")
    return result.y.T
