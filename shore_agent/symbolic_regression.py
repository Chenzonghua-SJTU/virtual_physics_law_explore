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
SEARCH_MAXSIZE = 48
MAX_AXIS_CANDIDATES = 3
MAX_INTERNAL_PARAMETERS = 24


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


def export_candidate(ax_source, ay_source, feature_names, *, _parameter_limit=5):
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
        if len(parameters) >= _parameter_limit:
            raise SymbolicRegressionError("Candidate needs more than five scalar parameters" if _parameter_limit == 5
                                          else "Candidate exceeds internal coefficient budget")
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
        if len(parameters) <= 5:
            Expression(law_spec, parameters)
        else:
            # Check the identical DSL structure with one placeholder symbol.
            # This does not certify the unrestricted coefficient list as an
            # executable five-parameter law; raw axis records say so explicitly.
            collapsed = _rename_parameters(law_spec, {p["name"]: "coefficient" for p in parameters})
            Expression(collapsed, [{"name": "coefficient", "initial": 1.0}])
    except ExpressionError as exc:
        raise SymbolicRegressionError(str(exc)) from exc
    return {"law_spec": law_spec, "parameter_spec": parameters}


def _rename_parameters(law_spec, mapping):
    class Rename(ast.NodeTransformer):
        def visit_Name(self, node):
            return ast.copy_location(ast.Name(id=mapping.get(node.id, node.id), ctx=ast.Load()), node)
    return {axis: ast.unparse(ast.fix_missing_locations(Rename().visit(ast.parse(source, mode="eval"))))
            for axis, source in law_spec.items()}


def validate_axis_candidate(candidate, component):
    """Validate non-executable single-axis output by deterministic re-export.

    A component with >5 coefficient occurrences is useful mathematical evidence,
    but is never accepted as an executable joint law by this helper.
    """
    if not isinstance(candidate, dict) or component not in ("ax", "ay"):
        raise SymbolicRegressionError("Invalid axis candidate")
    if candidate.get("component") != component or candidate.get("joint_fit_ready") is not False:
        raise SymbolicRegressionError("Single-axis candidates are not joint-fit-ready")
    source = candidate.get("source")
    expected = export_candidate(source if component == "ax" else "0",
                                source if component == "ay" else "0", FEATURES+PROPERTIES,
                                _parameter_limit=MAX_INTERNAL_PARAMETERS)
    if candidate.get("law_spec") != expected["law_spec"] or candidate.get("parameter_spec") != expected["parameter_spec"]:
        raise SymbolicRegressionError("Single-axis source and exported coefficients differ")
    count = len(expected["parameter_spec"])
    if candidate.get("parameter_count") != count or candidate.get("parameter_budget_compatible") != (count <= 5):
        raise SymbolicRegressionError("Invalid single-axis parameter metadata")
    return expected


def _evaluate_array(source, features):
    """Small vector interpreter for search auditing; never eval or compiled code."""
    def compute(node):
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
            if isinstance(node.op, ast.Pow):
                if np.any(np.abs(b) > 32):
                    raise SymbolicRegressionError("nonfinite_expression_or_exponent_limit")
                return np.power(a, b)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and len(node.args) == 1:
            if node.func.id == "q" and isinstance(node.args[0], ast.Constant) and node.args[0].value in PROPERTIES:
                return features[node.args[0].value]
            functions = {"sin": np.sin, "cos": np.cos, "exp": np.exp,
                         "sqrt": np.sqrt, "log": np.log, "abs": np.abs, "Abs": np.abs}
            if node.func.id in functions:
                return functions[node.func.id](visit(node.args[0]))
        raise SymbolicRegressionError("unsupported_expression")
    def visit(node):
        value = compute(node)
        checked = np.asarray(value, dtype=float)
        if not np.isfinite(checked).all() or np.any(np.abs(checked) > MAX_MAGNITUDE):
            raise SymbolicRegressionError("nonfinite_expression")
        return value
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
            candidate = export_candidate(source, "0", dataset["feature_names"], _parameter_limit=MAX_INTERNAL_PARAMETERS)
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
        best = min(range(len(ordered)), key=lambda i:(ordered[i]["loss"],ordered[i]["complexity"]))
        simple = min(range(len(ordered)), key=lambda i:(ordered[i]["complexity"],ordered[i]["parameter_count"],ordered[i]["loss"]))
        indexes = list(dict.fromkeys([best, simple, *np.linspace(0,len(ordered)-1,MAX_EQUATIONS_PER_AXIS).round().astype(int)]))
        if len(indexes) < MAX_EQUATIONS_PER_AXIS:
            indexes.extend(i for i in range(len(ordered)) if i not in indexes)
        ordered = [ordered[i] for i in indexes[:MAX_EQUATIONS_PER_AXIS]]
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


def _sharing_groups(parameter_spec, deadline=None):
    """Cheap proposal feasibility only; equality still requires data validation."""
    values = [float(p["initial"]) for p in parameter_spec]
    groups = [[i] for i in range(len(values))]
    while len(groups) > 5:
        if deadline is not None and time.monotonic() >= deadline:
            raise SymbolicRegressionError("sharing_time_limit")
        proposals = []
        for i, a in enumerate(groups):
            for j, b in enumerate(groups[:i]):
                together = [values[index] for index in a+b]
                lo, hi = min(together), max(together)
                distance = (hi-lo)/max(abs(lo),abs(hi),1e-12)
                if distance <= .1 and (lo >= 0 or hi <= 0):
                    proposals.append((distance,j,i))
        if not proposals:
            raise SymbolicRegressionError("sharing_no_supported_proposal")
        _, j, i = min(proposals)
        groups[j] += groups.pop(i)
    return groups


def _parameter_sharing(candidate, dataset, deadline):
    """Propose ties by numeric proximity, accept only after joint data fitting.

    The proposal is never treated as physical identity. A whole-probe holdout
    inside the discovery data checks the constrained fit when >=2 probes exist;
    fresh-probe independent validation is still required by the Agent.
    """
    from scipy.optimize import least_squares
    original = candidate["parameter_spec"]
    if len(original) <= 5:
        return candidate
    stop = min(deadline, time.monotonic()+1.0)
    values = np.asarray([p["initial"] for p in original], dtype=float)
    # Only propose close, same-sign coefficient occurrences. Their closeness is
    # not the acceptance test: distinct true values must fail the data check.
    groups = _sharing_groups(original, stop)
    names = [f"c{i+1}" for i in range(len(groups))]
    mapping = {original[index]["name"]: name for name, group in zip(names, groups) for index in group}
    law = _rename_parameters(candidate["law_spec"], mapping)
    guess = np.asarray([float(np.mean(values[group])) for group in groups])
    features = {name: dataset["X"][:,i] for i,name in enumerate(dataset["feature_names"])}
    full_features = _all_features(dataset)
    count = len(dataset["weights"])
    y, weights = dataset["y"], dataset["weights"]
    # Weight each selected trajectory equally, including the held-out trajectory.
    train_mask = np.ones(count, dtype=bool)
    heldout_ids = []
    if len(dataset["used_probe_ids"]) >= 2:
        last_id = dataset["used_probe_ids"][-1]
        heldout_size = dataset["samples_per_probe"][last_id]
        train_mask[-heldout_size:] = False
        heldout_ids = [last_id]
    calls = 0
    def predict(formula, parameters, table):
        context = dict(table, **parameters)
        return np.column_stack([np.broadcast_to(_evaluate_array(formula[axis], context),
                                               (len(next(iter(table.values()))),)) for axis in ("ax", "ay")])
    original_parameters = {p["name"]: p["initial"] for p in original}
    before_prediction = predict(candidate["law_spec"], original_parameters, features)
    def mse(prediction, mask):
        w = weights[mask]/sum(weights[mask])
        return np.sum(w[:,None]*(prediction[mask]-y[mask])**2, axis=0)
    old = mse(before_prediction, np.ones(count, dtype=bool))
    resolution = _differencing_tolerance(dataset)
    signal = np.sum(weights[:,None]*y*y, axis=0)
    def permitted(original_loss):
        return original_loss + np.maximum.reduce([.05*original_loss, 4*resolution, 1e-14*np.maximum(signal, 1e-12)])
    def residual(parameters, mask):
        nonlocal calls
        calls += 1
        if time.monotonic() >= stop: raise SymbolicRegressionError("sharing_time_limit")
        try:
            prediction = predict(law, dict(zip(names, parameters)), features)
            value = (prediction[mask]-y[mask])*np.sqrt(weights[mask])[:,None]
            return value.ravel()
        except (SymbolicRegressionError, ValueError, OverflowError, ZeroDivisionError):
            return np.full(2*int(np.sum(mask)), 1e6)
    result = least_squares(residual, guess, args=(train_mask,), max_nfev=35, x_scale="jac",
                           ftol=1e-9, xtol=1e-9, gtol=1e-9)
    constrained = predict(law, dict(zip(names, result.x)), features)
    checks = []
    for label, mask in (("fit", train_mask), ("heldout_discovery_probes", ~train_mask)):
        if not np.any(mask): continue
        baseline, fitted = mse(before_prediction, mask), mse(constrained, mask)
        tolerance = permitted(baseline)
        passed = bool(np.all(fitted <= tolerance))
        checks.append({"split": label, "original_mse_by_axis": baseline.tolist(),
                       "shared_mse_by_axis": fitted.tolist(), "maximum_accepted_mse_by_axis": tolerance.tolist(),
                       "passed": passed})
        if not passed: raise SymbolicRegressionError("sharing_data_rejected")
    # Refit on all discovery data after the whole-trajectory selection check.
    if heldout_ids:
        result = least_squares(residual, result.x, args=(np.ones(count,dtype=bool),), max_nfev=25,
                               x_scale="jac", ftol=1e-9, xtol=1e-9, gtol=1e-9)
    parameters = [{"name": name, "initial": float(value)} for name,value in zip(names,result.x)]
    Expression(law, parameters)
    params = {p["name"]:p["initial"] for p in parameters}
    prediction = predict(law, params, features)
    after = mse(prediction, np.ones(count,dtype=bool))
    if not np.all(after <= permitted(old)): raise SymbolicRegressionError("sharing_data_rejected")
    predict(law, params, full_features)  # Do not inherit pre-fit domain validity.
    scale = np.maximum(signal, 1e-20)
    return dict(candidate, law_spec=law, parameter_spec=parameters, parameter_count=len(parameters),
        acceleration_search_mse_by_axis=after.tolist(), acceleration_search_mse=float(np.sum(after)),
        normalized_acceleration_search_loss=float(np.mean(after/scale)),
        parameter_sharing={"status": "data_validated", "proposal": "close coefficients proposed, never assumed equal",
            "uncompressed_law_spec": candidate["law_spec"], "uncompressed_parameter_spec": original,
            "groups": [{"shared_parameter":name,"original_parameters":[original[i]["name"] for i in group]}
                       for name,group in zip(names,groups)],
            "original_loss_by_axis": old.tolist(), "shared_loss_by_axis": after.tolist(),
            "acceptance_tolerance_by_axis": permitted(old).tolist(), "fit_evaluations": calls,
            "heldout_discovery_probe_ids": heldout_ids, "split_checks": checks,
            "independent_validation": False,
            "limitation": "Ties are supported only by the supplied discovery data and resolution heuristic."})


def _axis_public_candidates(axes, dataset, tolerance_by_axis):
    result = {}
    for index, component in enumerate(("ax", "ay")):
        rows = sorted(axes[index], key=lambda r: (r["loss"],r["complexity"]))
        if rows:
            threshold = rows[0]["loss"] + tolerance_by_axis[index]
            simple = sorted([r for r in rows if r["loss"] <= threshold],
                            key=lambda r:(r["complexity"],r["parameter_count"],r["loss"]))
            rows = simple[:1] + rows[:1] + simple[1:] + rows[1:]
        seen, result[component] = set(), []
        for row in rows:
            if row["source"] in seen: continue
            seen.add(row["source"])
            source = row["source"]
            raw = export_candidate(source if index==0 else "0", source if index==1 else "0",
                                   dataset["feature_names"], _parameter_limit=MAX_INTERNAL_PARAMETERS)
            result[component].append(dict(raw, component=component, source=source,
                loss=row["loss"],complexity=row["complexity"],origin=row.get("origin","pysr"),
                parameter_count=len(raw["parameter_spec"]), joint_fit_ready=False,
                parameter_budget_compatible=len(raw["parameter_spec"])<=5,
                initial_domain_check={"status":"passed","scope":"This component on all acquired and controlled initial states"},
                prediction_accuracy_status="not_independently_validated"))
            if len(result[component]) >= MAX_AXIS_CANDIDATES: break
    return result


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
    resolution = _differencing_tolerance(dataset)
    tolerance = max(1e-10, float(np.mean(resolution/scale)))
    oversized = []
    for left, right in itertools.product(*axes):
        if time.monotonic() >= deadline: break
        try:
            candidate = export_candidate(left["source"], right["source"], dataset["feature_names"],
                                         _parameter_limit=MAX_INTERNAL_PARAMETERS)
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
            if candidate["parameter_count"] > 5:
                oversized.append((key,candidate))
            else:
                pool.append((key, candidate))
        except (ValueError, OverflowError) as exc:
            reject(_reason(exc), stage="pair", ax=left["source"], ay=right["source"])
    # The public first component is the simplest one within that axis's
    # resolution tolerance. Give their joint interpretation a fit opportunity,
    # rather than spending every slot on global loss/complexity extremes.
    axis_candidates = _axis_public_candidates(axes, dataset, resolution)
    preferred_key = None
    if all(axis_candidates[axis] for axis in ("ax", "ay")):
        try:
            preferred = export_candidate(axis_candidates["ax"][0]["source"], axis_candidates["ay"][0]["source"],
                                         dataset["feature_names"], _parameter_limit=MAX_INTERNAL_PARAMETERS)
            preferred_key = (preferred["law_spec"]["ax"], preferred["law_spec"]["ay"],
                             tuple(p["initial"] for p in preferred["parameter_spec"]))
        except (ValueError, OverflowError):
            pass  # Individually readable components need not form a legal pair.
    sharing_cache = cache.setdefault("parameter_sharing", {})
    sharing_deadline = min(deadline, time.monotonic()+2.0)
    by_loss = sorted(oversized, key=lambda item:(item[1]["normalized_acceleration_search_loss"],item[1]["complexity"]))
    by_complexity = sorted(oversized, key=lambda item:(item[1]["complexity"],item[1]["normalized_acceleration_search_loss"]))
    sharing_order = [item for item in oversized if item[0] == preferred_key]
    public_pair_prioritized = bool(sharing_order)
    queued = {item[0] for item in sharing_order}
    for accurate, simple in zip(by_loss, by_complexity):
        for item in (accurate, simple):
            if item[0] not in queued:
                queued.add(item[0])
                sharing_order.append(item)
    fit_attempts, prefilter_rejections = 0, 0
    for key,candidate in sharing_order:
        if key not in sharing_cache:
            if time.monotonic() >= sharing_deadline or fit_attempts >= 4: continue
            try:
                _sharing_groups(candidate["parameter_spec"], sharing_deadline)
            except SymbolicRegressionError as exc:
                if str(exc) == "sharing_time_limit": continue
                sharing_cache[key] = {"error": str(exc), "stage": "proposal_prefilter"}
                prefilter_rejections += 1
            else:
                fit_attempts += 1
                try:
                    sharing_cache[key] = _parameter_sharing(candidate, dataset, sharing_deadline)
                except (ValueError, OverflowError, ZeroDivisionError) as exc:
                    sharing_cache[key] = {"error": str(exc) if str(exc).startswith("sharing_") else "sharing_fit_failed"}
        shared = sharing_cache[key]
        if "error" in shared:
            reject(shared["error"],stage="sharing",ax=candidate["law_spec"]["ax"],ay=candidate["law_spec"]["ay"])
            continue
        new_key = (shared["law_spec"]["ax"],shared["law_spec"]["ay"],tuple(p["initial"] for p in shared["parameter_spec"]))
        pool.append((new_key,shared))
    # Uncompressed components remain available even if no joint sharing is accepted.
    # Rank by accuracy, then retain the simplest statistically unresolved model.
    # Resolution sensitivity is a heuristic, not a formal noise/confidence bound.
    ranked = sorted(pool, key=lambda item: (item[1]["normalized_acceleration_search_loss"], item[1]["complexity"]))
    if ranked:
        threshold = ranked[0][1]["normalized_acceleration_search_loss"] + tolerance
        simplest = sorted([i for i in ranked if i[1]["normalized_acceleration_search_loss"] <= threshold],
                          key=lambda i: (i[1]["complexity"], i[1]["parameter_count"], i[1]["normalized_acceleration_search_loss"]))
        ranked = simplest[:1] + ranked[:1] + simplest[1:] + ranked[1:]
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
        candidate["joint_fit_ready"] = True
        candidate["prediction_accuracy_status"] = "not_independently_validated"
        candidate["selection_role"] = "simplest_within_resolution_tolerance" if not candidates else "alternative_accuracy_candidate"
        candidates.append(candidate)
        if len(candidates) == limit: break
    return candidates, {"axis_candidates": axis_candidates, "axis_equations": dict(zip(("ax", "ay"), audits)), "rejection_counts": rejected,
        "rejection_examples": examples, "rejected_candidate_pairs": stages.get("pair", 0),
        "candidate_selection": {"strategy": "parameter_aware_pareto_then_resolution_tolerance_and_short_rollout",
            "normalized_resolution_tolerance": tolerance, "legal_pairs": len(pool),
            "over_budget_pairs_retained": len(oversized), "sharing_attempts_cached": len(sharing_cache),
            "sharing_fit_attempts_this_selection": fit_attempts,
            "sharing_proposal_prefilter_rejections_this_selection": prefilter_rejections,
            "sharing_order": "public_axis_first_pair_then_interleaved_loss_and_complexity; infeasible_proposals_do_not_consume_fit_slots",
            "sharing_public_axis_pair_prioritized": public_pair_prioritized,
            "sharing_unattempted_pairs": sum(key not in sharing_cache for key,_ in oversized),
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
    report = {"status": "running", "backend": "staged_pysr_with_regression_basis", "target": "velocity_difference_acceleration",
        "used_probe_ids": dataset["used_probe_ids"], "feature_names": dataset["feature_names"],
        "samples_per_probe": dataset["samples_per_probe"], "dropped_constant_features": dataset["dropped_constant_features"],
        "omitted_incomplete_properties": dataset["omitted_incomplete_properties"],
        "search_configuration": {"maxsize": SEARCH_MAXSIZE, "binary_operators": list(BINARY_OPERATORS),
            "unary_operators": list(UNARY_OPERATORS), "power_exponent_max_complexity": 1,
            "random_state": random_state, "warm_start": False, "parallelism": "multithreading",
            "linear_seed_max_terms": 3, "finalization_reserve_seconds": final_reserve,
            "operator_scope": "Plan: algebraic then full elementary operators; actual completed stages are in search_stages and depend on remaining budget.",
            "simplicity_preference": "Linear seeds plus parameter/complexity-aware selection within resolution tolerance."},
        "warnings": ["Search loss uses finite-difference acceleration, not independent prediction.",
            "All selected probes are discovery data and cannot serve as independent validation.",
            "Constant/absent properties do not establish absence of physical dependence.",
            "Body positions are not included; explicit t may substitute for unobserved body motion.",
            "Resolution tolerance is a finite-stencil sensitivity heuristic, not a confidence interval.",
            "Short rollout checks certify only acquired initial states; fit and fresh-probe validation remain required."],
        "data_quality": {"samples_per_probe": dataset["samples_per_probe"],
            "differencing_tolerance_by_axis": _differencing_tolerance(dataset).tolist(),
            "dropped_constant_features": dataset["dropped_constant_features"],
            "omitted_incomplete_properties": dataset["omitted_incomplete_properties"],
            "body_positions_included": False, "acceleration_source": "observed_velocity_finite_difference",
            "trajectory_checks": "executability only; reported RMSE is training diagnostic, not accuracy certification"},
        "axis_search_seconds": [], "search_axes_completed": [], "search_stages": [], "candidates": []}
    cache = {}
    last_complete_selection = None
    def snapshot(status):
        import copy
        nonlocal last_complete_selection
        candidates, audit = _select_candidates(axis_rows, dataset, max_candidates, deadline, cache)
        # The dataset is immutable throughout a search. A late snapshot may
        # exhaust its selection budget; keep previously certified candidates,
        # never replacing them with unvalidated partial search output.
        if audit["candidate_selection"]["selection_incomplete"]:
            if last_complete_selection is not None:
                candidates = copy.deepcopy(last_complete_selection["candidates"])
                audit["axis_candidates"] = copy.deepcopy(last_complete_selection["axis_candidates"])
                audit["candidate_selection"]["retained_checkpoint"] = bool(
                    candidates or any(audit["axis_candidates"].values()))
        else:
            last_complete_selection = {"candidates": copy.deepcopy(candidates),
                                       "axis_candidates": copy.deepcopy(audit["axis_candidates"])}
        report.update(audit)
        report.update(status=status, candidates=candidates, elapsed_seconds=time.monotonic()-started)
        if progress_callback is not None:
            import copy
            progress_callback(copy.deepcopy(report))
    snapshot("running")
    if time.monotonic() < deadline-final_reserve:
        for axis in range(2): axis_rows[axis] += _linear_rows(dataset, axis, deadline-final_reserve)
        snapshot("running")
    if time.monotonic() < deadline-final_reserve:
        from .symbolic_basis import generate_basis_candidates
        basis = generate_basis_candidates(dataset, deadline=min(deadline-final_reserve, time.monotonic()+3))
        report['basis_diagnostics'] = basis['diagnostics']
        for axis in range(2): axis_rows[axis] += basis['axis_rows'][axis]
        snapshot('running')
    needs_search = bool(dataset["feature_names"]) and any(not np.all(dataset["y"][:,i] == dataset["y"][0,i]) for i in range(2))
    if model_factory is None and needs_search and time.monotonic() < deadline-final_reserve:
        try: from pysr import PySRRegressor
        except ImportError as exc: raise SymbolicRegressionError("PySR is unavailable in the symbolic worker environment") from exc
        model_factory = PySRRegressor
    from .symbolic_geometry import ALIASES, feature_table, expand_aliases, radial_projection
    search_X, search_names = feature_table(dataset)
    projected, projection_diagnostics = radial_projection(dataset)
    report['geometric_features'] = {key: value for key, value in ALIASES.items() if key in search_names}
    report['projection_diagnostics'] = projection_diagnostics
    search_deadline = deadline-final_reserve
    total_search = max(0., search_deadline-time.monotonic())
    # A supported projection changes representation, not the admissible laws.
    # Keep Cartesian searches as a fallback; never force an unsupported symmetry.
    projected_fraction = .55 if projected is not None else 0.
    schedule = []
    if projected is not None:
        schedule += [('radial_algebra', None, projected_fraction*.4, ['sqrt', 'abs']),
                     ('radial_full', None, projected_fraction*.6, list(UNARY_OPERATORS))]
    for axis in range(2):
        schedule.append((f'axis_{axis}_algebra', axis, (1-projected_fraction)*.18, ['sqrt', 'abs']))
    for axis in range(2):
        schedule.append((f'axis_{axis}_full', axis, (1-projected_fraction)*.32, list(UNARY_OPERATORS)))
    for stage_index, (label, axis, fraction, unary) in enumerate(schedule):
        remaining = search_deadline-time.monotonic()
        stage_budget = min(total_search*fraction, remaining)
        if not needs_search or stage_budget < .15: break
        target = projected['target'] if axis is None else dataset['y'][:, axis]
        if np.all(target == target[0]): continue
        weights = projected['weights'] if axis is None else dataset['weights']
        options = dict(binary_operators=list(BINARY_OPERATORS), unary_operators=unary,
            constraints={'^': (-1, 1)}, maxsize=24 if label.endswith('algebra') else SEARCH_MAXSIZE,
            niterations=1000000, populations=8, population_size=27, ncycles_per_iteration=100,
            timeout_in_seconds=stage_budget, random_state=random_state+stage_index,
            parallelism='multithreading', warm_start=False, precision=64, verbosity=0, progress=False)
        if output_directory is not None: options['output_directory'] = str(Path(output_directory)/label)
        begin = time.monotonic()
        try:
            model = model_factory(**options)
            model.fit(search_X, target, weights=weights, variable_names=search_names)
        except Exception as exc:
            # Backend failures do not erase already checked candidates. Input
            # validation and export safety checks remain outside this boundary.
            report['search_stages'].append({'stage': label, 'status': 'error',
                'requested_seconds': stage_budget, 'elapsed_seconds': time.monotonic()-begin,
                'error_type': type(exc).__name__, 'message': str(exc)[:500]})
            report['warnings'].append('Search backend failed; returning earlier checked candidates without retrying the backend.')
            report['backend_error'] = True
            break
        elapsed = time.monotonic()-begin
        report['axis_search_seconds'].append(elapsed)
        report['search_stages'].append({'stage': label, 'requested_seconds': stage_budget,
                                       'elapsed_seconds': elapsed, 'features': search_names, 'unary_operators': unary})
        for _, row in model.equations_.iterrows():
            try:
                loss, complexity = float(row['loss']), int(row['complexity'])
                if not math.isfinite(loss) or loss < 0 or not 1 <= complexity <= SEARCH_MAXSIZE: continue
                source = expand_aliases(str(row['sympy_format']))
                if len(source) > 4096: continue
                for component in range(2) if axis is None else (axis,):
                    expression = f'({source})*{("x", "y")[component]}' if axis is None else source
                    axis_rows[component].append({'source': expression, 'complexity': complexity+(2 if axis is None else 0),
                                                'origin': 'pysr', 'search_representation': label})
            except (KeyError, ValueError, TypeError, SyntaxError): continue
        for component in range(2) if axis is None else (axis,):
            name = ('ax','ay')[component]
            if name not in report['search_axes_completed']: report['search_axes_completed'].append(name)
        snapshot('running')
    snapshot("timeout" if time.monotonic() >= deadline-final_reserve else
             "partial" if report.get('backend_error') else "completed")
    return report
