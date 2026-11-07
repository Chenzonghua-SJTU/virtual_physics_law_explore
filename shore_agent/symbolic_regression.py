"""Optional state-space symbolic search using acquired current-session probes.

PySR is imported only by ``run_search``. This module does not import a simulator,
read experiment archives, fit trajectory parameters, or submit a law. Its soft
search timeout is NOT a process deadline: callers must enforce a hard timeout.
"""
from __future__ import annotations

import ast
import itertools
import math
import time
from pathlib import Path

import numpy as np

from .expressions import Expression, ExpressionError, MAX_MAGNITUDE


FEATURES = ("t", "x", "y", "vx", "vy")
PROPERTIES = ("mass", "charge")
BINARY_OPERATORS = ("+", "-", "*", "/", "^")
UNARY_OPERATORS = ("sin", "cos", "exp", "sqrt", "log", "abs")
EXPORT_UNARY_OPERATORS = ("sin", "cos", "exp", "sqrt", "log", "abs")
MAX_ROWS = 20000
MAX_EQUATIONS_PER_AXIS = 32


class SymbolicRegressionError(ValueError):
    code = "symbolic_regression_error"


def prepare_dataset(probes):
    """Align observed state to velocity-derived acceleration; equal probe weight.

    Each probe contributes total weight 1/N_probes regardless of its sampling
    density. Properties are included only when supplied on every selected probe.
    Constant columns are removed without inferring absence of physical effects.
    Arrays and per-row public properties remain internal to the search worker.
    """
    if not isinstance(probes, (list, tuple)) or not probes or len(probes) > 128:
        raise SymbolicRegressionError("Provide 1 to 128 current-session probes")
    ids = [p.get("probe_id") for p in probes if isinstance(p, dict)]
    if len(ids) != len(probes) or not all(isinstance(i, str) and i for i in ids) or len(set(ids)) != len(ids):
        raise SymbolicRegressionError("Probe IDs must be distinct nonempty strings")
    properties = []
    for probe in probes:
        prop = probe.get("initial_conditions", {}).get("properties", {})
        if not isinstance(prop, dict):
            raise SymbolicRegressionError("Invalid public properties")
        selected = {}
        for key in PROPERTIES:
            if key in prop:
                value = prop[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise SymbolicRegressionError("Public properties must be finite numbers")
                selected[key] = float(value)
        properties.append(selected)
    common = [key for key in PROPERTIES if all(key in p for p in properties)]
    omitted = [key for key in PROPERTIES if any(key in p for p in properties) and key not in common]
    feature_names = list(FEATURES) + common
    xs, ys, ws, states, row_properties, counts = [], [], [], [], [], []
    for probe, prop in zip(probes, properties):
        try:
            t = np.asarray(probe["times"], dtype=float)
            r, v = (np.asarray(probe[key], dtype=float) for key in ("r_obs", "v_obs"))
            if t.ndim != 1 or not 3 <= len(t) <= 1000 or r.shape != (len(t), 2) or v.shape != r.shape:
                raise ValueError("shape")
            if not all(np.isfinite(a).all() for a in (t, r, v)) or not np.all(np.diff(t) > 0):
                raise ValueError("nonfinite or unordered")
            # Never accept an acceleration truth field: recompute from v_obs.
            a = np.gradient(v, t, axis=0)[1:-1]
            if not np.isfinite(a).all():
                raise ValueError("acceleration")
            if "a_est_times" in probe:
                at = np.asarray(probe["a_est_times"], dtype=float)
                if at.shape != t[1:-1].shape or not np.allclose(at, t[1:-1], rtol=1e-10, atol=1e-12):
                    raise ValueError("acceleration alignment")
        except (KeyError, TypeError, ValueError) as exc:
            raise SymbolicRegressionError("Invalid observation arrays or acceleration time alignment") from exc
        state = np.column_stack((t[1:-1], r[1:-1], v[1:-1]))
        x = np.column_stack((state, *[np.full(len(a), prop[key]) for key in common])) if common else state.copy()
        xs.append(x); ys.append(a); states.append(state)
        ws.append(np.full(len(a), 1.0 / (len(probes) * len(a))))
        row_properties.extend([prop.copy() for _ in a])
        counts.append(len(a))
    if sum(counts) > MAX_ROWS:
        raise SymbolicRegressionError("Too many observed samples")
    X, y, weights = np.concatenate(xs), np.concatenate(ys), np.concatenate(ws)
    varying = np.any(X != X[0], axis=0)
    dropped = [name for name, keep in zip(feature_names, varying) if not keep]
    return {"X": X[:, varying], "y": y, "weights": weights,
            "feature_names": [name for name, keep in zip(feature_names, varying) if keep],
            "used_probe_ids": ids, "samples_per_probe": dict(zip(ids, counts)),
            "dropped_constant_features": dropped, "omitted_incomplete_properties": omitted,
            "states": np.concatenate(states), "row_properties": row_properties,
            "probes": probes}


def export_candidate(ax_source, ay_source, feature_names):
    """Convert two SymPy-style strings into the existing bounded expression DSL.

    Every numerical coefficient occurrence gets its own parameter. We never
    merge coefficients merely because their optimized values happen to be close.
    Only structural +/-1, 0, and integer exponents -3..3 stay literal.
    """
    allowed = set(feature_names)
    if not allowed <= set(FEATURES + PROPERTIES):
        raise SymbolicRegressionError("Unknown feature name")
    parameters = []

    def parameter(value):
        if not math.isfinite(value) or abs(value) > MAX_MAGNITUDE:
            raise SymbolicRegressionError("Invalid fitted coefficient")
        if len(parameters) >= 5:
            raise SymbolicRegressionError("Candidate needs more than five scalar parameters")
        name = "c" + str(len(parameters) + 1)
        parameters.append({"name": name, "initial": float(value)})
        return ast.Name(id=name, ctx=ast.Load())

    def convert(node, *, exponent=False, offset=False):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = node.value
            if exponent and float(value).is_integer() and -3 <= value <= 3:
                return ast.Constant(value=int(value))
            if type(value) is int and ((exponent and -3 <= value <= 3) or
                                       (not exponent and value in (0, 1, -1) and not (offset and value))):
                return node
            return parameter(float(value))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            if isinstance(node.operand, ast.Constant) and type(node.operand.value) in (int, float):
                value = node.operand.value * (-1 if isinstance(node.op, ast.USub) else 1)
                return convert(ast.Constant(value=value), exponent=exponent, offset=offset)
            return ast.UnaryOp(op=node.op, operand=convert(node.operand))
        if isinstance(node, ast.Name) and node.id in allowed:
            if node.id in PROPERTIES:
                return ast.Call(func=ast.Name(id="q", ctx=ast.Load()), args=[ast.Constant(value=node.id)], keywords=[])
            return node
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
            is_offset = isinstance(node.op, (ast.Add, ast.Sub))
            # SymPy emits sqrt as a rational power; preserve that structural
            # operation without turning 1/2 into an unrelated fitted exponent.
            if isinstance(node.op, ast.Pow) and isinstance(node.right, ast.BinOp) and isinstance(node.right.op, ast.Div):
                if (isinstance(node.right.left, ast.Constant) and node.right.left.value == 1
                        and isinstance(node.right.right, ast.Constant) and node.right.right.value == 2):
                    return ast.Call(func=ast.Name(id="sqrt", ctx=ast.Load()), args=[convert(node.left)], keywords=[])
            return ast.BinOp(left=convert(node.left, offset=is_offset), op=node.op,
                             right=convert(node.right, exponent=isinstance(node.op, ast.Pow), offset=is_offset))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and len(node.args) == 1 and not node.keywords:
            name = "abs" if node.func.id == "Abs" else node.func.id
            if name in EXPORT_UNARY_OPERATORS:
                arg = convert(node.args[0])
                # Literal-only functions are forbidden by the existing DSL.
                if isinstance(arg, ast.Constant):
                    arg = parameter(float(arg.value))
                return ast.Call(func=ast.Name(id=name, ctx=ast.Load()), args=[arg], keywords=[])
        raise SymbolicRegressionError("Unsupported search expression syntax")

    law_spec = {}
    for key, source in (("ax", ax_source), ("ay", ay_source)):
        if not isinstance(source, str) or not source or len(source) > 4096:
            raise SymbolicRegressionError("Invalid search expression")
        try:
            tree = ast.parse(source, mode="eval")
            if sum(1 for _ in ast.walk(tree)) > 256:
                raise SymbolicRegressionError("Search expression too large")
            law_spec[key] = ast.unparse(ast.fix_missing_locations(convert(tree.body)))
        except (SyntaxError, RecursionError) as exc:
            raise SymbolicRegressionError("Invalid search expression syntax") from exc
        if len(law_spec[key]) > 600:
            raise SymbolicRegressionError("Export exceeds tool expression length")
    try:
        Expression(law_spec, parameters)
    except ExpressionError as exc:
        raise SymbolicRegressionError(str(exc)) from exc
    return {"law_spec": law_spec, "parameter_spec": parameters}


def _evaluate_array(source, features):
    """Small vector interpreter for search auditing; never eval or compiled code."""
    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return float(node.value)
        if isinstance(node, ast.Name) and node.id in features:
            return features[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp):
            a, b = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add): return a + b
            if isinstance(node.op, ast.Sub): return a - b
            if isinstance(node.op, ast.Mult): return a * b
            if isinstance(node.op, ast.Div): return np.divide(a, b)
            if isinstance(node.op, ast.Pow): return np.power(a, b)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and len(node.args) == 1:
            functions = {"sin": np.sin, "cos": np.cos, "exp": np.exp,
                         "sqrt": np.sqrt, "log": np.log, "abs": np.abs, "Abs": np.abs}
            if node.func.id in functions:
                return functions[node.func.id](visit(node.args[0]))
        raise SymbolicRegressionError("unsupported_expression")
    with np.errstate(all="ignore"):
        values = np.asarray(visit(ast.parse(source, mode="eval").body), dtype=float)
    if not np.isfinite(values).all() or np.any(np.abs(values) > MAX_MAGNITUDE):
        raise SymbolicRegressionError("nonfinite_expression")
    return values


def _candidate_loss(candidate, dataset):
    expr = Expression(candidate["law_spec"], candidate["parameter_spec"])
    parameters = {p["name"]: p["initial"] for p in candidate["parameter_spec"]}
    prediction = np.asarray([expr.acceleration(t, (x, y), (vx, vy), [], prop, parameters)
                             for (t, x, y, vx, vy), prop in zip(dataset["states"], dataset["row_properties"])])
    per_axis = np.sum(dataset["weights"][:, None] * (prediction - dataset["y"]) ** 2, axis=0)
    if not np.isfinite(per_axis).all():
        raise SymbolicRegressionError("Nonfinite candidate loss")
    return per_axis.tolist()


def _all_features(dataset):
    rows, properties = [], []
    for probe in dataset["probes"]:
        t, r, v = (np.asarray(probe[k], dtype=float) for k in ("times", "r_obs", "v_obs"))
        initial = probe.get("initial_conditions", {})
        prop = initial.get("properties", {})
        # Include known controls, even when the first measurement is later than t0.
        rows.append(np.r_[initial.get("t0", t[0]), initial.get("r0", r[0]), initial.get("v0", v[0])])
        rows.extend(np.column_stack((t, r, v)))
        properties.extend([prop] * (len(t) + 1))
    states = np.asarray(rows)
    features = {name: states[:, i] for i, name in enumerate(FEATURES)}
    for name in PROPERTIES:
        if name in dataset["feature_names"]:
            features[name] = np.asarray([p[name] for p in properties])
    return features


def _differencing_tolerance(dataset):
    """Estimate resolution sensitivity from central stencils, not a truth error bar."""
    errors = []
    for probe in dataset["probes"]:
        t, v = np.asarray(probe["times"]), np.asarray(probe["v_obs"])
        fine = np.gradient(v, t, axis=0)
        if len(t) >= 5:
            left, right = t[2:-2]-t[:-4], t[4:]-t[2:-2]
            wide = (-right/(left*(left+right)))[:, None]*v[:-4]
            wide += ((right-left)/(left*right))[:, None]*v[2:-2]
            wide += (left/(right*(left+right)))[:, None]*v[4:]
            # Exact nonuniform central stencil; /3 is the uniform h^2 scaling.
            errors.append(np.mean(((wide-fine[2:-2])/3.0)**2, axis=0))
    return np.mean(errors, axis=0) if errors else np.zeros(2)


def _linear_rows(dataset, axis, deadline=float("inf")):
    """Generic sparse linear combinations, not a physics equation catalogue."""
    X, y, w = dataset["X"], dataset["y"][:, axis], np.sqrt(dataset["weights"])
    names = dataset["feature_names"]
    result = []
    for degree in range(1, min(3, len(names)) + 1):
        for subset in itertools.combinations(range(len(names)), degree):
            if time.monotonic() >= deadline: return result
            design = X[:, subset]
            coef, _, rank, _ = np.linalg.lstsq(design * w[:, None], y * w, rcond=None)
            if rank != degree or not np.isfinite(coef).all():
                continue
            source = " + ".join(f"({float(c)!r}*{names[j]})" for j, c in zip(subset, coef))
            result.append({"source": source, "complexity": 4*degree-1,
                           "origin": "linear_least_squares"})
    return result


def _reason(exc):
    message = str(exc)
    if "five scalar" in message: return "parameter_budget"
    if "length" in message or "large" in message: return "expression_size"
    if "nonfinite" in message: return "observed_domain"
    return "dsl_export"


def _prepare_axis(rows, dataset, axis, audit, deadline=float("inf")):
    features = {name: dataset["X"][:, i] for i, name in enumerate(dataset["feature_names"])}
    complete = _all_features(dataset)
    valid, seen = [], set()
    for raw in rows:
        source = raw["source"]
        if source in seen: continue
        seen.add(source)
        row = dict(raw)
        if time.monotonic() >= deadline:
            row.update(domain_valid=None, rejection_reason="not_checked_budget")
            audit.append(row)
            continue
        try:
            candidate = export_candidate(source, "0", dataset["feature_names"])
            row["parameter_count"] = len(candidate["parameter_spec"])
            prediction = _evaluate_array(source, features)
            row["loss"] = float(np.sum(dataset["weights"] * (prediction-dataset["y"][:, axis])**2))
            _evaluate_array(source, complete)
            row["domain_valid"] = True
            valid.append(row)
        except (ValueError, OverflowError, TypeError, ZeroDivisionError) as exc:
            row["domain_valid"] = False
            row["rejection_reason"] = _reason(exc)
        audit.append(row)
    # Parameter cost is part of dominance BEFORE two components are combined.
    frontier = [r for r in valid if not any(
        o["loss"] <= r["loss"] and o["complexity"] <= r["complexity"] and
        o["parameter_count"] <= r["parameter_count"] and
        (o["loss"] < r["loss"] or o["complexity"] < r["complexity"] or
         o["parameter_count"] < r["parameter_count"])
        for o in valid)]
    # The PySR HOF is bounded by maxsize; generic seeds are also finite. Preserve
    # the best row for every complexity/parameter-cost cell before any cap.
    cells = {}
    for row in sorted(frontier, key=lambda r: (r["loss"], r["source"])):
        cells.setdefault((row["parameter_count"], row["complexity"]), row)
    ordered = sorted(cells.values(), key=lambda r: (r["parameter_count"], r["complexity"], r["loss"]))
    if len(ordered) > MAX_EQUATIONS_PER_AXIS:
        indexes = np.linspace(0, len(ordered)-1, MAX_EQUATIONS_PER_AXIS).round().astype(int)
        ordered = [ordered[i] for i in indexes]
    return ordered


def _short_rollout(candidate, dataset, deadline):
    """Bounded replay from each acquired initial state; not independent validation."""
    from scipy.integrate import solve_ivp
    expr = Expression(candidate["law_spec"], candidate["parameter_spec"])
    params = {p["name"]: p["initial"] for p in candidate["parameter_spec"]}
    local_deadline = min(deadline, time.monotonic() + .4)
    position_errors, velocity_errors, calls = [], [], 0
    for probe in dataset["probes"]:
        t, r, v = (np.asarray(probe[k], dtype=float) for k in ("times", "r_obs", "v_obs"))
        initial = probe.get("initial_conditions", {})
        t0 = float(initial.get("t0", t[0]))
        y0 = np.r_[initial.get("r0", r[0]), initial.get("v0", v[0])]
        prop = initial.get("properties", {})
        end = min(float(t[-1]), t0 + min(1.0, 2*float(np.median(np.diff(t)))))
        if end <= t0: raise SymbolicRegressionError("short_rollout_invalid_interval")
        probe_calls = 0
        def rhs(ti, state):
            nonlocal calls, probe_calls
            calls += 1; probe_calls += 1
            if time.monotonic() >= local_deadline: raise SymbolicRegressionError("short_rollout_time_limit")
            if probe_calls > 256: raise SymbolicRegressionError("short_rollout_rhs_limit")
            if not np.isfinite(state).all() or np.any(np.abs(state) > 1e7):
                raise SymbolicRegressionError("short_rollout_divergence")
            return np.r_[state[2:], expr.acceleration(ti, state[:2], state[2:], [], prop, params)]
        try:
            rhs(t0, y0)
            solution = solve_ivp(rhs, (t0, end), y0, t_eval=[end], method="DOP853", rtol=1e-6, atol=1e-9)
            if not solution.success or solution.y.shape != (4, 1):
                raise SymbolicRegressionError("short_rollout_integration_failure")
        except ExpressionError as exc:
            raise SymbolicRegressionError("short_rollout_domain") from exc
        # No extrapolation: when there is no acquired sample in this interval,
        # only numerical validity is checked, without claiming observed accuracy.
        if end >= t[0]:
            observed_r = np.array([np.interp(end, t, r[:, i]) for i in range(2)])
            observed_v = np.array([np.interp(end, t, v[:, i]) for i in range(2)])
            position_errors.append(float(np.sum((solution.y[:2, -1]-observed_r)**2)))
            velocity_errors.append(float(np.sum((solution.y[2:, -1]-observed_v)**2)))
    return {"status": "passed", "probe_count": len(dataset["probes"]), "rhs_calls": calls,
            "position_rmse": float(np.sqrt(np.mean(position_errors))) if position_errors else None,
            "velocity_rmse": float(np.sqrt(np.mean(velocity_errors))) if velocity_errors else None,
            "scope": "Short acquired-data replay only; not fitted or independently validated."}


def _compress_frontier(frontier, limit):
    """Keep accuracy and simplicity endpoints without treating tiny loss gains as proof.

    Losses remain untouched. The middle proposal is a representative of the
    complexity-ordered frontier, not a newly scored or independently tested law.
    """
    if not frontier:
        return []

    def signature(candidate):
        return (tuple(candidate["law_spec"][axis] for axis in ("ax", "ay")),
                tuple((p["name"], p["initial"]) for p in candidate["parameter_spec"]))

    ordered = sorted(frontier, key=lambda c: (c["complexity"], c["normalized_acceleration_search_loss"], signature(c)))
    best = min(ordered, key=lambda c: (c["normalized_acceleration_search_loss"], c["complexity"], signature(c)))
    choices = [(best, "lowest_search_loss"), (ordered[0], "lowest_complexity")]
    if len(ordered) > 2:
        choices.append((ordered[(len(ordered) - 1) // 2], "middle_complexity"))
    selected, seen = [], {}
    for candidate, role in choices:
        key = signature(candidate)
        if key in seen:
            if role == "lowest_complexity":
                selected[seen[key]]["selection_role"] = "lowest_loss_and_complexity"
            continue
        if len(selected) >= limit:
            continue
        seen[key] = len(selected)
        selected.append(dict(candidate, selection_role=role))
    return selected


def _select_candidates(axis_rows, dataset, limit, deadline, cache):
    audits = [[], []]
    axes = [_prepare_axis(rows, dataset, axis, audits[axis], deadline) for axis, rows in enumerate(axis_rows)]
    pool, seen, rejected = [], set(), {}
    examples, stages = [], {}
    def reject(reason, **fields):
        stage = fields.get("stage", "unknown")
        stages[stage] = stages.get(stage, 0) + 1
        rejected[reason] = rejected.get(reason, 0) + 1
        if len(examples) < 24: examples.append(dict(reason=reason, **fields))
    for axis, rows in zip(("ax", "ay"), audits):
        for r in rows:
            if r["domain_valid"] is False: reject(r["rejection_reason"], stage="axis", axis=axis, source=r["source"])
    scale = np.maximum(np.sum(dataset["weights"][:, None]*dataset["y"]**2, axis=0), 1e-20)
    tolerance = max(1e-10, float(np.mean(_differencing_tolerance(dataset)/scale)))
    for left, right in itertools.product(*axes):
        if time.monotonic() >= deadline: break
        try:
            if left["parameter_count"] + right["parameter_count"] > 5:
                raise SymbolicRegressionError("Candidate needs more than five scalar parameters")
            candidate = export_candidate(left["source"], right["source"], dataset["feature_names"])
            key = (candidate["law_spec"]["ax"], candidate["law_spec"]["ay"],
                   tuple(p["initial"] for p in candidate["parameter_spec"]))
            if key in seen: continue
            seen.add(key)
            losses = [left["loss"], right["loss"]]
            candidate.update(complexity=left["complexity"]+right["complexity"],
                parameter_count=len(candidate["parameter_spec"]),
                acceleration_search_mse_by_axis=losses, acceleration_search_mse=sum(losses),
                normalized_acceleration_search_loss=float(np.mean(np.asarray(losses)/scale)),
                discovery_probe_ids=list(dataset["used_probe_ids"]), dsl_valid=True,
                component_sources=[left.get("origin", "pysr"), right.get("origin", "pysr")],
                initial_domain_check={"status": "passed", "scope": "All acquired states and controlled initial states"})
            pool.append((key, candidate))
        except (ValueError, OverflowError) as exc:
            reject(_reason(exc), stage="pair", ax=left["source"], ay=right["source"])
    # Rank by accuracy, then retain the simplest statistically unresolved model.
    # Resolution sensitivity is a heuristic, not a formal noise/confidence bound.
    ranked = sorted(pool, key=lambda item: (item[1]["normalized_acceleration_search_loss"], item[1]["complexity"]))
    if ranked:
        threshold = ranked[0][1]["normalized_acceleration_search_loss"] + tolerance
        simplest = sorted([i for i in ranked if i[1]["normalized_acceleration_search_loss"] <= threshold],
                          key=lambda i: (i[1]["complexity"], i[1]["parameter_count"], i[1]["normalized_acceleration_search_loss"]))
        ranked = simplest + ranked
    checked, candidates = set(), []
    for key, candidate in ranked:
        if key in checked: continue
        checked.add(key)
        if len(checked) > 16: break
        if key not in cache:
            if time.monotonic() >= deadline: break
            try: cache[key] = _short_rollout(candidate, dataset, deadline)
            except (ValueError, OverflowError, ZeroDivisionError) as exc:
                cache[key] = {"status": "failed", "reason": str(exc) if str(exc).startswith("short_rollout_") else "short_rollout_domain"}
        result = cache[key]
        if result["status"] != "passed":
            reject(result["reason"], stage="rollout", ax=candidate["law_spec"]["ax"], ay=candidate["law_spec"]["ay"])
            continue
        candidate["short_rollout_check"] = result
        candidate["selection_role"] = "simplest_within_resolution_tolerance" if not candidates else "alternative_accuracy_candidate"
        candidates.append(candidate)
        if len(candidates) == limit: break
    return candidates, {"axis_equations": dict(zip(("ax", "ay"), audits)), "rejection_counts": rejected,
        "rejection_examples": examples, "rejected_candidate_pairs": stages.get("pair", 0),
        "candidate_selection": {"strategy": "parameter_aware_pareto_then_resolution_tolerance_and_short_rollout",
            "normalized_resolution_tolerance": tolerance, "legal_pairs": len(pool),
            "rejection_stage_counts": stages, "rejected_candidates_total": sum(stages.values()),
            "unchecked_axis_equations": sum(r["domain_valid"] is None for rows in audits for r in rows), "rollout_candidates_considered": len(checked),
            "axis_frontier_counts": [len(a) for a in axes], "full_axis_equations_retained": True,
            "selection_incomplete": time.monotonic() >= deadline,
            "stop_reason": "selection_deadline" if time.monotonic() >= deadline else None,
            "retained_checkpoint": False, "independent_validation": False}}


def run_search(probes, time_budget_seconds=30, max_candidates=3, random_state=42,
               output_directory=None, model_factory=None, progress_callback=None):
    """Search algebra, powers and elementary functions; certify acquired states.

    Linear seeds are explicitly labelled and use no physical templates. PySR
    coefficients, including real exponents, are exported to the existing DSL.
    Every returned pair passes a bounded short rollout, never just DSL syntax.
    """
    if isinstance(time_budget_seconds, bool) or not isinstance(time_budget_seconds, (int, float)) or not math.isfinite(time_budget_seconds) or not 0 < time_budget_seconds <= 120:
        raise SymbolicRegressionError("Search budget must be in (0, 120] seconds")
    if type(max_candidates) is not int or not 1 <= max_candidates <= 3:
        raise SymbolicRegressionError("Return one to three candidates")
    if type(random_state) is not int or not 0 <= random_state < 2**31:
        raise SymbolicRegressionError("Invalid search seed")
    started = time.monotonic()
    deadline = started + float(time_budget_seconds)
    final_reserve = min(5.0, max(2.0, time_budget_seconds*.2))
    dataset = prepare_dataset(probes)
    means = np.sum(dataset["weights"][:, None]*dataset["y"], axis=0)
    axis_rows = [[{"source": repr(float(value)), "complexity": 1, "origin": "constant_initialization"}]
                 for value in means]
    report = {"status": "running", "backend": "pysr_with_linear_seeds", "target": "velocity_difference_acceleration",
        "used_probe_ids": dataset["used_probe_ids"], "feature_names": dataset["feature_names"],
        "samples_per_probe": dataset["samples_per_probe"], "dropped_constant_features": dataset["dropped_constant_features"],
        "omitted_incomplete_properties": dataset["omitted_incomplete_properties"],
        "search_configuration": {"maxsize": 20, "binary_operators": list(BINARY_OPERATORS),
            "unary_operators": list(UNARY_OPERATORS), "power_exponent_max_complexity": 1,
            "random_state": random_state, "warm_start": False, "parallelism": "multithreading",
            "linear_seed_max_terms": 3, "finalization_reserve_seconds": final_reserve,
            "operator_scope": "All listed operators are enabled in each PySR search; no staged exclusion.",
            "simplicity_preference": "Linear seeds plus parameter/complexity-aware selection within resolution tolerance."},
        "warnings": ["Search loss uses finite-difference acceleration, not independent prediction.",
            "All selected probes are discovery data and cannot serve as independent validation.",
            "Constant/absent properties do not establish absence of physical dependence.",
            "Body positions are not included; explicit t may substitute for unobserved body motion.",
            "Resolution tolerance is a finite-stencil sensitivity heuristic, not a confidence interval.",
            "Short rollout checks certify only acquired initial states; fit and fresh-probe validation remain required."],
        "axis_search_seconds": [], "search_axes_completed": [], "candidates": []}
    cache = {}
    def snapshot(status):
        candidates, audit = _select_candidates(axis_rows, dataset, max_candidates, deadline, cache)
        # The dataset is immutable throughout a search. A late snapshot may
        # exhaust its selection budget; keep previously certified candidates,
        # never replacing them with unvalidated partial search output.
        previous = report.get("candidates", [])
        if audit["candidate_selection"]["selection_incomplete"] and previous:
            keys = {(c["law_spec"]["ax"], c["law_spec"]["ay"],
                     tuple(p["initial"] for p in c["parameter_spec"])) for c in candidates}
            kept = 0
            for candidate in previous:
                key = (candidate["law_spec"]["ax"], candidate["law_spec"]["ay"],
                       tuple(p["initial"] for p in candidate["parameter_spec"]))
                if key not in keys and len(candidates) < max_candidates:
                    candidates.append(candidate); keys.add(key); kept += 1
            audit["candidate_selection"]["retained_checkpoint"] = kept > 0
        report.update(audit)
        report.update(status=status, candidates=candidates, elapsed_seconds=time.monotonic()-started)
        if progress_callback is not None:
            import copy
            progress_callback(copy.deepcopy(report))
    snapshot("running")
    if time.monotonic() < deadline-final_reserve:
        for axis in range(2): axis_rows[axis] += _linear_rows(dataset, axis, deadline-final_reserve)
        snapshot("running")
    needs_search = bool(dataset["feature_names"]) and any(not np.all(dataset["y"][:,i] == dataset["y"][0,i]) for i in range(2))
    if model_factory is None and needs_search and time.monotonic() < deadline-final_reserve:
        try: from pysr import PySRRegressor
        except ImportError as exc: raise SymbolicRegressionError("PySR is unavailable in the symbolic worker environment") from exc
        model_factory = PySRRegressor
    for axis in range(2):
        remaining = deadline-time.monotonic()-final_reserve
        if remaining <= 0: break
        if not dataset["feature_names"] or np.all(dataset["y"][:,axis] == dataset["y"][0,axis]):
            report["axis_search_seconds"].append(0.0)
            continue
        axis_budget = remaining/(2-axis)
        options = dict(binary_operators=list(BINARY_OPERATORS), unary_operators=list(UNARY_OPERATORS),
            constraints={"^": (-1, 1)}, maxsize=20, niterations=1000000, populations=8, population_size=27,
            ncycles_per_iteration=100, timeout_in_seconds=axis_budget, random_state=random_state+axis,
            parallelism="multithreading", warm_start=False, precision=64, verbosity=0, progress=False)
        if output_directory is not None: options["output_directory"] = str(Path(output_directory)/("ax" if axis==0 else "ay"))
        begin = time.monotonic()
        model = model_factory(**options)
        model.fit(dataset["X"], dataset["y"][:,axis], weights=dataset["weights"], variable_names=dataset["feature_names"])
        report["axis_search_seconds"].append(time.monotonic()-begin)
        for _, row in model.equations_.iterrows():
            try:
                loss, complexity = float(row["loss"]), int(row["complexity"])
                if not math.isfinite(loss) or loss < 0 or not 1 <= complexity <= 20: continue
                source = str(row["sympy_format"])
                if len(source) > 4096: continue
                axis_rows[axis].append({"source": source, "complexity": complexity, "loss": loss, "origin": "pysr"})
            except (KeyError, ValueError, TypeError): continue
        report["search_axes_completed"].append("ax" if axis==0 else "ay")
        snapshot("running")
    snapshot("timeout" if time.monotonic() >= deadline-final_reserve else "completed")
    return report
