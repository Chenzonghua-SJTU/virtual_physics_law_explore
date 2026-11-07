"""Synthetic-only PySR API/export/timing smoke test; never an Agent world score.

Generate analytic observations here, send only training probes to the loopback
service, and evaluate frozen returned coefficients on separate analytic states.
No simulator, world catalog, historical run, parameter fitting or submission is
used. First/repeat client calls to a warmed service are NOT cold-start timings.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import http.client
import json
import math
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

import numpy as np

from shore_agent.expressions import Expression
from shore_agent.symbolic_service import SymbolicServiceError, search_remote


def _stamp():
    return datetime.now(timezone.utc).isoformat()


def _endpoint(endpoint):
    try:
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1")
                or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment
                or parsed.path not in ("", "/", "/search") or parsed.port is None):
            raise ValueError("invalid endpoint")
        return "::1" if parsed.hostname == "::1" else "127.0.0.1", parsed.port
    except (TypeError, ValueError) as exc:
        raise ValueError("A loopback HTTP endpoint with an explicit port is required") from exc


def read_health(endpoint):
    host, port = _endpoint(endpoint)
    connection = http.client.HTTPConnection(host, port, timeout=3)
    try:
        connection.request("GET", "/health")
        response = connection.getresponse()
        raw = response.read(65537)
        if response.status != 200 or len(raw) > 65536:
            return {"status": "unavailable", "error": "health_unavailable"}
        data = json.loads(raw)
        # Do not guess versions from local Python or from expected installation.
        keys = {"status", "pool_size", "ready", "busy", "warming", "failed",
                "pysr_version", "julia_version", "symbolic_regression_version", "backend_version"}
        return {key: value for key, value in data.items() if key in keys}
    except (OSError, ValueError, http.client.HTTPException):
        return {"status": "unavailable", "error": "health_unavailable"}
    finally:
        connection.close()


def analytic_probe(kind, parameters, probe_id, initial, span, n_samples):
    r0 = np.asarray(initial["r0"], dtype=float)
    v0 = np.asarray(initial["v0"], dtype=float)
    t0 = float(initial["t0"])
    tau = np.linspace(0, span, n_samples)[:, None]
    times = t0 + tau[:, 0]
    if kind == "constant_acceleration":
        value = np.asarray(parameters["acceleration"], dtype=float)
        positions = r0 + tau * v0 + .5 * tau**2 * value
        velocities = v0 + tau * value
        acceleration = np.broadcast_to(value, velocities.shape).copy()
    elif kind == "linear_damping":
        rate = np.asarray(parameters["damping_rates"], dtype=float)
        decay = np.exp(-tau * rate)
        velocities = v0 * decay
        positions = r0 + v0 * (1 - decay) / rate
        acceleration = -rate * velocities
    else:
        raise ValueError("Unknown analytic synthetic case")
    observed = {"probe_id": probe_id, "initial_conditions": {"r0": r0.tolist(), "v0": v0.tolist(),
                 "t0": t0, "properties": {}}, "times": times.tolist(),
                "r_obs": positions.tolist(), "v_obs": velocities.tolist(),
                "a_est_times": times[1:-1].tolist(),
                "a_est": np.gradient(velocities, times, axis=0)[1:-1].tolist(),
                "a_est_method": "synthetic_velocity_difference"}
    return observed, acceleration.tolist()


def build_cases():
    # Prespecified independent toy parameters, not selected from public worlds.
    specifications = [
        ("constant_acceleration", {"acceleration": [.371, -.829]},
         {"ax": "a1", "ay": "a2"}),
        ("linear_damping", {"damping_rates": [.613, 1.127]},
         {"ax": "-k1*vx", "ay": "-k2*vy"}),
    ]
    train_initial = [
        {"r0": [1.37, -.82], "v0": [.41, -.73], "t0": 0},
        {"r0": [-.64, 1.18], "v0": [-.87, .56], "t0": .3},
        {"r0": [.29, .47], "v0": [1.03, .22], "t0": .6},
    ]
    heldout_initial = [
        {"r0": [-2.41, 1.93], "v0": [-1.31, .87], "t0": 2.3},
        {"r0": [3.2, -1.41], "v0": [.22, -1.79], "t0": 3.7},
    ]
    cases = []
    for kind, parameters, formula in specifications:
        case = {"case_id": kind, "analytic_parameters": parameters, "analytic_formula": formula,
                "noise": False, "training_probes": [], "heldout_probes": [],
                "training_analytic_acceleration": {}, "heldout_analytic_acceleration": {}}
        for group, initial_states, span, samples in (("training", train_initial, 1.2, 41),
                                                     ("heldout", heldout_initial, 1.7, 51)):
            for index, initial in enumerate(initial_states):
                pid = f"synthetic_{kind}_{group}_{index + 1}"
                probe, target = analytic_probe(kind, parameters, pid, initial, span, samples)
                case[group + "_probes"].append(probe)
                case[group + "_analytic_acceleration"][pid] = target
        cases.append(case)
    return cases


def _error_summary(predictions, targets):
    per_probe = [np.mean((prediction - target)**2, axis=0)
                 for prediction, target in zip(predictions, targets)]
    mse = np.mean(per_probe, axis=0)
    return {"mse_by_axis": mse.tolist(), "vector_mse": float(sum(mse)),
            "vector_rmse": float(np.sqrt(sum(mse))), "weighting": "equal_per_trajectory"}


def evaluate_candidate(candidate, case):
    """Evaluate frozen initial coefficients; never refit on training or holdout."""
    result = {"law_spec": copy.deepcopy(candidate.get("law_spec")),
              "parameter_spec": copy.deepcopy(candidate.get("parameter_spec")),
              "component_sources": candidate.get("component_sources"),
              "search_reported_acceleration_mse": candidate.get("acceleration_search_mse"),
              "search_loss_scope": "observed_velocity_difference_targets_only",
              "parameters_frozen": True, "trajectory_rollout_tested": False}
    try:
        expression = Expression(candidate["law_spec"], candidate["parameter_spec"])
        coefficients = {item["name"]: item["initial"] for item in candidate["parameter_spec"]}
        for group in ("training", "heldout"):
            predictions, analytic, difference_predictions, difference_targets = [], [], [], []
            for probe in case[group + "_probes"]:
                prediction = np.asarray([expression.acceleration(t, r, v, [], {}, coefficients)
                    for t, r, v in zip(probe["times"], probe["r_obs"], probe["v_obs"])])
                predictions.append(prediction)
                analytic.append(np.asarray(case[group + "_analytic_acceleration"][probe["probe_id"]]))
                difference_predictions.append(prediction[1:-1])
                difference_targets.append(np.asarray(probe["a_est"]))
            result[group + "_analytic_acceleration_error"] = _error_summary(predictions, analytic)
            result[group + "_difference_acceleration_error"] = _error_summary(difference_predictions, difference_targets)
        result["evaluation_status"] = "evaluated"
    except (ValueError, TypeError, KeyError, OverflowError):
        result.update(evaluation_status="invalid_or_out_of_domain", error="candidate_evaluation_failed")
    return result


def _write(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_smoke(output, endpoint="http://127.0.0.1:8890", budget=25, seed=1729, repeats=2,
              search_fn=search_remote, health_fn=read_health):
    _endpoint(endpoint)
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not 0 < budget <= 120:
        raise ValueError("Budget must be in (0, 120] seconds")
    if type(seed) is not int or not 0 <= seed < 2**31 - 1 or type(repeats) is not int or not 1 <= repeats <= 5:
        raise ValueError("Invalid seed or repeat count")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write("{}\n")  # Reserve new output before any service request.
    cases = build_cases()
    report = {"kind": "synthetic_symbolic_regression_smoke", "status": "running", "started_at": _stamp(),
              "is_agent_six_world_score": False, "selects_public_world_configuration": False,
              "endpoint": endpoint, "time_budget_seconds_per_call": budget, "random_state": seed,
              "repeats_per_case": repeats, "cases": cases, "runs": [],
              "backend_versions": None, "backend_version_source": "not_reported_by_service_health",
              "warnings": [
                  "Only synthetic analytic observations are used; no world catalog or simulator truth is read.",
                  "Search receives training probes only. Heldout initial states and times remain outside the search request.",
                  "Search loss uses observed-velocity differences; analytic acceleration errors are separately labelled.",
                  "Frozen candidates are not parameter-refitted, trajectory-integrated, submitted, or scored as Agent experiments.",
                  "First/repeat requests use an already warmed service and may hit different workers; these are not cold-start timings.",
                  "These two toy families cannot establish generalization to the nine hidden universes or exact equation recovery.",
              ], "source_sha256": {str(Path(__file__).name): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    _write(output, report)
    started = time.monotonic()
    for case in cases:
        for trial in range(repeats):
            health = health_fn(endpoint)
            versions = {k: v for k, v in health.items() if k in
                        ("pysr_version", "julia_version", "symbolic_regression_version", "backend_version")}
            if versions:
                report["backend_versions"] = versions
                report["backend_version_source"] = "service_health"
            row = {"case_id": case["case_id"], "trial": trial + 1, "random_state": seed,
                   "started_at": _stamp(), "service_health_before": health,
                   "client_call_order": len(report["runs"]) + 1, "time_budget_seconds": budget}
            before = time.monotonic()
            try:
                response = search_fn(case["training_probes"], budget, endpoint, random_state=seed)
                row["client_call_seconds"] = time.monotonic() - before
                row["search_status"] = response.get("status")
                row["search_axes_completed"] = response.get("search_axes_completed", [])
                row["response"] = response
                row["candidate_checks"] = [evaluate_candidate(c, case) for c in response.get("candidates", [])]
                row["status"] = "response_received"
            except SymbolicServiceError as exc:
                row.update(status="service_error", error_code=exc.code,
                           client_call_seconds=time.monotonic() - before)
            row["row_wall_seconds_including_candidate_checks"] = time.monotonic() - before
            report["runs"].append(row)
            report["elapsed_seconds"] = time.monotonic() - started
            _write(output, report)
            print(json.dumps({k: row[k] for k in ("case_id", "trial", "status", "client_call_seconds")}), flush=True)
    report.update(status="completed_with_service_errors" if any(r["status"] == "service_error" for r in report["runs"])
                  else "completed", finished_at=_stamp(), elapsed_seconds=time.monotonic() - started)
    _write(output, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New JSON file; existing paths are never overwritten")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8890")
    parser.add_argument("--budget", type=float, default=25)
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args()
    try:
        run_smoke(args.output, args.endpoint, args.budget, args.seed, args.repeats)
    except (ValueError, FileExistsError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
