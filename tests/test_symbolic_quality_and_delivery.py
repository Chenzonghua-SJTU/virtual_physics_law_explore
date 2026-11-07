"""Generic regressions for algebra, local data reliability and candidate delivery."""
import time
import numpy as np
from shore_agent.symbolic_algebra import normalize_polynomial,expression_key
from shore_agent.symbolic_quality import derivatives,consistency
from shore_agent.symbolic_regression import prepare_dataset,_prepare_axis,_select_candidates
from shore_agent.numerics import rollout


def test_polynomial_expansion_recovers_cross_axis_coefficient_without_domain_cancellation():
    left='y*(-0.02*(x*x+y*y)+0.013*y*y-0.4)'
    right='-0.4*y-0.02*x*x*y-0.007*y*y*y'
    assert expression_key(left)==expression_key(right)
    assert expression_key(normalize_polynomial(left))==expression_key(right)
    assert normalize_polynomial('x/x')=='x/x'
    assert expression_key('sin(x)')!=expression_key('x')
    assert expression_key('log(x*x)')!=expression_key('2*log(x)')


def test_known_velocity_noise_uses_local_regression_without_hidden_targets():
    t=np.linspace(0,1,51); rng=np.random.default_rng(19)
    velocity=np.column_stack((t*t,-2*t*t))+rng.normal(0,.01,(len(t),2))
    position=np.column_stack((t**3/3,-2*t**3/3))
    p={'probe_id':'synthetic','observation_noise':{'velocity_sigma':.01,'position_sigma':0},'a_est':[[1e9,1e9]]*49}
    _,_,estimated,quality,_,detail=derivatives(p,t,position,velocity)
    exact=np.column_stack((2*t,-4*t))[1:-1]
    raw=np.gradient(velocity,t,axis=0)[1:-1]
    assert np.mean((estimated-exact)**2)<.25*np.mean((raw-exact)**2)
    assert np.all(quality>0) and detail['method']=='local_cubic_velocity'


def test_local_underresolution_is_downweighted_without_discarding_trajectory():
    t=np.linspace(-1,1,51); v=np.column_stack((np.tanh(t/.03),t))
    r=np.column_stack((t,t*t)); p={'probe_id':'sharp'}
    _,_,_,quality,error,detail=derivatives(p,t,r,v)
    assert len(quality)==49 and np.all(quality>0)
    assert quality[24]<.1 and np.median(quality[:10])>.9
    assert detail['low_reliability_times'] and np.isfinite(error).all()


def test_observed_integral_detects_pole_omitted_by_a_small_training_subset():
    p={'probe_id':'counterexample','times':[0,.1,.2],
       'r_obs':[[1.1,0],[.9,0],[.8,0]],'v_obs':[[-1,0],[-1,0],[-1,0]],
       'initial_conditions':{'properties':{}}}
    result=consistency({'ax':'-x/(x*x-1)','ay':'0'},{},[p])
    assert result['complete'] and result['denominator_sign_change_probe_ids']==['counterexample']
    assert result['per_probe'][0]['velocity_increment_rmse']>0


def synthetic_coupled_data():
    formula={'ax':'-a*x-b*x**3-c*x*y*y',
             'ay':'-d*y-c*x*x*y-e*y**3'}
    probes=[]
    for index,(x,y) in enumerate(((1.,2.),(-2.,1.),(2.,-3.))):
        p={'probe_id':f'p{index}','times':np.linspace(0,.8,41).tolist(),
           'initial_conditions':{'r0':[x,y],'v0':[.2,-.1],'t0':0,'properties':{}}}
        output=rollout(formula,{'a':.3,'b':.004,'c':.02,'d':.4,'e':.007},p,[])
        p.update(r_obs=output['r_pred'],v_obs=output['v_pred'])
        probes.append(p)
    return prepare_dataset(probes)


def test_complete_shared_polynomial_survives_shorter_factorized_component():
    data=synthetic_coupled_data()
    rows=[[{'source':'-0.3*x-0.004*x**3-0.02*x*y*y','complexity':20,'origin':'regression_basis'}],
          [{'source':'-0.4*y-0.02*x*x*y-0.007*y**3','complexity':20,'origin':'regression_basis'},
           {'source':'y*(-0.02*(x*x+y*y)+0.013*y*y-0.4)','complexity':13,'origin':'pysr'}]]
    axes=_prepare_axis(rows[1],data,1,[])
    assert len(axes)==1
    result,_=_select_candidates(rows,data,3,time.monotonic()+5,{})
    assert result and result[0]['parameter_count']==5
    assert 'parameter_sharing' in result[0]
    assert result[0]['fitted_parameters'] and result[0]['residuals']['observed_velocity_integral']['complete']
    # Cubic self terms remain independent, unlike the cross term shared by data.
    spec=result[0]['law_spec']
    assert '** 3' in spec['ax'] and '** 3' in spec['ay']
    assert result[0]['rank']==1
