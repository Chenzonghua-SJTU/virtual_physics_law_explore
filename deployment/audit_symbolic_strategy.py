#!/usr/bin/env python3
"""Read saved Agent logs and write an explicit, new SR adoption audit.

No model, search, simulator, evaluation or production Agent module is imported.
Formula matching is deliberately conservative: AST equality, parameter renaming
and partial-axis matches are distinct. Unmatched algebraic rewrites need review.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from deployment.summarize_e6_e7 import ACTIVE_STATUSES, token_metrics


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


class Archive:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.hashes, self.warnings, self.invalid = {}, [], set()

    def read(self, path, *, lines=False, default=None):
        path = Path(path)
        if not path.is_file():
            self.warnings.append(f"Missing: {path.relative_to(self.root)}")
            return ([] if lines else {}) if default is None else default
        data = path.read_bytes()
        self.hashes[str(path.relative_to(self.root))] = hashlib.sha256(data).hexdigest()
        try:
            return [json.loads(line) for line in data.splitlines() if line.strip()] if lines else json.loads(data)
        except (ValueError, UnicodeError):
            self.invalid.add(path)
            self.warnings.append(f"Incomplete or invalid JSON: {path.relative_to(self.root)}")
            return ([] if lines else {}) if default is None else default

    def unchanged(self):
        return all((self.root/path).is_file() and hashlib.sha256((self.root/path).read_bytes()).hexdigest() == digest
                   for path, digest in self.hashes.items())


def formula_signature(value, axes=("ax", "ay"), *, rename=False):
    """Compare syntax only; never evaluate or import a candidate expression."""
    if not isinstance(value, dict):
        return None
    names = {p.get("name") for p in value.get("parameter_spec", []) if isinstance(p, dict)}
    mapping = {}

    class Rename(ast.NodeTransformer):
        def visit_Name(self, node):
            if node.id in names:
                mapping.setdefault(node.id, f"parameter_{len(mapping)}")
                return ast.copy_location(ast.Name(id=mapping[node.id], ctx=node.ctx), node)
            return node

    try:
        trees = []
        for axis in axes:
            tree = ast.parse(value["law_spec"][axis], mode="eval")
            if rename:
                tree = Rename().visit(tree)
            trees.append(ast.dump(tree, include_attributes=False))
        return canonical(trees)
    except (KeyError, TypeError, ValueError, SyntaxError):
        return None


def match_formula(candidate, fit, *, component=None):
    axes = (component,) if component else ("ax", "ay")
    exact, other = formula_signature(candidate, axes), formula_signature(fit, axes)
    if exact is None or other is None:
        return None
    if exact == other:
        same_parameters = canonical(candidate.get("parameter_spec", [])) == canonical(fit.get("parameter_spec", []))
        return "exact_formula_and_parameters" if same_parameters else "same_formula_changed_parameter_spec"
    if formula_signature(candidate, axes, rename=True) == formula_signature(fit, axes, rename=True):
        return "same_structure_parameter_renaming_or_initial_changes"
    return None


def candidate_list(search):
    rows = []
    for index, candidate in enumerate(search.get("candidates", [])):
        if isinstance(candidate, dict):
            rows.append((f"joint:{index}", None, candidate))
    for axis, candidates in search.get("axis_candidates", {}).items():
        if axis in ("ax", "ay"):
            for index, candidate in enumerate(candidates):
                if isinstance(candidate, dict):
                    rows.append((f"{axis}:{index}", axis, candidate))
    return rows


def source_class(candidate, component):
    origins = [candidate.get("origin", "unknown")] if component else candidate.get("component_sources", [])
    if not origins:
        return "unspecified"
    return "all_"+str(origins[0]) if len(set(origins)) == 1 else "mixed"


def probe_summary(probe):
    initial = probe.get("initial_conditions", {})
    times = [x for x in probe.get("times", []) if finite(x)]
    steps = [b-a for a, b in zip(times, times[1:])]
    return {"probe_id": probe.get("probe_id"), "r0": initial.get("r0"), "v0": initial.get("v0"),
            "t0": initial.get("t0"), "properties": initial.get("properties", {}),
            "n_samples": len(times), "absolute_time_range": [min(times), max(times)] if times else None,
            "duration": max(times)-min(times) if times else None,
            "dt_range": [min(steps), max(steps)] if steps else None}


def coverage(probes, ids):
    selected = {key: probes[key] for key in ids if key in probes}
    rows = [probe_summary(p) for p in selected.values()]
    coordinates = [row["r0"] for row in rows if isinstance(row["r0"], list) and len(row["r0"]) == 2]
    times = [row["t0"] for row in rows if finite(row["t0"])]
    attributes = sorted({key for row in rows for key in row["properties"]})
    values = {key: sorted({row["properties"][key] for row in rows if finite(row["properties"].get(key))})
              for key in attributes}
    time_controls, property_controls = [], []
    for index, a in enumerate(rows):
        for b in rows[index+1:]:
            same_state = a["r0"] == b["r0"] and a["v0"] == b["v0"]
            if same_state and a["properties"] == b["properties"] and a["t0"] != b["t0"]:
                time_controls.append([a["probe_id"], b["probe_id"]])
            changed = [key for key in attributes if a["properties"].get(key) != b["properties"].get(key)]
            if same_state and a["t0"] == b["t0"] and len(changed) == 1:
                property_controls.append({"probe_ids": [a["probe_id"], b["probe_id"]], "property": changed[0]})
    return {"probe_ids": list(selected), "missing_probe_ids": [key for key in ids if key not in probes],
            "probe_count": len(rows), "sample_count": sum(row["n_samples"] for row in rows),
            "launch_times": sorted(set(times)), "property_values": values,
            "initial_coordinate_signs": {axis: {"negative": any(r[i] < 0 for r in coordinates),
                                                "positive": any(r[i] > 0 for r in coordinates)}
                                         for i, axis in enumerate(("x", "y"))},
            "off_axis_initial_probes": sum(r[0] != 0 and r[1] != 0 for r in coordinates),
            "distinct_initial_velocities": len({canonical(row["v0"]) for row in rows}),
            "same_complete_initial_state_delayed_controls": time_controls,
            "single_property_controls": property_controls, "probes": rows}


def context_delivery(model_messages, final_messages, search_id, search):
    if search_id is None:
        return {"source": None, "all_formula_parameter_specs_preserved": None}
    expected = {key: (candidate.get("law_spec"), candidate.get("parameter_spec"))
                for key, _, candidate in candidate_list(search)}
    contexts = [(f"model_messages.jsonl:{i}", row.get("call_number"), row.get("messages", []))
                for i, row in enumerate(model_messages, 1)]
    contexts.append(("messages.json", None, final_messages))
    for path, call, messages in contexts:
        for index, message in enumerate(messages):
            if not isinstance(message, dict) or message.get("role") != "tool":
                continue
            try:
                payload = json.loads(message.get("content", ""))
            except (ValueError, TypeError):
                continue
            data = payload.get("data", {}) if isinstance(payload, dict) else {}
            if not isinstance(data, dict):
                continue
            if data.get("search_id") != search_id:
                continue
            visible = {key: (candidate.get("law_spec"), candidate.get("parameter_spec"))
                       for key, _, candidate in candidate_list(data)}
            return {"source": path, "message_index": index, "call_number": call,
                    "tool_call_id": message.get("tool_call_id"), "visible_candidate_count": len(visible),
                    "all_formula_parameter_specs_preserved": canonical(expected) == canonical(visible)}
    return {"source": None, "all_formula_parameter_specs_preserved": None}


def relative_validation_errors(validation, probes):
    """Observation-only diagnostic; not an independent score or pass threshold."""
    result = []
    for row in validation.get("errors", {}).get("per_probe", []):
        probe = probes.get(row.get("probe_id"), {})
        positions = probe.get("r_obs", [])
        initial = probe.get("initial_conditions", {}).get("r0")
        error = row.get("position_rmse")
        if not initial or not positions or not finite(error):
            continue
        try:
            scale = math.sqrt(sum(sum((p[i]-initial[i])**2 for i in range(2)) for p in positions)/len(positions))
        except (TypeError, ValueError, IndexError):
            continue
        result.append({"probe_id": row.get("probe_id"), "position_rmse": error,
                       "observed_displacement_rms": scale,
                       "relative_rmse": error/scale if scale > 0 else None})
    return result


def analyze_world(archive, row):
    run_id = row.get("run_id")
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,199}", run_id):
        raise ValueError("Invalid or absent run_id in summary")
    directory = archive.root/"runs"/run_id
    tools = archive.read(directory/"tools.jsonl", lines=True)
    events = archive.read(directory/"events.jsonl", lines=True)
    model_events = archive.read(directory/"model_events.jsonl", lines=True)
    model_messages = archive.read(directory/"model_messages.jsonl", lines=True)
    final_messages = archive.read(directory/"messages.json", default=[])
    result = archive.read(directory/"result.json")
    records = {kind: {path.stem: archive.read(path) for path in sorted((directory/"records"/kind).glob("*.json"))}
               for kind in ("probe", "symbolic_search", "law", "validation", "submission")}
    probes, laws = records["probe"], records["law"]
    final_id = (row.get("law") or {}).get("law_id")
    if final_id is None:
        accepted = [r for r in records["submission"].values() if r.get("status") == "accepted"]
        final_id = accepted[-1].get("law_id") if accepted else None
    fits, searches, failures, validations = [], [], [], []
    for index, tool in enumerate(tools, 1):
        name, args, response = tool.get("tool"), tool.get("arguments", {}), tool.get("result", {})
        data = response.get("data") or {}
        if response.get("ok") is False:
            error = response.get("error") or {}
            failures.append({"source": f"tools.jsonl:{index}", "tool": name,
                             "code": error.get("code") if isinstance(error, dict) else str(error)[:160],
                             "budget": response.get("budget")})
        if name == "fit_law_and_rollout":
            law_id = data.get("law_id")
            law = laws.get(law_id, data)
            fits.append({"tool_line": index, "law_id": law_id, "ok": response.get("ok"),
                         "law_spec": args.get("law_spec"), "parameter_spec": args.get("parameter_spec", []),
                         "fitted_parameters": law.get("fitted_parameters"), "train_probe_ids": args.get("train_probe_ids", []),
                         "fit_status": law.get("fit_status"), "errors": law.get("errors", {}).get("overall"),
                         "submitted_same_law_id": final_id is not None and law_id == final_id,
                         "candidate_links": []})
        elif name == "symbolic_regression":
            sid = data.get("search_id")
            if sid is None and isinstance(response.get("error"), dict):
                match = re.search(r"analyses/(sr_[a-f0-9]+)\.json", str(response["error"].get("message", "")))
                if match and match[1] in records["symbolic_search"]:
                    sid = match[1]
            raw = records["symbolic_search"].get(sid, data)
            searches.append({"search_id": sid, "tool_line": index, "ok": response.get("ok"),
                             "requested_seconds": args.get("time_budget_seconds"),
                             "tool_seconds": tool.get("elapsed_seconds"), "arguments": args,
                             "budget_after": response.get("budget"), "raw": raw})
        elif name == "validate_law":
            vid = data.get("validation_id")
            validation = records["validation"].get(vid, data)
            discovered = set().union(*(set(s["raw"].get("used_probe_ids", [])) for s in searches))
            train = set(laws.get(args.get("law_id"), {}).get("train_probe_ids", []))
            test = set(args.get("test_probe_ids", []))
            validations.append({"tool_line": index, "validation_id": vid, "law_id": args.get("law_id"),
                                "ok": response.get("ok"), "test_probe_ids": sorted(test),
                                "training_or_sr_discovery_overlap": sorted(test & (train | discovered)),
                                "errors": validation.get("errors", {}).get("overall"),
                                "observation_relative_errors": relative_validation_errors(validation, probes),
                                "submitted_same_law_id": final_id is not None and args.get("law_id") == final_id})
    for search in searches:
        raw = search.pop("raw")
        search.update({key: raw.get(key) for key in (
            "status", "backend", "elapsed_seconds", "used_probe_ids", "feature_names", "samples_per_probe",
            "search_stages", "search_axes_completed", "axis_search_seconds", "search_configuration",
            "candidate_selection", "basis_diagnostics", "geometric_features", "projection_diagnostics",
            "data_quality", "stop_reason", "transport_audit_omitted_rows", "rejection_counts",
            "requested_time_budget_seconds", "effective_time_budget_seconds", "wall_seconds", "input_coverage",
            "outcome", "status_meaning")})
        search["axis_equation_counts"] = {axis: len(rows) for axis, rows in raw.get("axis_equations", {}).items()}
        selected = raw.get("used_probe_ids", search["arguments"].get("train_probe_ids", []))
        search["training_coverage"] = coverage(probes, selected)
        search["context_delivery"] = context_delivery(model_messages, final_messages, search["search_id"], raw)
        search["candidates"] = []
        for reference, component, candidate in candidate_list(raw):
            item = {key: candidate.get(key) for key in (
                "law_spec", "parameter_spec", "parameter_count", "component_sources", "origin", "source",
                "selection_role", "loss", "loss_by_axis", "complexity", "parameter_sharing", "initial_domain_check",
                "short_rollout_check", "prediction_accuracy_status", "joint_fit_ready", "acceleration_search_mse",
                "acceleration_search_mse_by_axis", "normalized_acceleration_search_loss") if key in candidate}
            item.update(reference=reference, component=component, source_class=source_class(candidate, component), fit_matches=[])
            for fit in fits:
                if fit["tool_line"] <= search["tool_line"]:
                    continue
                match = match_formula(candidate, fit, component=component)
                axes = ([component] if match else []) if component else [
                    axis for axis in ("ax", "ay") if match_formula(candidate, fit, component=axis)]
                if match is None and not axes:
                    continue
                relation = match if match else "partial_axis_structure_only"
                link = {"search_id": search["search_id"], "candidate_reference": reference,
                        "relation": relation, "component": component, "matching_axes": axes,
                        "source_class": item["source_class"]}
                fit["candidate_links"].append(link)
                item["fit_matches"].append({"tool_line": fit["tool_line"], "law_id": fit["law_id"],
                                           "relation": relation, "matching_axes": axes, "ok": fit["ok"],
                                           "submitted_same_law_id": fit["submitted_same_law_id"]})
            search["candidates"].append(item)
    reviews = []
    for index, event in enumerate(events, 1):
        if event.get("event") in ("symbolic_experiment_review", "symbolic_submission_review"):
            review = event.get("review", event.get("evidence", {}))
            reviews.append({"source": f"events.jsonl:{index}", "event": event["event"],
                            "reasons": event.get("reasons", review.get("reasons")),
                            "reviewed_probe_ids": review.get("reviewed_probe_ids"),
                            "budget": event.get("budget", review.get("budget")),
                            "recommended_search_seconds": review.get("recommended_search_seconds"),
                            "validation_warnings": review.get("validation_warnings")})
    metric_state = (1 if directory/"model_events.jsonl" in archive.invalid else
                    0 if (directory/"model_events.jsonl").is_file() else None)
    metrics = token_metrics(row, model_events, metric_state, row.get("status") not in ACTIVE_STATUSES)
    checks = {}
    for summary_key, logged_key in (("calls", "calls"), ("completion_tokens", "reported_completion_tokens"),
                                    ("average_output_tokens_per_call", "average_output_tokens_per_call"),
                                    ("max_call_output_tokens", "max_call_output_tokens"),
                                    ("model_elapsed_seconds", "model_seconds_from_logged_requests")):
        a, b = row.get(summary_key), metrics.get(logged_key)
        checks[summary_key] = math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-8) if finite(a) and finite(b) else None
    final_law = laws.get(final_id, {})
    unresolved = []
    if final_law.get("fit_status") in ("not_converged", "failed", "error"):
        unresolved.append({"kind": "submitted_fit_not_converged", "law_id": final_id,
                           "fit_status": final_law.get("fit_status")})
    for validation in validations:
        flagged = [item for item in validation["observation_relative_errors"]
                   if finite(item["relative_rmse"]) and item["relative_rmse"] >= .2]
        if validation["submitted_same_law_id"] and flagged:
            unresolved.append({"kind": "submitted_law_has_large_observation_relative_validation_residual",
                               "law_id": final_id, "validation_id": validation["validation_id"],
                               "tool_line": validation["tool_line"], "diagnostics": flagged,
                               "interpretation": "Observed evidence only; not proof the Agent ignored it or an official threshold."})
    return {"world_id": row.get("world_id"), "run_id": run_id, "status": row.get("status"), "reason": row.get("reason"),
            "evaluation_complete": row.get("evaluation_complete"), "score": (row.get("evaluation_score") or {}).get("total"),
            "timing_from_summary": {key: row.get(key) for key in (
                "exploration_seconds", "evaluation_seconds", "wall_seconds_including_evaluation", "model_elapsed_seconds",
                "symbolic_search_seconds", "exploration_deadline_met")},
            "tokens_from_summary": {key: row.get(key) for key in (
                "calls", "completion_tokens", "average_output_tokens_per_call", "max_call_output_tokens",
                "requests_with_reported_usage", "requests_without_reported_usage", "output_cap_compliant")},
            "token_log_audit": metrics, "summary_api_cross_checks": checks,
            "energy_used": row.get("energy_used"), "energy_budget": row.get("energy_budget"),
            "result_status": result.get("status"), "all_acquired_data": coverage(probes, list(probes)),
            "actual_symbolic_tool_calls": len(searches), "archived_symbolic_records": len(records["symbolic_search"]),
            "searches": searches, "fits": fits, "validations": validations, "reviews": reviews,
            "failures": failures, "model_failures": [{key: event.get(key) for key in
                ("call_number", "error", "elapsed_seconds", "usage_warning", "finish_reason")}
                for event in model_events if event.get("event") == "request" and event.get("error")],
            "tool_failure_events": [{"source": f"events.jsonl:{i}", "tool": event.get("name"),
                                     "code": event.get("result", {}).get("error", {}).get("code"),
                                     "budget": event.get("result", {}).get("budget")}
                                    for i, event in enumerate(events, 1) if event.get("event") == "tool_finished"
                                    and event.get("result", {}).get("ok") is False],
            "accepted_law_id": final_id,
            "accepted_law": {key: final_law.get(key) for key in ("law_spec", "fitted_parameters", "train_probe_ids", "fit_status")},
            "unresolved_evidence_at_submission": unresolved}


def build_audit(root, summary_path):
    archive = Archive(root)
    summary = archive.read(summary_path)
    worlds = [analyze_world(archive, row) for row in summary.get("worlds", [])]
    return {"kind": "saved_agent_symbolic_strategy_audit", "created_at": datetime.now(timezone.utc).isoformat(),
            "batch_id": summary.get("experiment_id"), "summary_status": summary.get("status"),
            "source_sha256": summary.get("source_sha256"),
            "scope": "Saved summary, tools, events, messages and public records only. No model/search/simulator/evaluation calls.",
            "definitions": {
                "adoption": "Exact syntax plus parameter specifications, renamed structure and partial-axis reuse are distinct; structure matches do not prove causality.",
                "unmatched_rewrite": "Algebraically equivalent rewrites not captured by syntax require manual review; never automatically counted as SR adoption.",
                "validation": "Training and all prior SR discovery probes are not independent validation. Candidate rollout checks are discovery diagnostics.",
                "tokens": "User-facing values come directly from summary. API-log verification never invents a full average when usage is missing.",
                "stages": "search_stages records actual backend execution; search_configuration describes plans only."},
            "worlds": worlds, "totals": {
                "world_count": len(worlds), "completed_evaluations": sum(w["evaluation_complete"] is True for w in worlds),
                "completed_scores_at_least_90": sum(w["evaluation_complete"] is True and finite(w["score"]) and w["score"] >= 90 for w in worlds),
                "actual_symbolic_tool_calls": sum(w["actual_symbolic_tool_calls"] for w in worlds),
                "review_events": dict(Counter(r["event"] for w in worlds for r in w["reviews"]))},
            "input_sha256": archive.hashes, "inputs_unchanged": archive.unchanged(), "warnings": archive.warnings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--batch")
    source.add_argument("--summary", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.batch and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,199}", args.batch):
        parser.error("invalid batch identifier")
    path = args.summary or root/"experiments"/"E5"/args.batch/"summary.json"
    path = path.resolve()
    if not path.is_relative_to(root) or not path.is_file():
        parser.error("summary must be an existing file inside --root")
    output = args.output.resolve()
    if output.is_relative_to(root/"runs"):
        parser.error("audit outputs must not be written into run archives")
    report = build_audit(root, path)
    if not report["inputs_unchanged"]:
        parser.error("input logs changed during audit; retry after synchronization completes")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"output": str(output), **report["totals"], "warnings": len(report["warnings"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
