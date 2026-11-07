"""Scientific-data/DSL adapter tests; real PySR search is tested on the worker."""
import copy
import json

import numpy as np
import pytest

from shore_agent.expressions import Expression
from shore_agent.symbolic_regression import (
    SymbolicRegressionError, _compress_frontier, export_candidate, prepare_dataset, run_search,
)


def probe(name="p1", n=5, properties=None):
    t = np.linspace(0, 1, n)
    return {"probe_id": name, "times": t.tolist(),
            "r_obs": np.column_stack((t, t**2)).tolist(),
            "v_obs": np.column_stack((t**2, -4*t**2)).tolist(),
            "a_est_times": t[1:-1].tolist(),
            "a_est": [[9999, 9999]] * (n-2),
            "initial_conditions": {"properties": properties or {}}}


def test_targets_use_observed_velocity_not_supplied_acceleration_or_hidden_fields():
    record = probe()
    record["acceleration_truth"] = [[-9000, 9000]] * 5
    before = copy.deepcopy(record)
    data = prepare_dataset([record])
    np.testing.assert_allclose(data["y"], np.column_stack((2*np.array(record["times"])[1:-1],
                                                        -8*np.array(record["times"])[1:-1])))
    np.testing.assert_allclose(data["states"][:, 0], record["a_est_times"])
    assert record == before


def test_probe_weights_do_not_reward_denser_sampling_and_property_coverage_is_explicit():
    data = prepare_dataset([probe("short", 4, {"mass": 2, "charge": 0}),
                            probe("long", 9, {"mass": 2})])
    assert sum(data["weights"][:2]) == pytest.approx(.5)
    assert sum(data["weights"][2:]) == pytest.approx(.5)
    assert "mass" in data["dropped_constant_features"]
    assert "charge" in data["omitted_incomplete_properties"]
    assert not set(data["feature_names"]) & {"mass", "charge"}
    varying = prepare_dataset([probe("a", properties={"mass": 1}), probe("b", properties={"mass": 3})])
    assert varying["feature_names"][-1] == "mass"


@pytest.mark.parametrize("mutator", [
    lambda p: p.update(times=[0, 0, .5, .75, 1]),
    lambda p: p.update(r_obs=[[1, 2]]),
    lambda p: p.update(a_est_times=[.25, .5]),
    lambda p: p["v_obs"][1].__setitem__(0, float("nan")),
    lambda p: p.update(initial_conditions={"properties": {"mass": True}}),
])
def test_invalid_arrays_and_alignment_fail_without_search(mutator):
    record = probe()
    mutator(record)
    with pytest.raises(SymbolicRegressionError):
        prepare_dataset([record])


def test_export_preserves_numerical_semantics_and_property_mapping():
    candidate = export_candidate("2.5*x + 1", "-3.25*mass*vy + sin(t)", ["x", "vy", "mass", "t"])
    assert len(candidate["parameter_spec"]) == 3
    assert "q('mass')" in candidate["law_spec"]["ay"]
    expression = Expression(candidate["law_spec"], candidate["parameter_spec"])
    parameters = {p["name"]: p["initial"] for p in candidate["parameter_spec"]}
    actual = expression.acceleration(.4, (2, 3), (4, 5), [], {"mass": 2}, parameters)
    np.testing.assert_allclose(actual, [6, -3.25*2*5+np.sin(.4)])


def test_equal_coefficients_are_not_forced_to_share_parameters_across_components():
    candidate = export_candidate("2.5*x", "2.5*y", ["x", "y"])
    assert len(candidate["parameter_spec"]) == 2
    assert candidate["law_spec"] == {"ax": "c1 * x", "ay": "c2 * y"}


def test_structural_powers_and_abs_are_compatible_with_the_existing_dsl():
    candidate = export_candidate("x**2 + Abs(y)", "x**(1/2)", ["x", "y"])
    assert candidate["parameter_spec"] == []
    assert candidate["law_spec"]["ay"] == "sqrt(x)"
    expression = Expression(candidate["law_spec"], [])
    np.testing.assert_allclose(expression.acceleration(0, (4, -2), (0, 0), [], {}, {}), [18, 2])


@pytest.mark.parametrize("source", [
    "__import__('os').system('echo unsafe')", "x.real", "x[0]", "unknown(x)",
    "x + missing", "lambda x: x", "float('nan')", "x + 1e999", "pow(x, 2)",
])
def test_unsupported_expression_syntax_is_rejected(source):
    with pytest.raises(SymbolicRegressionError):
        export_candidate(source, "0", ["x"])


def test_parameter_limit_is_enforced_for_the_combined_vector_without_coefficient_merging():
    with pytest.raises(SymbolicRegressionError, match="five"):
        export_candidate("2.1*x + 2.2*y + 2.3*t", "2.4*x + 2.5*y + 2.6*t", ["x", "y", "t"])


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def iterrows(self):
        return iter(enumerate(self.rows))


def test_search_adapter_uses_shared_budget_weights_and_exports_two_axis_candidates():
    calls, checkpoints = [], []

    class FakeSearch:
        def __init__(self, **kwargs):
            self.options = kwargs

        def fit(self, X, y, **kwargs):
            calls.append((self.options, X.copy(), y.copy(), kwargs))
            coefficient = 2 if len(calls) == 1 else -8
            self.equations_ = Rows([
                {"loss": 0.0, "complexity": 3, "sympy_format": f"{coefficient}.0*x"},
                {"loss": float("inf"), "complexity": 5, "sympy_format": "log(-x)"},
            ])

    result = run_search([probe()], time_budget_seconds=30, model_factory=FakeSearch,
                        progress_callback=checkpoints.append)
    assert len(calls) == 2
    assert calls[0][0]["timeout_in_seconds"] <= 14
    assert calls[1][0]["timeout_in_seconds"] < 28
    assert all(c[0]["warm_start"] is False and c[0]["precision"] == 64 for c in calls)
    assert calls[0][3]["variable_names"] == result["feature_names"]
    assert sum(calls[0][3]["weights"]) == pytest.approx(1)
    assert result["search_axes_completed"] == ["ax", "ay"]
    best = result["candidates"][0]
    assert best["acceleration_search_mse"] < 1e-20
    assert best["discovery_probe_ids"] == ["p1"]
    assert best["component_sources"] == ["pysr", "pysr"]
    assert result["used_probe_ids"] == ["p1"]
    assert result["status"] == "completed"
    assert checkpoints[0]["search_axes_completed"] == []
    assert checkpoints[0]["candidates"][0]["component_sources"] == ["constant_initialization"] * 2
    json.dumps(result, allow_nan=False)


def test_tiny_time_budget_never_claims_an_unchecked_initialization_is_valid():
    result = run_search([probe()], time_budget_seconds=1e-9)
    assert result["status"] == "timeout"
    assert result["search_axes_completed"] == []
    assert result["candidates"] == []


def test_constant_observed_acceleration_requires_no_pysr_dependency():
    record = probe()
    record["v_obs"] = [[0, 0]] * len(record["times"])
    result = run_search([record])
    assert result["search_axes_completed"] == []
    assert result["candidates"][0]["acceleration_search_mse"] == 0


def _frontier_candidate(source, complexity, loss):
    candidate = export_candidate(source, "-0.4", ["t"])
    return dict(candidate, complexity=complexity, normalized_acceleration_search_loss=loss,
                acceleration_search_mse=loss)


def test_roundoff_scale_loss_improvements_cannot_evict_simple_constant_endpoint():
    # Explicit ranking fixture: losses at floating-point differencing scale,
    # not a claim that these formulas have measurable physical differences.
    frontier = [
        _frontier_candidate("0.7", 2, 2.44e-30),
        _frontier_candidate("0.7 + 1e-15*t", 8, 2.33e-30),
        _frontier_candidate("0.7 + 2e-15*t", 14, 2.30e-30),
        _frontier_candidate("0.7 + 3e-15*t", 20, 2.29e-30),
    ]
    before = copy.deepcopy(frontier)
    selected = _compress_frontier(frontier, 3)
    assert [c["complexity"] for c in selected] == [20, 2, 8]
    assert [c["selection_role"] for c in selected] == [
        "lowest_search_loss", "lowest_complexity", "middle_complexity"]
    assert selected[1]["law_spec"] == {"ax": "c1", "ay": "c2"}
    assert [c["normalized_acceleration_search_loss"] for c in selected] == [2.29e-30, 2.44e-30, 2.33e-30]
    assert frontier == before
    for candidate in selected:
        Expression(candidate["law_spec"], candidate["parameter_spec"])


@pytest.mark.parametrize("count", [0, 1, 2, 3])
def test_short_frontier_keeps_available_distinct_endpoints_without_padding(count):
    frontier = [_frontier_candidate(f"0.7 + {index + 1}.0*t", index + 2, 1.0 / (index + 1))
                for index in range(count)]
    selected = _compress_frontier(frontier, 3)
    assert len(selected) == count
    assert len({json.dumps(c["parameter_spec"]) for c in selected}) == count
    if count == 1:
        assert selected[0]["selection_role"] == "lowest_loss_and_complexity"


def test_identical_accuracy_and_simplicity_endpoint_is_deduplicated():
    candidate = _frontier_candidate("0.7", 2, 0.0)
    selected = _compress_frontier([candidate, copy.deepcopy(candidate)], 3)
    assert len(selected) == 1
    assert selected[0]["selection_role"] == "lowest_loss_and_complexity"
    Expression(selected[0]["law_spec"], selected[0]["parameter_spec"])


def test_frontier_limit_one_preserves_accuracy_choice_and_limit_two_preserves_both_endpoints():
    simple = _frontier_candidate("0.7", 2, 1.0)
    accurate = _frontier_candidate("0.7 + 2.0*t", 5, 0.0)
    assert _compress_frontier([simple, accurate], 1)[0]["normalized_acceleration_search_loss"] == 0.0
    assert {c["selection_role"] for c in _compress_frontier([accurate, simple], 2)} == {
        "lowest_search_loss", "lowest_complexity"}


@pytest.mark.parametrize("kwargs", [
    {"time_budget_seconds": True}, {"time_budget_seconds": float("nan")},
    {"time_budget_seconds": 121}, {"max_candidates": 4}, {"random_state": -1},
])
def test_invalid_search_settings_are_rejected(kwargs):
    with pytest.raises(SymbolicRegressionError):
        run_search([probe()], **kwargs)


def physical_probe(name, position, velocity=(0.2, -0.1), start_sample=0.0):
    from scipy.integrate import solve_ivp
    t = np.linspace(start_sample, 1.2, 25)
    matrix = np.array([[-.13, .07], [.02, -.19]])
    def rhs(time, state):
        return np.r_[state[2:], matrix @ state[:2]]
    trajectory = solve_ivp(rhs, (0, t[-1]), np.r_[position, velocity],
                           t_eval=t, rtol=1e-11, atol=1e-13).y.T
    return {"probe_id": name, "times": t.tolist(), "r_obs": trajectory[:, :2].tolist(),
            "v_obs": trajectory[:, 2:].tolist(),
            "initial_conditions": {"t0": 0, "r0": list(position), "v0": list(velocity), "properties": {}}}


def test_real_power_exports_without_changing_negative_base_semantics():
    candidate = export_candidate("1.3*x**0.7", "y**2.0", ["x", "y"])
    assert candidate["law_spec"]["ay"] == "y ** 2"
    assert len(candidate["parameter_spec"]) == 2
    expression = Expression(candidate["law_spec"], candidate["parameter_spec"])
    parameters = {p["name"]: p["initial"] for p in candidate["parameter_spec"]}
    np.testing.assert_allclose(expression.acceleration(0, (3, -2), (0, 0), [], {}, parameters), [1.3*3**.7, 4])
    with pytest.raises(ValueError):
        expression.acceleration(0, (-3, 2), (0, 0), [], {}, parameters)


def test_every_returned_candidate_is_finite_at_actual_initial_state_even_if_measurements_start_later():
    import time
    from shore_agent.symbolic_regression import _select_candidates
    data = prepare_dataset([physical_probe("later", (0., 1.), velocity=(1., 0.), start_sample=.2)])
    rows = [[{"source": "1/x", "complexity": 3, "origin": "pysr"},
             {"source": "0.2", "complexity": 1, "origin": "constant_initialization"}],
            [{"source": "0.0", "complexity": 1, "origin": "constant_initialization"}]]
    candidates, audit = _select_candidates(rows, data, 3, time.monotonic()+3, {})
    assert audit["rejection_counts"]["observed_domain"] == 1
    rejected = next(r for r in audit["axis_equations"]["ax"] if r["source"] == "1/x")
    assert rejected["domain_valid"] is False
    assert candidates
    assert all(c["short_rollout_check"]["status"] == "passed" for c in candidates)
    assert all("/ x" not in c["law_spec"]["ax"] for c in candidates)


def test_time_singularity_is_rejected_despite_perfect_interior_derivative_fit():
    import time
    from shore_agent.symbolic_regression import _select_candidates
    t = np.linspace(0, 1, 12)
    p = {"probe_id": "constant_acceleration", "times": t.tolist(),
         "r_obs": np.column_stack((.5*t*t, 1+t*0)).tolist(),
         "v_obs": np.column_stack((t, t*0)).tolist(),
         "initial_conditions": {"t0": 0, "r0": [0, 1], "v0": [0, 0], "properties": {}}}
    rows = [[{"source": "vx/t", "complexity": 3, "origin": "pysr"},
             {"source": "1.0", "complexity": 1, "origin": "pysr"}],
            [{"source": "0", "complexity": 1, "origin": "pysr"}]]
    candidates, audit = _select_candidates(rows, prepare_dataset([p]), 3, time.monotonic()+3, {})
    assert audit["rejection_counts"]["observed_domain"] == 1
    assert candidates[0]["short_rollout_check"]["position_rmse"] < 1e-8
    assert candidates[0]["short_rollout_check"]["velocity_rmse"] < 1e-8


def test_moderate_linear_pair_survives_complex_coefficient_budget_and_all_axis_rows_are_auditable():
    import time
    from shore_agent.symbolic_regression import _select_candidates
    data = prepare_dataset([physical_probe("a", (1., 0.)), physical_probe("b", (0., 1.)),
                            physical_probe("c", (-1., 2.))])
    rows = []
    for ax in (True, False):
        simple = "-0.13*x + 0.07*y" if ax else "0.02*x - 0.19*y"
        axis = [{"source": simple+f" + {i*1e-8!r}*t + {i*2e-8!r}*vx", "complexity": 15, "origin": "pysr"}
                for i in range(1, 10)]
        axis += [{"source": simple, "complexity": 7, "origin": "pysr"},
                 {"source": "0.0", "complexity": 1, "origin": "constant_initialization"}]
        rows.append(axis)
    candidates, audit = _select_candidates(rows, data, 3, time.monotonic()+3, {})
    assert len(audit["axis_equations"]["ax"]) == 11
    assert len(audit["axis_equations"]["ay"]) == 11
    assert candidates
    best = candidates[0]
    assert best["component_sources"] == ["pysr", "pysr"]
    assert best["parameter_count"] == 4
    assert best["short_rollout_check"]["position_rmse"] < 1e-6
    assert "x" in best["law_spec"]["ay"] and "y" in best["law_spec"]["ay"]


def test_generic_linear_seed_recovers_coupled_components_without_claiming_pysr_origin():
    class EmptySearch:
        def __init__(self, **kwargs):
            assert kwargs["binary_operators"] == ["+", "-", "*", "/", "^"]
            assert kwargs["constraints"]["^"] == (-1, 1)
            assert {"sin", "cos", "exp", "log", "sqrt", "abs"} == set(kwargs["unary_operators"])
        def fit(self, *args, **kwargs): self.equations_ = Rows([])
    records = [physical_probe("a", (1., 0.)), physical_probe("b", (0., 1.)),
               physical_probe("c", (-1., 2.))]
    result = run_search(records, time_budget_seconds=15, model_factory=EmptySearch)
    best = result["candidates"][0]
    assert best["component_sources"] == ["linear_least_squares"] * 2
    assert best["parameter_count"] <= 5
    assert best["short_rollout_check"]["position_rmse"] < 1e-5
    assert best["acceleration_search_mse"] < 1e-8
    assert result["candidate_selection"]["independent_validation"] is False
    json.dumps(result, allow_nan=False)


def test_late_snapshot_retains_only_previously_certified_candidates(monkeypatch):
    from shore_agent import symbolic_regression as sr
    clock = [100.0]
    monkeypatch.setattr(sr.time, "monotonic", lambda: clock[0])
    checkpoints = []
    class SlowSearch:
        def __init__(self, **kwargs): pass
        def fit(self, *args, **kwargs):
            # Backend can exceed its soft timeout; hard supervisor remains external.
            clock[0] += 40
            self.equations_ = Rows([{ "loss": 0., "complexity": 3, "sympy_format": "vx/t"}])
    result = run_search([physical_probe("p", (1., 2.))], time_budget_seconds=30,
                        model_factory=SlowSearch, progress_callback=checkpoints.append)
    before = checkpoints[1]["candidates"]
    assert before
    assert result["candidates"] == before
    assert result["candidate_selection"]["selection_incomplete"] is True
    assert result["candidate_selection"]["retained_checkpoint"] is True
    assert all(c["short_rollout_check"]["status"] == "passed" for c in result["candidates"])
    assert any(r["source"] == "vx/t" for r in result["axis_equations"]["ax"])
    assert next(r for r in result["axis_equations"]["ax"] if r["source"] == "vx/t")["domain_valid"] is None


@pytest.mark.parametrize("source", ["sin(t)", "cos(t)", "exp(t)", "log(t + 2.0)"])
def test_elementary_functions_remain_in_search_and_certified_return_space(source):
    import time
    from shore_agent.symbolic_regression import _select_candidates, UNARY_OPERATORS
    function = source.split("(")[0]
    assert function in UNARY_OPERATORS
    data = prepare_dataset([physical_probe("p", (1., 2.))])
    rows = [[{"source": source, "complexity": 4, "origin": "pysr"}],
            [{"source": "0", "complexity": 1, "origin": "pysr"}]]
    candidates, audit = _select_candidates(rows, data, 3, time.monotonic()+3, {})
    assert len(candidates) == 1
    assert function+"(" in candidates[0]["law_spec"]["ax"]
    assert candidates[0]["short_rollout_check"]["status"] == "passed"
    assert audit["axis_equations"]["ax"][0]["domain_valid"] is True


def test_log_is_allowed_but_its_initial_domain_failure_is_rejected():
    import time
    from shore_agent.symbolic_regression import _select_candidates
    data = prepare_dataset([physical_probe("late", (1., 2.), start_sample=.2)])
    rows = [[{"source": "log(t)", "complexity": 2, "origin": "pysr"}],
            [{"source": "0", "complexity": 1, "origin": "pysr"}]]
    candidates, audit = _select_candidates(rows, data, 3, time.monotonic()+3, {})
    assert candidates == []
    assert audit["rejection_counts"]["observed_domain"] == 1
