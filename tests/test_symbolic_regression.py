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
    assert len(calls) == 4
    assert calls[0][0]["timeout_in_seconds"] <= 14
    assert calls[1][0]["timeout_in_seconds"] < 28
    assert all(c[0]["warm_start"] is False and c[0]["precision"] == 64 for c in calls)
    assert set(result["feature_names"]) <= set(calls[0][3]["variable_names"])
    assert 'radius2' in calls[0][3]['variable_names']
    assert calls[0][0]['unary_operators'] == ['sin', 'cos', 'exp', 'sqrt', 'log', 'abs']
    assert calls[-1][0]['unary_operators'] == ['sin', 'cos', 'exp', 'sqrt', 'log', 'abs']
    assert sum(calls[0][3]["weights"]) == pytest.approx(1)
    assert result["search_axes_completed"] == ["ax", "ay"]
    best = result["candidates"][0]
    assert best["acceleration_search_mse"] < 1e-20
    assert best["discovery_probe_ids"] == ["p1"]
    assert set(best["component_sources"]) <= {"pysr", "regression_basis", "linear_least_squares"}
    assert any(row['origin'] == 'pysr' for row in result['axis_equations']['ax'])
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


def test_backend_stage_failure_retains_previously_checked_candidates_without_retry():
    attempts = []
    class BrokenSearch:
        def __init__(self, **kwargs):
            attempts.append(kwargs)
        def fit(self, *args, **kwargs):
            raise RuntimeError('backend temporarily unavailable')
    result = run_search([probe()], time_budget_seconds=30, model_factory=BrokenSearch)
    assert len(attempts) == 1
    assert result['status'] == 'partial'
    assert result['search_stages'][-1]['status'] == 'error'
    assert result['candidates']
    assert all(c['short_rollout_check']['status'] == 'passed' for c in result['candidates'])
    assert all('pysr' not in c['component_sources'] for c in result['candidates'])


def test_reserved_search_budget_end_is_completed_not_backend_timeout(monkeypatch):
    from shore_agent import symbolic_regression as sr
    clock = [100.]
    monkeypatch.setattr(sr.time, 'monotonic', lambda: clock[0])
    class BudgetSearch:
        def __init__(self, **kwargs): pass
        def fit(self, *args, **kwargs):
            clock[0] += 26
            self.equations_ = Rows([])
    result = run_search([probe()], time_budget_seconds=30, model_factory=BudgetSearch)
    assert result['status'] == 'completed'
    assert result['stop_reason'] == 'search_budget_reached'
    assert result['candidates']


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
            assert set(kwargs["unary_operators"]) == {"sin", "cos", "exp", "log", "sqrt", "abs"}
        def fit(self, *args, **kwargs): self.equations_ = Rows([])
    records = [physical_probe("a", (1., 0.)), physical_probe("b", (0., 1.)),
               physical_probe("c", (-1., 2.))]
    result = run_search(records, time_budget_seconds=15, model_factory=EmptySearch)
    best = result["candidates"][0]
    assert all(source in ('linear_least_squares', 'regression_basis') for source in best['component_sources'])
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
    before = [c['candidates'] for c in checkpoints if not c['candidate_selection']['selection_incomplete']][-1]
    assert before
    assert result["candidates"] == before
    assert result["candidate_selection"]["selection_incomplete"] is True
    assert result["candidate_selection"]["retained_checkpoint"] is True
    assert all(c["short_rollout_check"]["status"] == "passed" for c in result["candidates"])
    assert any(r["source"].replace(' ', '') == "vx/t" for r in result["axis_equations"]["ax"])
    assert next(r for r in result["axis_equations"]["ax"] if r["source"].replace(' ', '') == "vx/t")["domain_valid"] is None


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


def sharing_probes(second_cross_coefficient=.35):
    from scipy.integrate import solve_ivp
    records = []
    for index, initial in enumerate(([1.,2.,.3,-.2], [-2.,.5,-.4,.7], [.4,-1.5,.8,.1])):
        t = np.linspace(0, .8, 81)
        def rhs(time, z):
            x,y,vx,vy=z
            return [vx,vy,.8*x+.35*y+.21*vx,
                    second_cross_coefficient*x+.65*y-.45*vy]
        z = solve_ivp(rhs,(0,t[-1]),initial,t_eval=t,rtol=1e-12,atol=1e-14).y.T
        records.append({"probe_id":f"sharing_{index}","times":t.tolist(),
                        "r_obs":z[:,:2].tolist(),"v_obs":z[:,2:].tolist(),
                        "initial_conditions":{"r0":initial[:2],"v0":initial[2:],"t0":0,"properties":{}}})
    return records


def test_near_repeated_coefficients_are_jointly_fitted_and_checked_before_sharing():
    import time
    from shore_agent.symbolic_regression import _parameter_sharing
    data=prepare_dataset(sharing_probes())
    raw=export_candidate("0.8*x+0.3502*y+0.21*vx","0.3498*x+0.65*y-0.45*vy",
                         data["feature_names"],_parameter_limit=24)
    shared=_parameter_sharing(raw,data,time.monotonic()+3)
    assert len(raw["parameter_spec"]) == 6
    assert len(shared["parameter_spec"]) == 5
    audit=shared["parameter_sharing"]
    assert audit["status"] == "data_validated"
    assert audit["uncompressed_law_spec"] == raw["law_spec"]
    assert audit["uncompressed_parameter_spec"] == raw["parameter_spec"]
    assert audit["fit_evaluations"] > 1
    assert audit["heldout_discovery_probe_ids"] == ["sharing_2"]
    assert all(c["passed"] for c in audit["split_checks"])
    assert any(len(group["original_parameters"]) == 2 for group in audit["groups"])
    assert audit["independent_validation"] is False
    Expression(shared["law_spec"],shared["parameter_spec"])


def test_close_but_distinct_true_coefficients_are_not_silently_merged():
    import time
    from shore_agent.symbolic_regression import _parameter_sharing
    data=prepare_dataset(sharing_probes(second_cross_coefficient=.36))
    raw=export_candidate("0.8*x+0.35*y+0.21*vx","0.36*x+0.65*y-0.45*vy",
                         data["feature_names"],_parameter_limit=24)
    with pytest.raises(SymbolicRegressionError,match="sharing_data_rejected"):
        _parameter_sharing(raw,data,time.monotonic()+3)


def test_infeasible_low_loss_pairs_do_not_consume_joint_fit_slots(monkeypatch):
    import time
    from shore_agent import symbolic_regression as sr
    data=prepare_dataset(sharing_probes())
    # Isolate pair scheduling from the already-tested axis scoring. Four nominally
    # lower-loss, larger search trees have too few compatible coefficient groups.
    simple="0.8*x+0.3502*y+0.21*vx"
    left=[{"source":simple+f"+{offset}*sin(0.17*t)","complexity":24+i,
           "parameter_count":5,"loss":i*1e-12,"origin":"pysr"}
          for i,offset in enumerate((.0001,.0002,.0003,.0004))]
    left.append({"source":simple,"complexity":11,"parameter_count":3,"loss":1e-6,"origin":"pysr"})
    right=[{"source":"0.3498*x+0.65*y-0.45*vy","complexity":11,
            "parameter_count":3,"loss":0.,"origin":"pysr"}]
    monkeypatch.setattr(sr,"_prepare_axis",lambda rows,*args:rows)
    real_share=sr._parameter_sharing
    fitted=[]
    def share(candidate,*args):
        fitted.append(candidate)
        return real_share(candidate,*args)
    monkeypatch.setattr(sr,"_parameter_sharing",share)
    candidates,audit=sr._select_candidates([left,right],data,3,time.monotonic()+3,{})
    assert len(fitted)==1
    assert len(fitted[0]["parameter_spec"])==6
    assert len(candidates)==1
    assert candidates[0]["parameter_sharing"]["status"]=="data_validated"
    selection=audit["candidate_selection"]
    assert selection["sharing_fit_attempts_this_selection"]==1
    assert selection["sharing_proposal_prefilter_rejections_this_selection"]==4
    assert selection["sharing_unattempted_pairs"]==0


def test_sharing_fit_queue_keeps_simple_candidate_beside_lower_losses(monkeypatch):
    import time
    from shore_agent import symbolic_regression as sr
    data=prepare_dataset(sharing_probes())
    simple="0.8*x+0.3502*y+0.21*vx"
    # Added repetitions can be proposed for sharing, so they consume real fit
    # slots if attempted. Simulate data rejection and verify complexity diversity.
    left=[{"source":simple+f"+0.35*sin(0.35*t+{offset})","complexity":30+i,
           "parameter_count":6,"loss":i*1e-12,"origin":"pysr"}
          for i,offset in enumerate((.35,.3501,.3502,.3503,.3504))]
    left.append({"source":simple,"complexity":11,"parameter_count":3,"loss":1e-6,"origin":"pysr"})
    right=[{"source":"0.3498*x+0.65*y-0.45*vy","complexity":11,
            "parameter_count":3,"loss":0.,"origin":"pysr"}]
    monkeypatch.setattr(sr,"_prepare_axis",lambda rows,*args:rows)
    real_share=sr._parameter_sharing
    sizes=[]
    def share(candidate,*args):
        sizes.append(len(candidate["parameter_spec"]))
        if sizes[-1]>6: raise SymbolicRegressionError("sharing_data_rejected")
        return real_share(candidate,*args)
    monkeypatch.setattr(sr,"_parameter_sharing",share)
    candidates,audit=sr._select_candidates([left,right],data,3,time.monotonic()+3,{})
    assert sizes[:2]==[9,6]
    assert len(sizes)<=6
    assert len(candidates)==1
    assert candidates[0]["parameter_sharing"]["status"]=="data_validated"
    assert audit["candidate_selection"]["sharing_unattempted_pairs"]==6-len(sizes)


def test_public_axis_first_pair_gets_fit_before_loss_and_complexity_extremes(monkeypatch):
    import time
    from shore_agent import symbolic_regression as sr
    data=prepare_dataset(sharing_probes())
    good="0.8*x+0.3502*y+0.21*vx"
    left=[{"source":good+f"+0.35*sin(0.35*t+{offset})","complexity":30+i,
           "parameter_count":6,"loss":i*1e-12,"origin":"pysr"}
          for i,offset in enumerate((.35,.3501,.3502,.3503,.3504))]
    left.extend([
        {"source":good,"complexity":11,"parameter_count":3,"loss":1e-6,"origin":"pysr"},
        {"source":"0.8*x+0.35*y+0.21*vy","complexity":8,"parameter_count":3,"loss":1.,"origin":"pysr"}])
    right=[{"source":"0.3498*x+0.65*y-0.45*vy","complexity":11,
            "parameter_count":3,"loss":0.,"origin":"pysr"}]
    monkeypatch.setattr(sr,"_prepare_axis",lambda rows,*args:rows)
    monkeypatch.setattr(sr,"_differencing_tolerance",lambda dataset:np.array([1e-5,1e-5]))
    real_share=sr._parameter_sharing
    fitted=[]
    def share(candidate,*args):
        fitted.append(candidate["law_spec"]["ax"])
        if len(candidate["parameter_spec"])>6 or "vy" in candidate["law_spec"]["ax"]:
            raise SymbolicRegressionError("sharing_data_rejected")
        return real_share(candidate,*args)
    monkeypatch.setattr(sr,"_parameter_sharing",share)
    candidates,audit=sr._select_candidates([left,right],data,3,time.monotonic()+3,{})
    assert audit["axis_candidates"]["ax"][0]["source"]==good
    assert fitted[0]==export_candidate(good,"0",data["feature_names"])["law_spec"]["ax"]
    assert len(fitted)<=6
    assert audit["candidate_selection"]["sharing_public_axis_pair_prioritized"] is True
    assert len(candidates)==1
    assert candidates[0]["parameter_sharing"]["status"]=="data_validated"


def test_full_axis_formulas_survive_even_when_joint_parameter_sharing_fails():
    import time
    from shore_agent.symbolic_regression import _select_candidates, validate_axis_candidate
    data=prepare_dataset(sharing_probes(second_cross_coefficient=.36))
    rows=[[{"source":"0.8*x+0.35*y+0.21*vx","complexity":11,"origin":"pysr"}],
          [{"source":"0.36*x+0.65*y-0.45*vy","complexity":11,"origin":"pysr"}]]
    candidates,audit=_select_candidates(rows,data,3,time.monotonic()+3,{})
    assert candidates == []
    assert audit["rejection_counts"]["sharing_data_rejected"] == 1
    for component in ("ax","ay"):
        axis=audit["axis_candidates"][component]
        assert len(axis)==1
        assert axis[0]["joint_fit_ready"] is False
        assert axis[0]["parameter_count"]==3
        validate_axis_candidate(axis[0],component)


def test_axis_with_more_than_five_coefficients_is_safe_readable_output():
    import time
    from shore_agent.symbolic_regression import _select_candidates, validate_axis_candidate
    data=prepare_dataset([physical_probe("p",(1.,2.))])
    source="0.1*x+0.2*y+0.3*t+0.4*vx+0.5*vy+0.6*x*y"
    rows=[[{"source":source,"complexity":25,"origin":"pysr"}],
          [{"source":"0","complexity":1,"origin":"pysr"}]]
    _,audit=_select_candidates(rows,data,3,time.monotonic()+3,{})
    axis=audit["axis_candidates"]["ax"][0]
    assert axis["parameter_count"]==6
    assert axis["parameter_budget_compatible"] is False
    assert axis["joint_fit_ready"] is False
    validate_axis_candidate(axis,"ax")
    tampered=copy.deepcopy(axis);tampered["parameter_spec"][0]["initial"]+=1
    with pytest.raises(SymbolicRegressionError):validate_axis_candidate(tampered,"ax")
    assert axis["prediction_accuracy_status"] == "not_independently_validated"


def test_search_size_includes_larger_generic_expressions_and_retains_full_operator_set():
    from shore_agent.symbolic_regression import SEARCH_MAXSIZE
    options=[]
    class EmptySearch:
        def __init__(self,**kwargs):options.append(kwargs)
        def fit(self,*args,**kwargs):self.equations_=Rows([])
    result=run_search([physical_probe("p",(1.,2.))],model_factory=EmptySearch,time_budget_seconds=15)
    assert SEARCH_MAXSIZE==48
    assert {o['maxsize'] for o in options} == {24, 48}
    assert all('exp' in o['unary_operators'] for o in options)
    assert all('^' in o['binary_operators'] for o in options)
    assert any({"sin","cos","exp","log"}.issubset(o["unary_operators"]) for o in options)
    assert result["search_configuration"]["maxsize"]==48
    assert result['search_configuration']['early_unary_operators']==['sin','cos','exp','sqrt','log','abs']
    assert "executability only" in result["data_quality"]["trajectory_checks"]
    assert all(c["joint_fit_ready"] for c in result["candidates"])


def test_all_elementary_candidates_are_available_from_the_first_compact_stage():
    options=[]
    class EarlyOnlySearch:
        def __init__(self,**kwargs):
            options.append(kwargs)
        def fit(self,*args,**kwargs):
            if len(options)>1:
                raise RuntimeError('stop_after_first_stage_for_test')
            assert options[0]['unary_operators']==['sin','cos','exp','sqrt','log','abs']
            assert '^' in options[0]['binary_operators']
            self.equations_=Rows([{'loss':.01,'complexity':5,'sympy_format':source}
                for source in ('exp(-0.23*x)','sin(0.23*x)','cos(0.23*x)','log(x*x+0.4)')])
    result=run_search([probe()],time_budget_seconds=15,model_factory=EarlyOnlySearch)
    assert result['backend_error'] is True
    assert result['search_stages'][0]['stage']=='axis_0_algebra'
    for function in ('exp','sin','cos','log'):
        assert any(row['origin']=='pysr' and row['source'].startswith(function+'(')
                   and row['domain_valid'] is True for row in result['axis_equations']['ax'])


def test_axis_frontier_cap_preserves_accuracy_and_simplicity_endpoints():
    from shore_agent.symbolic_regression import _prepare_axis, MAX_EQUATIONS_PER_AXIS
    data=prepare_dataset([probe()])
    # Search complexity belongs to the original tree and can exceed a simplified
    # source spelling. These costs create 40 nondominated parameter/cost cells.
    rows=[{"source":f"{float(c)!r}*x", "complexity":23+i, "origin":"pysr"}
          for i,c in enumerate(np.linspace(1.5,2.,18))]
    rows += [{"source":f"{float(c)!r}*x+0.01*y", "complexity":1+i,"origin":"pysr"}
             for i,c in enumerate(np.linspace(.1,1.3,22))]
    audit=[]
    frontier=_prepare_axis(rows,data,0,audit)
    assert len(frontier)==MAX_EQUATIONS_PER_AXIS
    assert len(audit)==40
    from shore_agent.symbolic_algebra import expression_key
    assert any(expression_key(r["source"])==expression_key("2.0*x") for r in frontier)
    assert min(r["complexity"] for r in frontier)==1


def test_single_axis_delivery_always_keeps_lowest_loss_beside_simple_choices():
    from shore_agent.symbolic_regression import _axis_public_candidates
    data=prepare_dataset([probe()])
    rows=[{"source":f"{value}.0*x","complexity":cost,"loss":loss,"parameter_count":1,"origin":"pysr"}
          for value,cost,loss in ((1,1,3.),(3,2,2.),(4,3,1.),(2,10,0.))]
    result=_axis_public_candidates([rows,rows],data,[10.,10.])
    for axis in ("ax","ay"):
        assert len(result[axis])==3
        assert "2.0*x" in {r["source"] for r in result[axis]}
        assert "1.0*x" in {r["source"] for r in result[axis]}


def test_partial_nonempty_selection_cannot_replace_complete_certified_checkpoint(monkeypatch):
    from shore_agent import symbolic_regression as sr
    good=dict(export_candidate("0.1*x","0.2*y",["x","y"]),
              normalized_acceleration_search_loss=.01,short_rollout_check={"status":"passed"})
    bad=dict(export_candidate("4.0*x","5.0*y",["x","y"]),
             normalized_acceleration_search_loss=100.,short_rollout_check={"status":"passed"})
    selections=[0]
    def selection(*args,**kwargs):
        selections[0]+=1
        complete=selections[0]==1
        pair=good if complete else bad
        return ([copy.deepcopy(pair)] if complete else [copy.deepcopy(pair)]*3,
                {"axis_candidates":{"ax":[{"source":"good" if complete else "bad"}],"ay":[]},
                 "candidate_selection":{"selection_incomplete":not complete,"retained_checkpoint":False}})
    monkeypatch.setattr(sr,"_select_candidates",selection)
    class EmptySearch:
        def __init__(self,**kwargs):pass
        def fit(self,*args,**kwargs):self.equations_=Rows([])
    result=run_search([probe()],model_factory=EmptySearch,time_budget_seconds=15)
    assert len(result["candidates"])==1
    assert all(result["candidates"][0][key]==value for key,value in good.items())
    assert result["axis_candidates"]["ax"][0]["source"]=="good"
    assert result["candidate_selection"]["retained_checkpoint"] is True


@pytest.mark.parametrize("source",["1/exp(1000*x)","1/(1000000000000.0*x)","1**33"])
def test_vector_domain_guard_rejects_intermediate_overflow_and_excessive_powers(source):
    from shore_agent.symbolic_regression import _evaluate_array
    with pytest.raises(SymbolicRegressionError):
        _evaluate_array(source,{"x":np.array([2.])})


def test_selection_cannot_consume_trajectory_refit_reserve(monkeypatch):
    from shore_agent import symbolic_regression as sr
    clock=[100.0]; deadlines=[]; finalized=[]
    monkeypatch.setattr(sr.time,'monotonic',lambda:clock[0])
    candidate=dict(export_candidate('0.1*x','0.2*y',['x','y']),
                   normalized_acceleration_search_loss=.01,short_rollout_check={'status':'passed'})
    def selection(rows,dataset,limit,deadline,cache):
        deadlines.append(deadline)
        cache['refinement_candidates']=[copy.deepcopy(candidate)]
        clock[0]=deadline
        return [copy.deepcopy(candidate)],{'axis_candidates':{},'candidate_selection':{
            'selection_incomplete':True,'retained_checkpoint':False}}
    monkeypatch.setattr(sr,'_select_candidates',selection)
    monkeypatch.setattr(sr,'_refine_final_candidates',lambda report,data,deadline,**kw:finalized.append(deadline-clock[0]))
    class EmptySearch:
        def __init__(self,**kwargs): pass
        def fit(self,*args,**kwargs): self.equations_=Rows([])
    run_search([probe()],model_factory=EmptySearch,time_budget_seconds=30)
    assert deadlines and max(deadlines)<=122.5
    assert finalized and finalized[0]>=7.5


def test_parameter_ties_compare_same_split_refits(monkeypatch):
    import scipy.optimize,time
    from shore_agent.symbolic_regression import _parameter_sharing
    original=scipy.optimize.least_squares;calls=[]
    def capture(fun,x0,*args,**kwargs):
        calls.append((len(x0),kwargs['args'][0].copy()))
        return original(fun,x0,*args,**kwargs)
    monkeypatch.setattr(scipy.optimize,'least_squares',capture)
    data=prepare_dataset(sharing_probes())
    raw=export_candidate('0.8*x+0.3502*y+0.21*vx','0.3498*x+0.65*y-0.45*vy',
                         data['feature_names'],_parameter_limit=24)
    result=_parameter_sharing(raw,data,time.monotonic()+3)
    assert [n for n,_ in calls]==[5,6,5]
    assert np.array_equal(calls[0][1],calls[1][1]) and not calls[0][1].all()
    assert calls[2][1].all()
    assert result['parameter_sharing']['split_baseline']=='unconstrained_parameters_refitted_on_same_training_split'


def test_joint_scalar_counterparts_survive_different_axis_shortlists(monkeypatch):
    import time
    from shore_agent import symbolic_regression as sr
    data=prepare_dataset([physical_probe('p',(1.,2.))])
    left=[{'source':f'({v}*x)*x','complexity':6,'loss':i,'domain_valid':True,
           'parameter_count':1,'search_representation':'radial_full'} for i,v in enumerate((.1,.2))]
    right=[dict(row,source=row['source'][:-1]+'y') for row in left]
    def prepare(rows,dataset,axis,audit,*args):
        audit.extend(rows)
        return [rows[axis]]
    monkeypatch.setattr(sr,'_prepare_axis',prepare)
    result,audit=sr._select_candidates([left,right],data,3,time.monotonic()+3,{})
    assert audit['candidate_selection']['axis_frontier_counts']==[2,2]
