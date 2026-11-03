"""Numerical tests use independently specified toy laws, never simulator truth."""
import ast
from pathlib import Path

import numpy as np
import pytest

from shore_agent.expressions import Expression, ExpressionError
from shore_agent.numerics import NumericalError, errors_for_rollouts, fit, rollout


def constant_acceleration_probe(probe_id="p1", n=31, t0=3.0, acceleration=(0.7, -0.4)):
    times = t0 + np.linspace(0, 2, n)
    tau = (times - t0)[:, None]
    r0, v0 = np.asarray([1.5, -2.0]), np.asarray([-0.2, 0.8])
    a = np.asarray(acceleration)
    return {"probe_id": probe_id,
            "initial_conditions": {"r0": r0.tolist(), "v0": v0.tolist(), "properties": {}, "t0": t0},
            "times": times.tolist(), "r_obs": (r0 + tau * v0 + 0.5 * tau ** 2 * a).tolist(),
            "v_obs": (v0 + tau * a).tolist()}


def test_full_state_and_public_body_and_property_dependencies():
    expr = Expression({"ax": "k*y+sin(t)+vx*q('mass')+sum_b(by-x)",
                       "ay": "-k*x+vy+sum_b(bx-y)"}, [{"name": "k", "initial": 0.5}])
    actual = expr.acceleration(0.0, [2, 3], [4, 5], [{"body_id": "test", "position": [7, 8]}], {"mass": 2}, {"k": 0.5})
    np.testing.assert_allclose(actual, [15.5, 8])


@pytest.mark.parametrize("formula", [
    "__import__('os')", "x.__class__", "x[0]", "[x for x in y]", "sum_b(sum_b(bx))",
    "bx", "unknown*x", "q('secret')", "0.125*x", "9*x", "(1+1)*x", "sin(1)*x",
    "x+1", "x if t else y", "(lambda: x)()", "True", "x//y", "sum_b(1)",
])
def test_unsafe_or_hidden_constant_syntax_is_rejected(formula):
    with pytest.raises(ExpressionError):
        Expression({"ax": formula, "ay": "0"}, [])


def test_parameter_rules_and_declared_limit():
    with pytest.raises(ExpressionError):
        Expression({"ax": "x", "ay": "0"}, [{"name": "x", "initial": 1}])
    with pytest.raises(ExpressionError):
        Expression({"ax": "a+b+c+d+e+f", "ay": "0"}, [{"name": name, "initial": 1} for name in "abcdef"])
    with pytest.raises(ExpressionError):
        Expression({"ax": "a", "ay": "0"}, [{"name": "a", "initial": 2, "lower": 0, "upper": 1}])
    with pytest.raises(ExpressionError):
        Expression({"ax": "0", "ay": "0"}, [{"name": "unused", "initial": 1}])


def test_integer_power_and_domain_errors():
    expr = Expression({"ax": "x**2", "ay": "y**-3"}, [])
    np.testing.assert_allclose(expr.acceleration(0, [3, 2], [0, 0], [], {}, {}), [9, 0.125])
    with pytest.raises(ExpressionError):
        expr.acceleration(0, [3, 0], [0, 0], [], {}, {})
    with pytest.raises(ExpressionError):
        Expression({"ax": "sqrt(x)", "ay": "0"}, []).acceleration(0, [-1, 0], [0, 0], [], {}, {})


def test_rollout_uses_absolute_time_and_controlled_initial_state():
    probe = constant_acceleration_probe()
    probe["r_obs"][0] = [99, 99]  # observation noise must not alter controlled initial state
    prediction = rollout({"ax": "t", "ay": "0"}, {}, probe, [])
    times = np.asarray(probe["times"])
    tau = times - 3.0
    expected_vx = -0.2 + (times ** 2 - 9) / 2
    expected_x = 1.5 - 0.2 * tau + 3 * tau ** 2 / 2 + tau ** 3 / 6
    np.testing.assert_allclose(np.asarray(prediction["r_pred"])[:, 0], expected_x, atol=1e-7)
    np.testing.assert_allclose(np.asarray(prediction["v_pred"])[:, 0], expected_vx, atol=1e-7)
    np.testing.assert_allclose(np.asarray(prediction["a_pred"])[:, 0], times)
    assert prediction["r_pred"][0] == [1.5, -2.0]


def test_parameter_fit_and_frozen_rollout():
    probes = [constant_acceleration_probe("p1", 31), constant_acceleration_probe("p2", 11, t0=7)]
    result = fit({"ax": "a", "ay": "b"}, [{"name": "a", "initial": 0}, {"name": "b", "initial": 0}], probes, [])
    assert result["converged"], result
    assert result["fitted_parameters"]["a"] == pytest.approx(0.7, abs=1e-7)
    assert result["fitted_parameters"]["b"] == pytest.approx(-0.4, abs=1e-7)
    assert result["errors"]["overall"]["position_rmse"] < 1e-7
    assert result["errors"]["overall"]["velocity_rmse"] < 1e-7
    holdout = constant_acceleration_probe("new", 9, t0=11)
    predicted = rollout({"ax": "a", "ay": "b"}, result["fitted_parameters"], holdout, [])
    np.testing.assert_allclose(predicted["r_pred"], holdout["r_obs"], atol=1e-7)


def test_equal_trajectory_weight_and_vector_rmse():
    probes = [constant_acceleration_probe("short", 2), constant_acceleration_probe("long", 50)]
    predictions = []
    for probe, delta in zip(probes, (1, 3)):
        predictions.append({"probe_id": probe["probe_id"], "times": probe["times"],
                            "r_pred": (np.asarray(probe["r_obs"]) + [delta, 0]).tolist(), "v_pred": probe["v_obs"]})
    errors = errors_for_rollouts(probes, predictions)
    assert errors["overall"]["position_rmse"] == pytest.approx(np.sqrt(5))
    assert errors["overall"]["velocity_rmse"] == 0


def test_fitting_objective_is_equal_trajectory_position_only():
    # Contradictory accelerations with 2 vs 50 samples but identical sample times
    # distribution are approximated by explicitly calculating the LS optimum.
    probes = [constant_acceleration_probe("short", 2, acceleration=(1, 0)),
              constant_acceleration_probe("long", 50, acceleration=(3, 0))]
    for probe in probes:
        probe["v_obs"] = (np.asarray(probe["v_obs"]) + 1000).tolist()
    weights = [np.mean((np.asarray(p["times"]) - 3) ** 4) for p in probes]
    expected = (weights[0] + 3 * weights[1]) / sum(weights)
    result = fit({"ax": "a", "ay": "0"}, [{"name": "a", "initial": 0}], probes, [])
    assert result["fitted_parameters"]["a"] == pytest.approx(expected, abs=1e-5)
    assert result["errors"]["overall"]["velocity_rmse"] > 100


def test_domain_failure_and_divergence_are_bounded():
    probe = constant_acceleration_probe()
    probe["initial_conditions"]["r0"] = [-1, 1]
    failed = fit({"ax": "sqrt(x)", "ay": "0"}, [], [probe], [])
    assert failed["fit_status"] == "failed"
    assert not failed["converged"]
    with pytest.raises(NumericalError):
        rollout({"ax": "k*x", "ay": "0"}, {"k": 1e8}, probe, [])


def test_fit_exhaustion_is_not_reported_as_convergence():
    result = fit({"ax": "a", "ay": "0"}, [{"name": "a", "initial": 0}],
                 [constant_acceleration_probe(acceleration=(3, 0))], [], max_nfev=1)
    assert result["fit_status"] == "not_converged"
    assert not result["converged"]


def test_rollout_honors_remaining_session_deadline(monkeypatch):
    import shore_agent.numerics as numerics
    ticks = iter([100.0, 100.001, 100.003])
    monkeypatch.setattr(numerics.time, "monotonic", lambda: next(ticks))
    with pytest.raises(NumericalError) as error:
        rollout({"ax": "0", "ay": "0"}, {}, constant_acceleration_probe(), [], timeout_seconds=0.002)
    assert error.value.code == "numerical_timeout"


def test_rollout_zero_budget_and_invalid_timeout():
    probe = constant_acceleration_probe()
    with pytest.raises(NumericalError) as error:
        rollout({"ax": "0", "ay": "0"}, {}, probe, [], timeout_seconds=0)
    assert error.value.code == "numerical_timeout"
    for timeout in (True, -1, float("inf"), float("nan")):
        with pytest.raises(NumericalError):
            rollout({"ax": "0", "ay": "0"}, {}, probe, [], timeout_seconds=timeout)


def test_time_grid_roundoff_is_normalized_but_earlier_samples_rejected():
    probe = constant_acceleration_probe(t0=2.635)
    probe["initial_conditions"]["t0"] = 527 * 0.005
    assert probe["times"][0] < probe["initial_conditions"]["t0"]
    prediction = rollout({"ax": "0", "ay": "0"}, {}, probe, [])
    assert prediction["times"] == probe["times"]
    np.testing.assert_allclose(prediction["r_pred"][0], probe["initial_conditions"]["r0"])
    probe["initial_conditions"]["t0"] += 0.005
    with pytest.raises(NumericalError, match="times must"):
        rollout({"ax": "0", "ay": "0"}, {}, probe, [])


def test_huge_parameter_integer_is_rejected_cleanly():
    with pytest.raises(ExpressionError):
        Expression({"ax": "a", "ay": "0"}, [{"name": "a", "initial": 10 ** 1000}])


def test_numerical_modules_never_import_simulator():
    folder = Path(__file__).parents[1] / "shore_agent"
    for filename in ("expressions.py", "numerics.py"):
        tree = ast.parse((folder / filename).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("shore_sim")
            elif isinstance(node, ast.Import):
                assert all(not alias.name.startswith("shore_sim") for alias in node.names)


def test_independent_evaluation_requires_accepted_ended_session(tmp_path):
    import json
    from evaluate import evaluate_run
    with pytest.raises(ValueError, match="accepted submission"):
        evaluate_run(tmp_path)
    (tmp_path / "records/submission").mkdir(parents=True)
    (tmp_path / "records/law").mkdir()
    submission = {"submission_id": "s1", "law_id": "l1", "status": "accepted", "session_ended": False,
                  "claims": {"dynamics_order": 2, "hidden_matter": False, "time_dependence": False}}
    path = tmp_path / "records/submission/s1.json"
    path.write_text(json.dumps(submission))
    with pytest.raises(ValueError, match="accepted submission"):
        evaluate_run(tmp_path)
    submission["session_ended"] = True
    path.write_text(json.dumps(submission))
    # Deliberately wrong, parameter-free straight-line candidate: evaluation must
    # report its error honestly and must not refit it against hidden trajectories.
    law = {"law_id": "l1", "law_spec": {"ax": "0", "ay": "0"},
           "fitted_parameters": {}, "known_bodies": []}
    law_path = tmp_path / "records/law/l1.json"
    law_path.write_text(json.dumps(law))
    before = law_path.read_bytes()
    # This seed exercises decimal grid values whose binary multiplication differs
    # from rounded sample times (the prior implementation failed 4/20 rollouts).
    result = evaluate_run(tmp_path, seed=1871, n_probes=20)
    assert result["complete"] and result["n_successful"] == 20
    assert result["overall"]["position_rmse"] > 1
    assert result == evaluate_run(tmp_path, seed=1871, n_probes=20)
    assert law_path.read_bytes() == before
