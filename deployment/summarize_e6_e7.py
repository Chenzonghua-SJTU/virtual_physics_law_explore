#!/usr/bin/env python3
"""Read E6/E7 summaries and logs; write one explicitly selected analysis JSON.

No model, simulator, evaluation, or archive-mutating code is imported. Exact
candidate adoption is identifiable only when a later fit has the same formula
AST and named parameter specification; unmatched cases remain unknown.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

WORLD_IDS = tuple(f"world_{i}" for i in range(1, 7))
ACTIVE_STATUSES = {"queued", "starting", "running", "stopping", "evaluating"}
TOOL_CLASSES = {
    "observe_body": "observations", "insert_probe": "observations",
    "fit_law_and_rollout": "fitting", "validate_law": "validation",
    "symbolic_regression": "symbolic_regression", "analyze_residual": "analysis",
    "read_file": "file_reads", "list_files": "file_reads",
    "save_draft": "submission", "submit": "submission",
}


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def count(value):
    return value if type(value) is int and value >= 0 else None


def read_json(path, warnings):
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("expected object")
        return data
    except (OSError, ValueError):
        warnings.append(f"Unreadable JSON object: {path.name}")
        return {}


def read_lines(path, warnings):
    rows, malformed = [], 0
    if not path.is_file():
        return rows, None
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError("expected object")
                    rows.append(row)
                except ValueError:
                    malformed += 1
    except OSError:
        warnings.append(f"Unreadable log: {path.name}")
        return [], None
    if malformed:
        warnings.append(f"{path.name}: {malformed} malformed or incomplete lines")
    return rows, malformed


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def law_signature(value):
    """Ignore expression whitespace/key order, not names, values, or algebra."""
    if not isinstance(value, dict):
        return None
    try:
        law, params = value["law_spec"], value["parameter_spec"]
        if set(law) != {"ax", "ay"} or not isinstance(params, list):
            return None
        trees = [ast.dump(ast.parse(law[key], mode="eval"), include_attributes=False)
                 for key in ("ax", "ay")]
        return canonical([trees, sorted(params, key=lambda p: p["name"])])
    except (KeyError, TypeError, SyntaxError, ValueError):
        return None


def token_metrics(row, events, malformed, terminal):
    requests = [e for e in events if e.get("event") == "request"]
    started = [e for e in events if e.get("event") == "request_started"]
    declared = count(row.get("calls"))
    if declared is None:
        declared = count((row.get("model_usage") or {}).get("calls"))
    call_numbers = [count(e.get("call_number")) for e in requests + started]
    expected = max([declared or 0, len(requests), len(started)] + [n for n in call_numbers if n is not None])
    outputs = [count((e.get("usage") or {}).get("completion_tokens")) for e in requests]
    known = [n for n in outputs if n is not None]
    missing = max(0, expected - len(known))
    complete = (malformed == 0 and expected > 0 and len(requests) == expected
                and len(known) == expected)
    average = sum(known) / expected if complete and terminal else None
    source = "model_events.jsonl" if malformed is not None else "unavailable"
    maximum = max(known) if known else None
    total = sum(known) if known else None
    # A copied summary can be used only with an explicit, internally consistent
    # complete-usage declaration. Never invent an average from partial usage.
    if malformed is None:
        with_usage = count(row.get("requests_with_reported_usage"))
        without_usage = count(row.get("requests_without_reported_usage"))
        declared_total = count(row.get("completion_tokens"))
        declared_average = number(row.get("average_output_tokens_per_call"))
        complete = (terminal and expected > 0 and with_usage == expected and without_usage == 0
                    and declared_total is not None and declared_average is not None
                    and math.isclose(declared_average, declared_total / expected, rel_tol=1e-9, abs_tol=1e-9))
        if complete:
            average, total = declared_average, declared_total
            maximum = count(row.get("max_call_output_tokens"))
            missing, source = 0, "summary_explicit_complete_usage_not_log_verified"
        else:
            missing = without_usage
    elapsed = [number(e.get("elapsed_seconds")) for e in requests]
    model_seconds = number(row.get("model_elapsed_seconds"))
    if model_seconds is None:
        model_seconds = number((row.get("model_usage") or {}).get("elapsed_seconds"))
    if model_seconds is None and any(n is not None for n in elapsed):
        model_seconds = sum(n for n in elapsed if n is not None)
    request_limits = [count(e.get("max_tokens")) for e in requests]
    return {
        "calls": expected or declared, "finalized_request_records": len(requests),
        "started_request_records": len(started), "reported_usage_requests": len(known) if malformed is not None else count(row.get("requests_with_reported_usage")),
        "requests_without_reported_usage": missing, "usage_complete": complete,
        "usage_log_verified": complete and malformed == 0,
        "usage_source": source, "reported_completion_tokens": total,
        "average_output_tokens_per_call": average,
        "max_call_output_tokens": maximum,
        "max_output_is_complete": complete and maximum is not None,
        "observed_calls_above_4096": sum(n > 4096 for n in known) if known else None,
        "observed_requests_above_4096": sum(n > 4096 for n in request_limits if n is not None) if requests else None,
        "model_elapsed_seconds": model_seconds,
        "model_seconds_from_logged_requests": sum(n for n in elapsed if n is not None) if requests else None,
        "model_time_log_complete": bool(expected and malformed == 0 and len(elapsed) == expected and all(n is not None for n in elapsed)),
    }


def tools_metrics(rows, log_state, directory, warnings):
    groups, signatures = {}, Counter()
    previous, streak, longest = None, 0, 0
    searches, candidates, fits = [], [], []
    for index, row in enumerate(rows):
        name = row.get("tool", "unknown")
        args, result = row.get("arguments") or {}, row.get("result") or {}
        signature = canonical([name, args])
        signatures[signature] += 1
        streak = streak + 1 if signature == previous else 1
        longest, previous = max(longest, streak), signature
        bucket = TOOL_CLASSES.get(name, "other")
        for key in ("class:" + bucket, "tool:" + name):
            entry = groups.setdefault(key, {"calls": 0, "ok_calls": 0, "reported_seconds": 0.0, "missing_duration_calls": 0})
            entry["calls"] += 1
            entry["ok_calls"] += result.get("ok") is True
            seconds = number(row.get("elapsed_seconds"))
            if seconds is None:
                entry["missing_duration_calls"] += 1
            else:
                entry["reported_seconds"] += seconds
        if name == "fit_law_and_rollout":
            data = result.get("data") or {}
            fits.append({"tool_call_index": index + 1, "signature": law_signature(args),
                         "ok": result.get("ok") is True, "law_id": data.get("law_id"),
                         "fit_status": data.get("fit_status")})
        if name != "symbolic_regression":
            continue
        data = result.get("data") or {}
        search_id = data.get("search_id")
        if isinstance(search_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", search_id):
            archived = read_json(directory / "records" / "symbolic_search" / (search_id + ".json"), warnings)
            if archived:
                data = archived
        entries = data.get("candidates")
        listed = entries if isinstance(entries, list) else []
        search = {"search_id": search_id, "tool_call_index": index + 1,
                  "ok": result.get("ok") is True, "status": data.get("status", "tool_error"),
                  "error_code": (result.get("error") or {}).get("code"),
                  "axes_completed": data.get("search_axes_completed"),
                  "candidates_returned": len(entries) if isinstance(entries, list) else None,
                  "tool_elapsed_seconds": number(row.get("elapsed_seconds")),
                  "runtime_wall_seconds": number(data.get("wall_seconds")),
                  "service_elapsed_seconds": number(data.get("elapsed_seconds")),
                  "search_elapsed_seconds": number(data.get("search_elapsed_seconds")),
                  "requested_time_budget_seconds": number(data.get("requested_time_budget_seconds", args.get("time_budget_seconds"))),
                  "effective_time_budget_seconds": number(data.get("effective_time_budget_seconds")),
                  "body_positions_included": data.get("body_positions_included"),
                  "identifiable_fit_calls": [], "candidate_fit_adoption": "unknown" if listed else "no_candidates"}
        searches.append(search)
        for candidate_index, candidate in enumerate(listed):
            signature = law_signature(candidate)
            if signature is not None:
                candidates.append((search, candidate_index, signature))
    for search, candidate_index, signature in candidates:
        for fit in fits:
            if fit["tool_call_index"] > search["tool_call_index"] and fit["signature"] == signature:
                search["identifiable_fit_calls"].append({k: v for k, v in fit.items() if k != "signature"} | {"candidate_index": candidate_index})
                search["candidate_fit_adoption"] = "identified_exact_match"
    repeated = sorted(((key, n) for key, n in signatures.items() if n > 1), key=lambda item: -item[1])
    return {
        "log_available": log_state is not None, "malformed_log_lines": log_state,
        "calls": len(rows), "time_by_class": {k[6:]: v for k, v in groups.items() if k.startswith("class:")},
        "time_by_tool": {k[5:]: v for k, v in groups.items() if k.startswith("tool:")},
        "repeat_definition": "Same tool and JSON arguments (sorted object keys); additional occurrences beyond the first, across the complete tool log.",
        "repeated_call_occurrences": sum(n - 1 for _, n in repeated),
        "repeated_signatures": len(repeated), "longest_identical_call_streak": longest,
        "most_repeated": [{"tool": json.loads(key)[0], "argument_signature_sha256": hashlib.sha256(key.encode()).hexdigest(), "occurrences": n} for key, n in repeated[:10]],
        "symbolic_regression": {"calls": len(searches), "statuses": dict(Counter(s["status"] for s in searches)),
            "reported_tool_seconds": sum(s["tool_elapsed_seconds"] or 0 for s in searches),
            "searches_with_identifiable_fit": sum(s["candidate_fit_adoption"] == "identified_exact_match" for s in searches),
            "adoption_note": "Only later exact formula-AST and named parameter-spec matches are identifiable. Algebraic rewrites, renamed parameters, or changed initial values remain unknown; fit success is reported separately.",
            "searches": searches},
    }


def analyze_world(root, row):
    warnings = []
    run_id = row.get("run_id")
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,199}", run_id):
        warnings.append("Missing or invalid run_id; logs unavailable")
        directory = root / "runs" / "__missing_analysis_input__"
    else:
        directory = root / "runs" / run_id
    if not directory.is_dir():
        warnings.append("Run directory unavailable; summary-only metrics may be incomplete")
    events, event_state = read_lines(directory / "model_events.jsonl", warnings)
    tool_rows, tool_state = read_lines(directory / "tools.jsonl", warnings)
    tokens = token_metrics(row, events, event_state, row.get("status") not in ACTIVE_STATUSES)
    score = number((row.get("evaluation_score") or {}).get("total"))
    complete = row.get("evaluation_complete") is True
    return {"world_id": row.get("world_id"), "run_id": run_id, "status": row.get("status"),
            "reason": row.get("reason"), "evaluation_complete": complete, "raw_score": score,
            "complete_and_raw_score_at_least_90": complete and score is not None and score >= 90,
            "score_for_batch_mean_incomplete_as_zero": score if complete and score is not None else 0,
            "exploration_seconds": number(row.get("exploration_seconds")),
            "evaluation_seconds": number(row.get("evaluation_seconds")),
            "total_seconds": number(row.get("wall_seconds_including_evaluation")),
            "exploration_deadline_met": row.get("exploration_deadline_met"),
            "energy_used": number(row.get("energy_used")), "energy_budget": number(row.get("energy_budget")),
            "model": tokens, "tools": tools_metrics(tool_rows, tool_state, directory, warnings), "warnings": warnings}


def analyze(root):
    root = Path(root).resolve()
    folder = root / "experiments" / "E5"
    warnings, batches = [], []
    selection_path = folder / "e6-selection.json"
    selection = read_json(selection_path, warnings)
    for path in sorted([*folder.glob("e6-*/summary.json"), *folder.glob("e7-*/summary.json")]):
        summary = read_json(path, warnings)
        if not summary:
            continue
        configuration = summary.get("configuration") or {}
        model = configuration.get("model") or {}
        indexed = {r.get("world_id"): r for r in summary.get("worlds", []) if isinstance(r, dict)}
        worlds = [analyze_world(root, indexed.get(world, {"world_id": world, "run_id": (summary.get("runs") or {}).get(world), "status": "missing_summary_row"})) for world in WORLD_IDS]
        batches.append({"id": summary.get("experiment_id", path.parent.name), "stage": path.parent.name[:2].upper(),
            "summary_status": summary.get("status"), "summary_path": str(path.relative_to(root)),
            "profile": (configuration.get("agent") or {}).get("guidance_profile", "baseline"),
            "model": model.get("model"), "sampling_seed": model.get("sampling_seed"),
            "sampling_seed_mode": "per_request_fixed_seed" if model.get("sampling_seed") is not None else "provider_default_unfixed_seed",
            "symbolic_regression_enabled": (configuration.get("numerics") or {}).get("symbolic_regression_enabled", False),
            "world_count": 6, "complete_worlds": sum(w["evaluation_complete"] for w in worlds),
            "complete_worlds_raw_score_at_least_90": sum(w["complete_and_raw_score_at_least_90"] for w in worlds),
            "mean_raw_score_incomplete_as_zero": sum(w["score_for_batch_mean_incomplete_as_zero"] for w in worlds) / 6,
            "mean_exploration_seconds": mean_known(worlds, "exploration_seconds"),
            "mean_total_seconds": mean_known(worlds, "total_seconds"), "worlds": worlds})
    repeats = defaultdict(list)
    for batch in batches:
        repeats[(batch["stage"], batch["profile"], batch["model"], batch["symbolic_regression_enabled"])].append(batch)
    groups = []
    for (stage, profile, model, symbolic), rows in repeats.items():
        groups.append({"stage": stage, "profile": profile, "model": model, "symbolic_regression_enabled": symbolic,
            "batch_ids": [r["id"] for r in rows], "repeats": len(rows),
            "high_world_counts_by_batch": [r["complete_worlds_raw_score_at_least_90"] for r in rows],
            "complete_world_counts_by_batch": [r["complete_worlds"] for r in rows],
            "mean_of_batch_means_incomplete_as_zero": sum(r["mean_raw_score_incomplete_as_zero"] for r in rows) / len(rows)})
    return {"generated_at": datetime.now(timezone.utc).isoformat(),
        "definitions": {"score": "Local development-world score, not official competition or hidden-world performance.",
            "deadline": "300 seconds applies to exploration; post-submission independent evaluation is excluded and total time includes it.",
            "output_tokens": "Completion tokens per model request, including retries; partial/missing usage never yields an invented full-run average.",
            "repeats": "Each six-world batch remains separate; repeated batches are averaged without selecting the best score for each world.",
            "symbolic_scope": "First PySR version searches observed state/probe properties without body-position inputs; this does not establish the value of body-aware symbolic regression.",
            "reproducibility": "A fixed sampling/search seed does not guarantee GPU/CPU multithreaded bitwise reproducibility.",
            "sampling_seed_mode": "E6 explicitly fixes the same model sampling seed on every request. Repeated actions may be associated with this setting, but these batches alone do not establish causality. Seeded E6 baseline is not an equivalent replication of the historical unseeded 3ba6d63/R01 run. Any unseeded or per-turn-seed amendment must remain a separate batch/protocol.",
            "tool_repeats": "Repeated identical calls are descriptive; a repeated observation or changed external state may be intentional."},
        "phase1_selection": {"source": "experiments/E5/e6-selection.json", "available": selection_path.is_file(),
                             "selected_profile": selection.get("selected_profile"), "record": selection or None},
        "batches": batches, "repeat_groups": groups, "warnings": warnings}


def mean_known(worlds, key):
    values = [w[key] for w in worlds if w[key] is not None]
    return {"value": sum(values) / len(values) if values else None, "worlds_with_reported_value": len(values)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, help="Default: PROJECT/experiments/E5/e6-e7-analysis.json")
    args = parser.parse_args(argv)
    root = args.project.resolve()
    output = (args.output or root / "experiments/E5/e6-e7-analysis.json").resolve()
    if output == root / "runs" or root / "runs" in output.parents:
        parser.error("Analysis output cannot be written inside runs")
    if output.name in {"summary.json", "manifest.json", "e6-selection.json", "e6-protocol.json"}:
        parser.error("Refusing to overwrite an experiment input")
    report = analyze(root)
    payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({"output": str(output), "batches": len(report["batches"]), "warnings": len(report["warnings"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
