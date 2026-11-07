"""Diagnostic isolation and accounting tests; no real PySR or vendor worlds."""
import copy

import numpy as np
import pytest

from deployment import check_symbolic_identifiability as diagnostic


def marker_dataset():
    result = {'world_id':'opaque_diagnostic_id', 'exact_acceleration':{}}
    for split, offset in (('train',0),('heldout',10)):
        probes, exact = [], {}
        for index in range(2):
            times = np.arange(5)*.02 + offset + index
            velocity = np.array([.1+index*.1,.3+index*.1])
            positions = np.array([1.+index,2.+index]) + (times-times[0])[:,None]*velocity
            name = f'{split}_{index}'
            probes.append({'probe_id':name, 'times':times.tolist(), 'r_obs':positions.tolist(),
                           'v_obs':np.tile(velocity,(5,1)).tolist(),
                           'initial_conditions':{'r0':positions[0].tolist(),'v0':velocity.tolist(),
                                                 't0':float(times[0]),'properties':{'mass':1.+index,'charge':2.+index}}})
            exact[name] = {'times':times[1:-1].tolist(),'values':[[7.,11.]]*3}
        result[split+'_probes'] = probes
        result['exact_acceleration'][split] = exact
    return result


def test_exact_labels_align_without_entering_production_probe_records():
    dataset = marker_dataset()
    before = copy.deepcopy(dataset)
    prepared, exact = diagnostic.aligned_data(dataset,'train')
    assert prepared['feature_names'] == diagnostic.FEATURES
    np.testing.assert_allclose(prepared['y'],0,atol=1e-12)
    np.testing.assert_array_equal(exact,np.tile([7.,11.],(6,1)))
    assert dataset == before
    dataset['exact_acceleration']['train']['train_0']['times'][0] += .01
    with pytest.raises(ValueError,match='align'):
        diagnostic.aligned_data(dataset,'train')


def test_direct_backend_receives_exact_numeric_labels_only(tmp_path):
    captures = []
    class Rows:
        def __init__(self, source): self.source=source
        def iterrows(self):
            return iter([(0,{'loss':0.,'complexity':1,'sympy_format':self.source})])
    class FakeModel:
        def __init__(self, **options): self.options=options
        def fit(self, X, y, **kwargs):
            captures.append((self.options,X.copy(),y.copy(),copy.deepcopy(kwargs)))
            self.equations_ = Rows('7.0' if len(captures)==1 else '11.0')
    dataset = marker_dataset()
    checkpoints=[]
    result = diagnostic.direct_search(dataset,'A_exact',tmp_path,lambda r:checkpoints.append(copy.deepcopy(r)),FakeModel)
    assert result['search_axes_completed'] == ['ax','ay'] and len(captures)==2
    for index,(options,X,y,kwargs) in enumerate(captures):
        np.testing.assert_array_equal(y,np.full(6,[7.,11.][index]))
        assert options['maxsize']==48
        assert options['random_state']==42+index
        assert kwargs['variable_names']==diagnostic.FEATURES
        assert set(kwargs)=={'weights','variable_names'}
        assert 'opaque_diagnostic_id' not in str(options)+str(kwargs)
    assert set(dataset['train_probes'][0])=={'probe_id','times','r_obs','v_obs','initial_conditions'}
    assert checkpoints[-1]['elapsed_seconds']<=diagnostic.SEARCH_SECONDS
    exact_captures=captures[:]
    captures.clear()
    diagnostic.direct_search(dataset,'B_velocity_difference',tmp_path,lambda r:None,FakeModel)
    for first,second in zip(exact_captures,captures):
        assert first[0]==second[0]
        np.testing.assert_array_equal(first[1],second[1])
        np.testing.assert_array_equal(first[3]['weights'],second[3]['weights'])
        np.testing.assert_allclose(second[2],0,atol=1e-12)
        assert first[0]['timeout_in_seconds']==30


def test_holdout_is_scored_but_never_selects_raw_equation():
    dataset=marker_dataset()
    result={'axis_equations':{'ax':[{'source':'7.0','loss':0.,'complexity':1,'origin':'pysr'},
                                  {'source':'70.0','loss':1.,'complexity':1,'origin':'pysr'}],
                             'ay':[{'source':'11.0','loss':0.,'complexity':1,'origin':'pysr'}]}}
    first=diagnostic.evaluate_search(result,dataset)
    for exact in dataset['exact_acceleration']['heldout'].values():
        exact['values']=[[70.,110.]]*3
    second=diagnostic.evaluate_search(result,dataset)
    assert first['axes']['ax']['lowest_training_loss_raw_pysr']['source']=='7.0'
    assert second['axes']['ax']['lowest_training_loss_raw_pysr']['source']=='7.0'
    assert first['raw_training_best_pair']['heldout']['nrmse']==0
    assert second['raw_training_best_pair']['heldout']['nrmse']==pytest.approx(.9)
    assert second['heldout_used_for_search_or_selection'] is False


def test_metric_uses_energy_weighted_vector_normalization():
    values=np.array([[3.,4.],[3.,4.]])
    metrics=diagnostic.acceleration_metrics(np.zeros_like(values),values,np.array([.25,.75]))
    assert metrics['nrmse']==1.
    assert metrics['mse_by_axis']==[9.,16.]
    assert diagnostic.acceleration_metrics(np.full_like(values,np.nan),values,np.ones(2))['status']=='invalid_prediction'


def test_raw_backend_metrics_survive_production_export_rejection():
    source='+'.join(f'{i/100}*x' for i in range(1,31))
    result={'axis_equations':{'ax':[{'source':source,'loss':0.,'complexity':48,'origin':'pysr'}],
                             'ay':[{'source':'11.0','loss':0.,'complexity':1,'origin':'pysr'}]}}
    report=diagnostic.evaluate_search(result,marker_dataset())
    raw_pair=report['raw_training_best_pair']
    assert raw_pair['export_status']=='rejected'
    assert raw_pair['heldout']['status']=='finite'
    assert raw_pair['heldout']['nrmse'] is not None


def test_runtime_requires_existing_local_julia_and_sets_both_thread_controls(tmp_path):
    with pytest.raises(ValueError,match='existing executable'):
        diagnostic.runtime_environment({})
    julia=tmp_path/'julia'
    julia.write_text('placeholder')
    with pytest.raises(ValueError,match='existing executable'):
        diagnostic.runtime_environment({'PYTHON_JULIAPKG_EXE':str(julia)})
    julia.chmod(0o700)
    environment=diagnostic.runtime_environment({'PYTHON_JULIAPKG_EXE':str(julia),
                                                'PYTHON_JULIACALL_THREADS':'192',
                                                'PYTHON_JULIAPKG_OFFLINE':'no'})
    assert environment['PYTHON_JULIAPKG_OFFLINE']=='yes'
    assert environment['PYTHON_JULIACALL_THREADS']==environment['JULIA_NUM_THREADS']=='4'
    assert environment['OPENBLAS_NUM_THREADS']==environment['OMP_NUM_THREADS']=='1'
