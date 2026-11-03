"""Developer-only, post-submission evaluation. Never exposed as an Agent tool.

Usage: python evaluate.py --run-dir runs/example --seed 1871 --n-probes 20
Truth is imported only after an accepted, ended submission is located.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import numpy as np

from shore_agent.numerics import errors_for_rollouts, rollout
from shore_scoring import finite_nonnegative, problem_score
from shore_worlds import (DEFAULT_WORLD_ID, LEGACY_PHYSICS_VERSION,
                          validate_physics_version, validate_world_id, validate_world_physics)


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _accepted_law(run_dir):
    accepted = []
    for path in (run_dir / "records" / "submission").glob("*.json"):
        submission = _read(path)
        if submission.get("status") == "accepted" and submission.get("session_ended") is True:
            accepted.append(submission)
    if len(accepted) != 1:
        raise ValueError("Independent evaluation requires exactly one accepted submission with session_ended=true")
    submission = accepted[0]
    law_id = submission.get("law_id", "")
    if not isinstance(law_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", law_id):
        raise ValueError("Invalid submitted law identifier")
    law = _read(run_dir / "records" / "law" / (law_id + ".json"))
    if law.get("law_id") != law_id:
        raise ValueError("Submitted law record does not match its identifier")
    return submission, law


def _evaluation_environment(run_dir):
    config_path = run_dir / "config.json"
    env = _read(config_path).get("environment", {}) if config_path.exists() else {}
    if not isinstance(env, dict):
        raise ValueError("Invalid environment configuration")
    world_id = validate_world_id(env.get("world_id", DEFAULT_WORLD_ID))
    configured_version = (validate_physics_version(env["physics_version"])
                          if "physics_version" in env else None)
    physics_version = configured_version or LEGACY_PHYSICS_VERSION
    mission_path = run_dir / "mission.json"
    if mission_path.exists():
        mission = _read(mission_path)
        task = mission.get("task", {})
        if not isinstance(task, dict):
            raise ValueError("Invalid saved mission")
        mission_world = validate_world_id(task.get("world_id", DEFAULT_WORLD_ID))
        if mission_world != world_id:
            raise ValueError("Mission/config world identity mismatch; evaluation refused")
        mission_version = validate_physics_version(task.get("physics_version", LEGACY_PHYSICS_VERSION))
        if configured_version is not None and configured_version != mission_version:
            raise ValueError("Mission/config physics version mismatch; evaluation refused")
        physics_version = mission_version
    # Missing version tags belong to archived v1 sessions, never today's default.
    # Return a copy rather than altering the saved historical configuration.
    env = dict(env, physics_version=physics_version)
    validate_world_physics(world_id, physics_version)
    return env, world_id


def _matching_submission(value, submission):
    if not isinstance(value, dict):
        return False
    return all(value.get(key) in (None, submission.get(key)) for key in ('submission_id', 'law_id'))


def _energy_used(run_dir, submission):
    """Read an explicit final budget; missing records are not free experiments."""
    def energy(budget):
        remaining = budget.get('energy_remaining') if isinstance(budget, dict) else None
        return 100.0 - remaining if finite_nonnegative(remaining) and remaining <= 100 else None

    result_path = run_dir / 'result.json'
    if result_path.exists():
        try:
            result = _read(result_path)
            if isinstance(result, dict) and _matching_submission(result.get('submission') or {}, submission):
                used = energy(result.get('budget'))
                if used is not None:
                    return used, 'result.json:budget.energy_remaining'
        except (OSError, ValueError, TypeError):
            pass
    for filename in ('tools.jsonl', 'events.jsonl'):
        path = run_dir / filename
        if not path.exists():
            continue
        try:
            lines = path.read_text(encoding='utf-8').splitlines()
        except (OSError, UnicodeError):
            continue
        for line in reversed(lines):
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if not isinstance(item, dict):
                continue
            if filename == 'tools.jsonl':
                result = item.get('result')
                data = result.get('data') if isinstance(result, dict) else None
                if (item.get('tool') != 'submit' or not isinstance(data, dict)
                        or result.get('ok') is not True or data.get('status') != 'accepted'
                        or data.get('session_ended') is not True or not _matching_submission(data, submission)):
                    continue
                budget = result.get('budget')
            else:
                if (item.get('event') != 'session_finished' or item.get('status') != 'submitted'
                        or not _matching_submission(item.get('submission') or {}, submission)):
                    continue
                budget = item.get('budget')
            used = energy(budget)
            if used is not None:
                return used, filename + ':final_budget.energy_remaining'
    return None, None


def _reference_variance(positions):
    values = np.concatenate([np.asarray(p, dtype=float) for p in positions], axis=0)
    if values.ndim != 2 or values.shape[1] != 2 or not len(values) or not np.isfinite(values).all():
        raise ValueError('Invalid reference position samples')
    with np.errstate(over='raise', invalid='raise'):
        return float(np.mean(np.sum((values - np.mean(values, axis=0)) ** 2, axis=1)))


def _score(run_dir, submission, world_id, physics_version, *, mse, variance, count,
           candidate_failed=False, truth_failed=False, unavailable_reason=None,
           source='fresh_independent_evaluation'):
    # This private import is downstream of accepted-submission and version checks.
    from shore_sim.worlds import truth_claims
    used, energy_source = _energy_used(run_dir, submission)
    score = problem_score(mse, variance, submission.get('claims'), truth_claims(world_id, physics_version),
                          used, count, candidate_failed=candidate_failed, truth_failed=truth_failed,
                          unavailable_reason=unavailable_reason)
    score.update(source=source, energy_source=energy_source)
    return score


def evaluate_run(run_dir, seed=1871, n_probes=20):
    run_dir = Path(run_dir)
    submission, law = _accepted_law(run_dir)
    if type(n_probes) is not int or not 1 <= n_probes <= 100:
        raise ValueError("n_probes must be between 1 and 100")
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    env, world_id = _evaluation_environment(run_dir)
    physics_version = env["physics_version"]
    # Deliberate truth boundary: this import is never reachable by a runtime tool.
    # Identity checks precede oracle access; legacy archives default to world_1.
    from shore_sim.simulator import truth_trajectory, truth_reference
    if physics_version == 'v4':
        from shore_sim.worlds import body_positions_at

        def visible_input(t):
            # Once the session has ended, visible positions are prescribed input
            # state to the frozen acceleration law, not force-law parameters or
            # observations returned to the research Agent.
            return body_positions_at(t, world_id=world_id, physics_version=physics_version)

        body_input_protocol = 'instantaneous_visible_state'
    else:
        visible_input = law['known_bodies']
        body_input_protocol = 'frozen_static_observed_positions'
    position_limit = float(env.get("position_limit", 5))
    velocity_limit = float(env.get("velocity_limit", 3))
    time_max = float(env.get("time_max", 30))
    if not all(np.isfinite(v) and v > 0 for v in (position_limit, velocity_limit, time_max)):
        raise ValueError("Invalid evaluation range in local environment configuration")
    rng = np.random.default_rng(seed)
    probes, predictions, failures, initial_conditions = [], [], [], []
    reference_positions = []
    for index in range(n_probes):
        # The hidden test set is fixed by configuration and seed, never changed
        # in response to the Agent's chosen training/validation experiments.
        r0 = rng.uniform(-position_limit, position_limit, 2).tolist()
        v0 = rng.uniform(-velocity_limit, velocity_limit, 2).tolist()
        # All times stay on the observation grid; evaluation uses an independent oracle,
        # independently of whether the training observations contained noise.
        t0 = round(int(rng.integers(0, max(1, int(time_max / 3 / 0.005)))) * 0.005, 10)
        horizon = min(20.0, time_max - t0)
        n_samples = min(50, int(horizon / 0.005) + 1)
        dt = max(1, int(horizon / max(1, n_samples - 1) / 0.005)) * 0.005
        times = np.round(t0 + np.arange(n_samples) * dt, 10)
        properties = {"mass": float(rng.uniform(0.5, 2)), "charge": float(rng.uniform(-1, 1))}
        initial = {"r0": r0, "v0": v0, "t0": t0, "dt": dt, "properties": properties}
        initial_conditions.append({"probe_id": f"hidden_{index + 1:03d}", "n_samples": n_samples, **initial})
        try:
            truth = truth_trajectory(r0, v0, times, t0=t0, world_id=world_id,
                                     properties=properties, physics_version=physics_version)
        except (ValueError, OverflowError, FloatingPointError) as exc:
            failures.append({"probe_id": f"hidden_{index + 1:03d}", "stage": "truth_reference",
                             "reason": str(exc)})
            continue
        reference_positions.append(truth[:, :2])
        probe = {"probe_id": f"hidden_{index + 1:03d}", "initial_conditions": initial,
                 "times": times.tolist(), "r_obs": truth[:, :2].tolist(), "v_obs": truth[:, 2:].tolist()}
        try:
            prediction = rollout(law["law_spec"], law["fitted_parameters"], probe, visible_input)
            probes.append(probe)
            predictions.append(prediction)
        except (ValueError, OverflowError, FloatingPointError) as exc:
            failures.append({"probe_id": probe["probe_id"], "stage": "candidate_rollout", "reason": str(exc)})
    metrics = errors_for_rollouts(probes, predictions) if probes else None
    truth_failed = any(item['stage'] == 'truth_reference' for item in failures)
    variance = None
    if not truth_failed:
        try:
            variance = _reference_variance(reference_positions)
        except (ValueError, OverflowError, FloatingPointError):
            truth_failed = True
    mse = None
    if not failures:
        # Vector-position MSE across every test sample, exactly the PDF metric.
        with np.errstate(over='ignore', invalid='ignore'):
            mse = float(np.mean(np.concatenate([
                np.sum((np.asarray(pred['r_pred']) - np.asarray(probe['r_obs'])) ** 2, axis=1)
                for probe, pred in zip(probes, predictions)])))
    score = _score(run_dir, submission, world_id, physics_version, mse=mse, variance=variance,
                   count=n_probes, candidate_failed=any(item['stage'] == 'candidate_rollout' for item in failures),
                   truth_failed=truth_failed)
    return {
        "evaluation_kind": "independent_post_session_hidden_initial_conditions",
        "local_only": True, "official_score": False, "world_id": world_id,
        "physics_version": physics_version,
        "body_input_protocol": body_input_protocol,
        "body_input_note": (
            "Local v4 adapter supplies exact instantaneous visible positions to the frozen law during "
            "post-session rollout. Training/validation tools use acquired observations only; this "
            "evaluation state is never returned to the active Agent. The official bodies encoding "
            "is not specified by the problem PDF and remains an integration boundary."
            if physics_version == 'v4' else
            "Historical evaluation retains this law's frozen acquired static body positions."),
        "truth_reference": truth_reference(world_id, physics_version=physics_version),
        "submission_id": submission["submission_id"], "law_id": law["law_id"],
        "claims": submission["claims"], "seed": seed, "n_trajectories": n_probes,
        "n_successful": len(predictions), "complete": not failures,
        "overall": metrics["overall"] if metrics and not failures else None,
        "successful_subset_overall": metrics["overall"] if metrics else None,
        "per_probe": metrics["per_probe"] if metrics else [], "failures": failures,
        "initial_conditions": initial_conditions,
        "test_set_policy": "fixed_seed_and_configuration_independent_of_exploration_history",
        "score": score,
        "interpretation": "PDF-formula score on local test data, not an official competition score. Prediction equivalence does not uniquely identify source structure; no pass threshold is imposed.",
    }


def score_existing_evaluation(run_dir, evaluation, reference_cache=None):
    """Score an archive without rerunning its candidate, fitting, or model.

    The saved position MSE is reused. Only reference positions for the exact
    archived initial conditions and sample times are regenerated to obtain V.
    No files or supplied evaluation dictionaries are modified by this function.
    """
    run_dir = Path(run_dir)
    source = 'archived_position_mse_and_reconstructed_reference_variance'
    try:
        submission, _law = _accepted_law(run_dir)
        env, world_id = _evaluation_environment(run_dir)
    except (OSError, ValueError, KeyError, TypeError):
        result = problem_score(None, None, {}, {}, None, 0,
                               unavailable_reason='accepted_archive_unavailable')
        result.update(source=source, energy_source=None)
        return result
    version = env['physics_version']
    count = evaluation.get('n_trajectories') if isinstance(evaluation, dict) else None

    def unavailable(reason, *, mse=None):
        return _score(run_dir, submission, world_id, version, mse=mse, variance=None,
                      count=count, unavailable_reason=reason, source=source)

    if not isinstance(evaluation, dict):
        return unavailable('evaluation_unavailable')
    expected_identity = {'world_id': world_id, 'physics_version': version,
                         'law_id': submission['law_id'], 'submission_id': submission['submission_id']}
    for key, expected in expected_identity.items():
        if key in evaluation and evaluation[key] != expected:
            return unavailable('evaluation_identity_mismatch')
    if 'claims' in evaluation and evaluation['claims'] != submission.get('claims'):
        return unavailable('evaluation_claims_mismatch')
    failures = evaluation.get('failures', [])
    if not isinstance(failures, list) or any(not isinstance(item, dict) for item in failures):
        return unavailable('invalid_evaluation_failures')
    if any(item.get('stage') == 'truth_reference' for item in failures):
        return unavailable('truth_reference_failed')
    if type(count) is not int or count < 20:
        return unavailable('fewer_than_20_test_trajectories')
    if failures:
        if any(item.get('stage') != 'candidate_rollout' for item in failures):
            return unavailable('unknown_evaluation_failure')
        return _score(run_dir, submission, world_id, version, mse=None, variance=None, count=count,
                      candidate_failed=True, source=source)
    if (evaluation.get('complete') is not True or type(evaluation.get('n_successful')) is not int
            or evaluation['n_successful'] != count):
        return unavailable('incomplete_evaluation')
    initial_conditions, per_probe = evaluation.get('initial_conditions'), evaluation.get('per_probe')
    if (not isinstance(initial_conditions, list) or len(initial_conditions) != count
            or not isinstance(per_probe, list) or len(per_probe) != count):
        return unavailable('archived_test_samples_unavailable')
    metrics = {}
    for item in per_probe:
        if not isinstance(item, dict) or not isinstance(item.get('probe_id'), str) or item['probe_id'] in metrics:
            return unavailable('invalid_archived_test_samples')
        metrics[item['probe_id']] = item
    specifications, sample_counts, per_mse, identifiers = [], [], [], set()
    for initial in initial_conditions:
        if not isinstance(initial, dict) or initial.get('probe_id') not in metrics or initial.get('probe_id') in identifiers:
            return unavailable('invalid_archived_test_samples')
        identifier = initial['probe_id']
        identifiers.add(identifier)
        metric = metrics[identifier]
        samples = initial.get('n_samples', metric.get('n_samples'))
        if (type(samples) is not int or samples < 1 or samples > 50
                or (metric.get('n_samples') is not None and metric['n_samples'] != samples)):
            return unavailable('invalid_archived_test_samples')
        t0, dt = initial.get('t0'), initial.get('dt')
        if not finite_nonnegative(t0) or not finite_nonnegative(dt) or dt <= 0:
            return unavailable('invalid_archived_test_samples')
        try:
            r0, v0 = np.asarray(initial['r0'], dtype=float), np.asarray(initial['v0'], dtype=float)
        except (ValueError, TypeError, KeyError):
            return unavailable('invalid_archived_test_samples')
        if r0.shape != (2,) or v0.shape != (2,) or not np.isfinite(r0).all() or not np.isfinite(v0).all():
            return unavailable('invalid_archived_test_samples')
        times = np.round(float(t0) + np.arange(samples) * float(dt), 10)
        if np.any(np.abs(times / 0.005 - np.round(times / 0.005)) > 1e-7):
            return unavailable('invalid_archived_test_samples')
        properties = initial.get('properties', {})
        if not isinstance(properties, dict):
            return unavailable('invalid_archived_test_samples')
        specifications.append({'r0': r0.tolist(), 'v0': v0.tolist(), 't0': float(t0),
                               'times': times.tolist(), 'properties': properties})
        sample_counts.append(samples)
        per_mse.append(metric.get('position_mse'))
    overall = evaluation.get('overall')
    overall_mse = overall.get('position_mse') if isinstance(overall, dict) else None
    if not finite_nonnegative(overall_mse):
        return unavailable('invalid_position_statistics')
    if all(finite_nonnegative(value) for value in per_mse):
        # Old overall MSE was trajectory-weighted. Match PDF sample weighting if
        # an archive has differing trajectory lengths, using saved per-row MSE.
        if not math.isclose(float(np.mean(per_mse)), overall_mse, rel_tol=1e-9, abs_tol=1e-15):
            return unavailable('inconsistent_archived_position_mse')
        mse = float(np.average(per_mse, weights=sample_counts))
    elif len(set(sample_counts)) == 1:
        mse = float(overall_mse)
    else:
        return unavailable('archived_per_probe_mse_unavailable')
    try:
        cache_key = (world_id, version, json.dumps(specifications, sort_keys=True, allow_nan=False))
    except (ValueError, TypeError):
        return unavailable('invalid_archived_test_samples', mse=mse)
    if reference_cache is not None and cache_key in reference_cache:
        variance = reference_cache[cache_key]
    else:
        from shore_sim.simulator import truth_trajectory
        positions = []
        try:
            for spec in specifications:
                trajectory = truth_trajectory(spec['r0'], spec['v0'], np.asarray(spec['times']),
                                               t0=spec['t0'], world_id=world_id,
                                               physics_version=version, properties=spec['properties'])
                positions.append(trajectory[:, :2])
            variance = _reference_variance(positions)
        except (ValueError, TypeError, KeyError, OverflowError, FloatingPointError):
            return unavailable('truth_reference_failed', mse=mse)
        if reference_cache is not None:
            reference_cache[cache_key] = variance
    return _score(run_dir, submission, world_id, version, mse=mse, variance=variance,
                  count=count, source=source)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--seed", type=int, default=1871)
    parser.add_argument("--n-probes", type=int, default=20)
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        result = evaluate_run(args.run_dir, args.seed, args.n_probes)
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(2, f"Evaluation refused or failed: {exc}\n")
    output = Path(args.output) if args.output else Path(args.run_dir) / "evaluation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"complete": result["complete"], "overall": result["overall"],
                      "n_successful": result["n_successful"], "n_trajectories": result["n_trajectories"],
                      "output": str(output.resolve())}, ensure_ascii=False, indent=2))
    if not result["complete"]:
        parser.exit(1)


if __name__ == "__main__":
    main()
