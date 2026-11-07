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
BINARY_OPERATORS = ("+", "-", "*", "/")
UNARY_OPERATORS = ("sin", "cos", "exp", "sqrt", "log", "abs")
MAX_ROWS = 20000
MAX_EQUATIONS_PER_AXIS = 8


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
            "states": np.concatenate(states), "row_properties": row_properties}


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
            if name in UNARY_OPERATORS:
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


def _candidate_loss(candidate, dataset):
    expr = Expression(candidate["law_spec"], candidate["parameter_spec"])
    parameters = {p["name"]: p["initial"] for p in candidate["parameter_spec"]}
    prediction = np.asarray([expr.acceleration(t, (x, y), (vx, vy), [], prop, parameters)
                             for (t, x, y, vx, vy), prop in zip(dataset["states"], dataset["row_properties"])])
    per_axis = np.sum(dataset["weights"][:, None] * (prediction - dataset["y"]) ** 2, axis=0)
    if not np.isfinite(per_axis).all():
        raise SymbolicRegressionError("Nonfinite candidate loss")
    return per_axis.tolist()


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


def _select_candidates(axis_rows, dataset, limit):
    pool, seen, rejected = [], set(), 0
    # Normalize only ranking, not raw input variables, targets or exported laws.
    scale = np.sum(dataset["weights"][:, None] * dataset["y"] ** 2, axis=0)
    scale = np.maximum(scale, 1e-20)
    for left, right in itertools.product(*axis_rows):
        try:
            candidate = export_candidate(left["source"], right["source"], dataset["feature_names"])
            signature = (tuple(candidate["law_spec"].values()), tuple(p["initial"] for p in candidate["parameter_spec"]))
            if signature in seen:
                continue
            seen.add(signature)
            losses = _candidate_loss(candidate, dataset)
            complexity = int(left["complexity"] + right["complexity"])
            candidate.update(complexity=complexity, acceleration_search_mse_by_axis=losses,
                             acceleration_search_mse=float(sum(losses)),
                             normalized_acceleration_search_loss=float(np.mean(np.asarray(losses) / scale)),
                             discovery_probe_ids=list(dataset["used_probe_ids"]), dsl_valid=True,
                             component_sources=[left.get("origin", "pysr"), right.get("origin", "pysr")])
            pool.append(candidate)
        except (SymbolicRegressionError, ExpressionError, OverflowError, ValueError):
            rejected += 1
    # Return nondominated accuracy/complexity choices; no physical score implied.
    frontier = [c for c in pool if not any(
        other["complexity"] <= c["complexity"] and
        other["normalized_acceleration_search_loss"] <= c["normalized_acceleration_search_loss"] and
        (other["complexity"] < c["complexity"] or
         other["normalized_acceleration_search_loss"] < c["normalized_acceleration_search_loss"])
        for other in pool)]
    return _compress_frontier(frontier, limit), rejected


def run_search(probes, time_budget_seconds=30, max_candidates=3, random_state=42,
               output_directory=None, model_factory=None, progress_callback=None):
    """Search each acceleration component within one shared soft time budget.

    ``progress_callback`` receives JSON-compatible snapshots before and between
    searches. A supervising process can persist these for hard-timeout recovery.
    Reuse a warmed Julia runtime, never a prior session's search state/model.
    """
    if isinstance(time_budget_seconds, bool) or not isinstance(time_budget_seconds, (int, float)) or not 0 < time_budget_seconds <= 120:
        raise SymbolicRegressionError("Search budget must be in (0, 120] seconds")
    if type(max_candidates) is not int or not 1 <= max_candidates <= 3:
        raise SymbolicRegressionError("Return one to three candidates")
    if type(random_state) is not int or not 0 <= random_state < 2**31 - 1:
        raise SymbolicRegressionError("Invalid search seed")
    started = time.monotonic()
    deadline = started + float(time_budget_seconds)
    dataset = prepare_dataset(probes)
    means = np.sum(dataset["weights"][:, None] * dataset["y"], axis=0)
    axis_rows = [[{"source": repr(float(value)), "complexity": 1, "loss": float("inf"), "origin": "constant_initialization"}]
                 for value in means]
    warnings = ["Search loss is against velocity-difference acceleration, not independent trajectory prediction.",
                "All selected probes were used for structure discovery and cannot serve as independent validation.",
                "Constant or absent properties do not establish absence of physical dependence.",
                "This version searches state and public probe properties only; body-set expressions are not supported.",
                "State-only dependence on t does not establish explicit physical time dependence; it may substitute for unmodeled body motion.",
                "A fixed seed with multithreaded search does not guarantee bitwise reproducibility."]
    report = {"status": "running", "backend": "pysr", "target": "velocity_difference_acceleration",
              "used_probe_ids": dataset["used_probe_ids"], "feature_names": dataset["feature_names"],
              "samples_per_probe": dataset["samples_per_probe"],
              "dropped_constant_features": dataset["dropped_constant_features"],
              "omitted_incomplete_properties": dataset["omitted_incomplete_properties"],
              "search_configuration": {"maxsize": 20, "binary_operators": list(BINARY_OPERATORS),
                  "unary_operators": list(UNARY_OPERATORS), "random_state": random_state,
                  "warm_start": False, "parallelism": "multithreading"},
              "warnings": warnings, "axis_search_seconds": [], "search_axes_completed": [], "candidates": []}

    def snapshot(status):
        candidates, rejected = _select_candidates(axis_rows, dataset, max_candidates)
        report.update(status=status, candidates=candidates, rejected_candidate_pairs=rejected,
                      elapsed_seconds=time.monotonic() - started)
        if progress_callback is not None:
            # Keep an immutable checkpoint even if the caller stores it in memory.
            import copy
            progress_callback(copy.deepcopy(report))

    snapshot("running")
    needs_search = bool(dataset["feature_names"]) and any(
        not np.all(dataset["y"][:, i] == dataset["y"][0, i]) for i in range(2))
    if model_factory is None and needs_search and time.monotonic() < deadline - 2.0:
        try:
            from pysr import PySRRegressor
        except ImportError as exc:
            raise SymbolicRegressionError("PySR is unavailable in the symbolic worker environment") from exc
        model_factory = PySRRegressor
    for axis in range(2):
        remaining = deadline - time.monotonic() - 2.0
        if remaining <= 0:
            break
        # Constant observed acceleration needs no evolutionary search. This is
        # a sample-level shortcut, never a claim about unseen state dependence.
        if not dataset["feature_names"] or np.all(dataset["y"][:, axis] == dataset["y"][0, axis]):
            report["axis_search_seconds"].append(0.0)
            continue
        axis_budget = remaining / (2 - axis)
        options = dict(binary_operators=list(BINARY_OPERATORS), unary_operators=list(UNARY_OPERATORS),
                       maxsize=20, niterations=1000000, populations=8, population_size=27,
                       ncycles_per_iteration=100, timeout_in_seconds=axis_budget,
                       random_state=random_state + axis, parallelism="multithreading",
                       warm_start=False, precision=64, verbosity=0, progress=False)
        if output_directory is not None:
            options["output_directory"] = str(Path(output_directory) / ("ax" if axis == 0 else "ay"))
        axis_start = time.monotonic()
        model = model_factory(**options)
        model.fit(dataset["X"], dataset["y"][:, axis], weights=dataset["weights"],
                  variable_names=dataset["feature_names"])
        report["axis_search_seconds"].append(time.monotonic() - axis_start)
        rows = []
        for _, row in model.equations_.iterrows():
            try:
                loss, complexity = float(row["loss"]), int(row["complexity"])
                if not math.isfinite(loss) or loss < 0 or complexity < 1:
                    continue
                rows.append({"source": str(row["sympy_format"]), "complexity": complexity, "loss": loss})
            except (KeyError, TypeError, ValueError):
                continue
        # Keep both low-loss and simple solutions before pairing the axes.
        simple = sorted(rows, key=lambda r: (r["complexity"], r["loss"]))[:1]
        accurate = sorted(rows, key=lambda r: (r["loss"], r["complexity"]))[:MAX_EQUATIONS_PER_AXIS - 2]
        axis_rows[axis] += accurate + simple
        report["search_axes_completed"].append("ax" if axis == 0 else "ay")
        snapshot("running")
    snapshot("timeout" if time.monotonic() >= deadline - 2.0 else "completed")
    return report
