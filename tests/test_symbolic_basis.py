"""Numerical discovery fixtures use arbitrary data laws, never world identities."""
import copy
import time

import numpy as np
import pytest

from shore_agent.symbolic_basis import generate_basis_candidates
from shore_agent.symbolic_regression import _evaluate_array, export_candidate


def numerical_data(span=13., n=320):
    rng=np.random.default_rng(938)
    t=np.linspace(0,span,n)
    x,y,vx,vy=rng.uniform(-2,2,(4,n))
    # Reordered columns and irrelevant derived fields ensure no positional
    # assumptions or leakage from an extra feature column.
    return {"X":np.column_stack([vy,t,x,x*x+y*y,vx,y]),
            "feature_names":["vy","t","x","r2","vx","y"],
            "y":np.zeros((n,2)),"weights":np.full(n,1/n),
            "used_probe_ids":["observed_a","observed_b"]}


def table(data):
    return dict(zip(data["feature_names"],data["X"].T))


def generated(data):
    return generate_basis_candidates(data,deadline=time.monotonic()+3)


def test_sparse_cubic_proposals_recover_generic_space_velocity_interactions():
    data=numerical_data()
    z=table(data); x,y,vx,vy=(z[k] for k in ("x","y","vx","vy"))
    data["y"]=np.column_stack([.73*x+.041*x*y*y-.016*vx**3,
                               -.31*y+.041*x*x*y+.022*vy])
    before=copy.deepcopy(data)
    result=generated(data)
    for axis,rows in enumerate(result["axis_rows"]):
        best=min(rows,key=lambda row:row["basis_fit_mse"])
        assert best["origin"]=="regression_basis"
        assert best["basis_family"]=="sparse_polynomial"
        assert best["basis_fit_mse"]<1e-20
        np.testing.assert_allclose(_evaluate_array(best["source"],z),data["y"][:,axis],atol=1e-12)
        assert best["fitting_metadata"]["independent_validation"] is False
    np.testing.assert_array_equal(data["X"],before["X"])
    assert result["diagnostics"]["unused_features"]==["r2"]
    assert result["diagnostics"]["used_probe_ids"]==["observed_a","observed_b"]
    assert result["diagnostics"]["elapsed_seconds"]<3


@pytest.mark.parametrize("frequency,phase",[(.73,.41),(1.17,-.83)])
def test_common_frequency_is_estimated_and_full_formulas_remain_exportable(frequency,phase):
    data=numerical_data()
    z=table(data); t,x,y=(z[k] for k in ("t","x","y"))
    data["y"]=np.column_stack([
        -.22*x+.083*np.cos(frequency*t+phase)*x+.083*np.sin(frequency*t+phase)*y,
        -.22*y+.083*np.sin(frequency*t+phase)*x-.083*np.cos(frequency*t+phase)*y])
    result=generated(data)
    diagnostic=result["diagnostics"]["time_modulation"]
    assert diagnostic["status"]=="resolved_on_supplied_data"
    assert diagnostic["frequency"]==pytest.approx(frequency,rel=1e-5)
    sources=[]
    for axis,rows in enumerate(result["axis_rows"]):
        sparse=[row for row in rows if row["basis_family"]=="shared_frequency_linear_modulation"
                and row["fitting_metadata"]["selected_terms"]==3]
        assert sparse
        best=min(sparse,key=lambda row:row["basis_fit_mse"])
        assert best["basis_fit_mse"]<1e-12
        np.testing.assert_allclose(_evaluate_array(best["source"],z),data["y"][:,axis],atol=1e-5)
        sources.append(best["source"])
    exported=export_candidate(*sources,["t","x","y","vx","vy"],_parameter_limit=24)
    assert len(exported["parameter_spec"])<=24
    assert all(len(source)<600 for source in exported["law_spec"].values())


def test_short_local_time_window_does_not_guess_unobserved_slow_frequency():
    data=numerical_data(span=.25)
    z=table(data); t,x,y=(z[k] for k in ("t","x","y"))
    data["y"]=np.column_stack([(.2+.04*np.sin(.73*t+.41))*x,
                               (.1+.07*np.cos(.73*t+.41))*y])
    result=generated(data)
    assert result["diagnostics"]["time_modulation"]["status"]=="unresolved"
    assert not any(row["basis_family"]=="shared_frequency_linear_modulation"
                   for rows in result["axis_rows"] for row in rows)


def test_too_few_times_report_unidentifiable_without_time_candidates():
    data=numerical_data(n=9)
    z=table(data)
    data["y"]=np.column_stack([.3*z["x"],-.27*z["y"]])
    result=generated(data)
    assert result["diagnostics"]["time_modulation"]["reason"]=="insufficient_distinct_times"


def test_expired_deadline_returns_without_numerical_work():
    result=generate_basis_candidates(numerical_data(),deadline=time.monotonic()-1)
    assert result["axis_rows"]==[[],[]]
    assert result["diagnostics"]["budget_exhausted"] is True
    assert result["diagnostics"]["elapsed_seconds"]<.1


def test_axis_limit_and_finite_data_validation():
    data=numerical_data()
    z=table(data)
    data["y"]=np.column_stack([.3*z["x"]-.02*z["vy"]**3,-.27*z["y"]+.004*z["x"]**2])
    result=generate_basis_candidates(data,deadline=time.monotonic()+3,max_candidates_per_axis=2)
    assert all(len(rows)<=2 for rows in result["axis_rows"])
    data["X"][0,0]=float("nan")
    with pytest.raises(ValueError,match="finite"):
        generated(data)


def test_polynomial_stage_timeout_keeps_completed_lower_degree_candidates(monkeypatch):
    from shore_agent import symbolic_basis as basis
    data=numerical_data()
    z=table(data)
    data["y"]=np.column_stack([.3*z["x"],-.27*z["y"]])
    original=basis._sparse_paths
    calls=[]
    def bounded_path(*args,**kwargs):
        calls.append(1)
        if len(calls)>1: raise basis._Deadline
        return original(*args,**kwargs)
    monkeypatch.setattr(basis,"_sparse_paths",bounded_path)
    monkeypatch.setattr(basis,"_periodic",lambda *args:([[],[]],{"status":"unresolved"}))
    result=generated(data)
    assert all(result["axis_rows"])
    assert result["diagnostics"]["polynomial"]["status"]=="budget_exhausted"
    assert all(min(row["basis_fit_mse"] for row in rows)<1e-20 for rows in result["axis_rows"])


def test_sparse_observation_windows_report_temporal_alias_risk():
    data=numerical_data()
    z=table(data)
    t=np.concatenate([np.linspace(0,1,160),np.linspace(9,10,160)])
    data["X"][:,data["feature_names"].index("t")]=t
    data["y"]=np.column_stack([(.2+.04*np.sin(.73*t+.41))*z["x"],
                               (.1+.07*np.cos(.73*t+.41))*z["y"]])
    result=generated(data)
    diagnostic=result["diagnostics"]["time_modulation"]
    assert diagnostic["temporal_alias_risk"] is True
    assert diagnostic["maximum_observation_gap"]==pytest.approx(8.)
    assert diagnostic["independent_validation"] is False


def test_nonfinite_deadline_cannot_disable_time_limit():
    with pytest.raises(ValueError,match="deadline"):
        generate_basis_candidates(numerical_data(),deadline=float("nan"))


def test_valid_minimal_probe_data_skips_basis_without_failing_the_search():
    data={"X":np.empty((1,0)),"feature_names":[],"y":np.zeros((1,2)),"weights":np.ones(1)}
    result=generated(data)
    assert result["axis_rows"]==[[],[]]
    assert result["diagnostics"]["reason"]=="insufficient_derivative_samples"
