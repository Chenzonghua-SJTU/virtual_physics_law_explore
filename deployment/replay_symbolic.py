"""Offline SR replay on explicitly named acquired observations; never a new mission.

This diagnostic reads probe/search records only. Held-out records are never sent
to the search service or parameter fitter. Its results are not Agent scores and
must not replace the original run. Run separately from timed Agent experiments.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shore_agent.expressions import Expression
from shore_agent.numerics import errors_for_rollouts, fit, rollout
from shore_agent.symbolic_service import search_remote


def _read_record(run, kind, record_id):
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", record_id):
        raise ValueError("Invalid record ID")
    file = run / "records" / kind / (record_id + ".json")
    if file.is_symlink() or file.resolve().parent != (run / "records" / kind).resolve():
        raise ValueError("Record path is outside the requested run")
    raw = file.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _candidate_check(candidate, probes, parameters, rollout_seconds):
    """Evaluate supplied coefficients, without fitting or choosing on held-out data."""
    expression = Expression(candidate["law_spec"], candidate["parameter_spec"])
    initial_failures, derivative_mses, predictions, failures = [], [], [], []
    for probe in probes:
        initial = probe["initial_conditions"]
        properties = initial.get("properties", {})
        try:
            expression.acceleration(float(initial.get("t0", probe["times"][0])),
                                    initial["r0"], initial["v0"], [], properties, parameters)
        except (ValueError, OverflowError) as exc:
            initial_failures.append({"probe_id": probe["probe_id"], "code": getattr(exc, "code", type(exc).__name__)})
        try:
            times = np.asarray(probe["times"], dtype=float)
            states, velocities = np.asarray(probe["r_obs"]), np.asarray(probe["v_obs"])
            observed_a = np.gradient(velocities, times, axis=0)[1:-1]
            predicted_a = np.asarray([expression.acceleration(t, r, v, [], properties, parameters)
                                     for t, r, v in zip(times[1:-1], states[1:-1], velocities[1:-1])])
            mse = np.mean((predicted_a - observed_a) ** 2, axis=0)
            if not np.isfinite(mse).all():
                raise ValueError("nonfinite_derivative_residual")
            derivative_mses.append(mse)
        except (ValueError, OverflowError) as exc:
            failures.append({"probe_id": probe["probe_id"], "stage": "derivative",
                             "code": getattr(exc, "code", type(exc).__name__)})
        try:
            predictions.append(rollout(candidate["law_spec"], parameters, probe, [],
                                       timeout_seconds=rollout_seconds))
        except (ValueError, OverflowError) as exc:
            failures.append({"probe_id": probe["probe_id"], "stage": "rollout",
                             "code": getattr(exc, "code", type(exc).__name__)})
    complete = len(predictions) == len(probes) and bool(probes)
    return {"probe_ids": [p["probe_id"] for p in probes], "initial_domain_failures": initial_failures,
            "all_rollouts_completed": complete,
            "acceleration_mse_by_axis": np.mean(derivative_mses, axis=0).tolist()
            if probes and len(derivative_mses) == len(probes) else None,
            "trajectory_errors": errors_for_rollouts(probes, predictions) if complete else None,
            "failures": failures}


def _review_candidates(candidates, train, heldout, fit_seconds, rollout_seconds):
    rows = []
    for index, candidate in enumerate(candidates):
        row = {"index": index, "law_spec": candidate["law_spec"],
               "parameter_spec": candidate["parameter_spec"],
               "parameter_count": len(candidate["parameter_spec"]),
               "component_sources": candidate.get("component_sources"),
               "selection_role": candidate.get("selection_role")}
        initial = {p["name"]: p["initial"] for p in candidate["parameter_spec"]}
        row["initial_training"] = _candidate_check(candidate, train, initial, rollout_seconds)
        row["initial_heldout"] = _candidate_check(candidate, heldout, initial, rollout_seconds)
        if fit_seconds:
            started = time.monotonic()
            fitted = fit(candidate["law_spec"], candidate["parameter_spec"], train, [],
                         timeout_seconds=fit_seconds, max_nfev=40)
            row["training_only_refit"] = {k: v for k, v in fitted.items() if k != "rollouts"}
            row["refit_wall_seconds"] = time.monotonic() - started
            if fitted.get("errors") is not None:
                row["refitted_heldout"] = _candidate_check(candidate, heldout, fitted["fitted_parameters"], rollout_seconds)
        rows.append(row)
    return rows


def replay(run_directory, search_id, output, *, heldout_probe_ids=(), budget=30,
           endpoint="http://127.0.0.1:8890", random_state=42, fit_seconds=0, rollout_seconds=1,
           search_function=search_remote):
    run = Path(run_directory).resolve()
    output = Path(output).resolve()
    if output.exists() or output.is_relative_to(run):
        raise ValueError("Use a fresh diagnostic output outside the original run")
    if budget not in (30, 40, 60) or not 0 <= fit_seconds <= 25 or not 0 < rollout_seconds <= 4:
        raise ValueError("Invalid diagnostic time budgets")
    original, search_hash = _read_record(run, "symbolic_search", search_id)
    train_ids = original["used_probe_ids"]
    if len(set(train_ids)) != len(train_ids) or not train_ids:
        raise ValueError("Invalid archived discovery probe IDs")
    heldout_probe_ids = list(heldout_probe_ids)
    if len(set(heldout_probe_ids)) != len(heldout_probe_ids) or set(train_ids) & set(heldout_probe_ids):
        raise ValueError("Held-out probes must be distinct and disjoint from the original discovery set")
    records, hashes = {}, {"symbolic_search/" + search_id: search_hash}
    for probe_id in [*train_ids, *heldout_probe_ids]:
        probe, digest = _read_record(run, "probe", probe_id)
        if probe.get("probe_id") != probe_id:
            raise ValueError("Record ID mismatch")
        records[probe_id] = probe
        hashes["probe/" + probe_id] = digest
    train = [records[i] for i in train_ids]
    heldout = [records[i] for i in heldout_probe_ids]
    report = {"kind": "offline_symbolic_replay_not_agent_result", "source_run_id": run.name,
              "source_search_id": search_id, "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "train_probe_ids": train_ids, "heldout_probe_ids": heldout_probe_ids,
              "source_record_sha256": hashes,
              "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
                  ("shore_agent/symbolic_regression.py", "shore_agent/symbolic_service.py",
                   "shore_agent/expressions.py", "shore_agent/numerics.py", "deployment/replay_symbolic.py")},
              "scope": "No mission, new observations, energy use, model calls, hidden truth, or independent scoring. "
                       "Held-out records were not sent to search or fit; diagnostic selection must not be credited to the Agent.",
              "request": {"time_budget_seconds": budget, "random_state": random_state,
                          "endpoint": endpoint, "per_candidate_refit_seconds": fit_seconds,
                          "per_probe_rollout_seconds": rollout_seconds},
              "old_search": original, "status": "started"}
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive reservation before any CPU work prevents replacing another replay.
    with output.open("x") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    started = time.monotonic()
    try:
        report["new_search"] = search_function(train, budget, endpoint=endpoint, random_state=random_state)
        report["search_client_seconds"] = time.monotonic() - started
        for label in ("old", "new"):
            report[label + "_candidate_diagnostics"] = _review_candidates(
                report[label + "_search"]["candidates"], train, heldout, fit_seconds, rollout_seconds)
        report["status"] = "completed"
    except Exception as exc:
        report["status"] = "failed"
        report["failure"] = {"code": getattr(exc, "code", type(exc).__name__)}
        raise
    finally:
        report["offline_total_seconds"] = time.monotonic() - started
        immutable = all(_read_record(run, *key.split("/"))[1] == digest for key, digest in hashes.items())
        report["source_records_unchanged"] = immutable
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        temporary.replace(output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--search-id", required=True)
    parser.add_argument("--heldout-probe-ids", nargs="*", default=[])
    parser.add_argument("--budget", type=int, choices=(30, 40, 60), default=30)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8890")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--fit-seconds", type=float, default=0)
    parser.add_argument("--rollout-seconds", type=float, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = replay(args.run_dir, args.search_id, args.output,
                    heldout_probe_ids=args.heldout_probe_ids, budget=args.budget,
                    endpoint=args.endpoint, random_state=args.seed, fit_seconds=args.fit_seconds,
                    rollout_seconds=args.rollout_seconds)
    print(json.dumps({"status": result["status"], "output": str(args.output),
                      "search_seconds": result["search_client_seconds"],
                      "new_candidates": len(result["new_search"]["candidates"]),
                      "source_records_unchanged": result["source_records_unchanged"]}))


if __name__ == "__main__":
    main()
