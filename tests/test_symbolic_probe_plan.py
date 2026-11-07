import copy

import pytest

from shore_agent.symbolic_guidance import build_probe_plan_review, build_review


def probe(t0=0., *, speed=1.):
    return {'initial_conditions':{'r0':[1.,0.],'v0':[speed,0.],'properties':{'mass':1.},'t0':t0},
            'times':[t0,t0+1,t0+2], 'r_obs':[[1.,0.],[1+speed,.01],[1+2*speed,.04]],
            'v_obs':[[speed,0.],[speed,.02],[speed,.04]]}


def scenario():
    records={'probe':{'p':probe()},'law':{},'validation':{}}
    budget={'energy_remaining':4,'wall_seconds_remaining':200,'session_ended':False}
    task={'time_grid':.005,'physical_time_range':[0,30],
          'maximum_single_trajectory_duration':10,'position_noise_sigma':0,'reference_length':1,
          'limits':{'probe_energy':1}}
    control={'r0':[1.,0.],'v0':[1.,0.],'properties':{'mass':1.}}
    args={'probes':[control,copy.deepcopy(control)],'t0':0.,'dt':1.,'n_samples':3}
    return records,budget,task,args


def test_last_training_batch_review_is_pure_and_suggests_dynamic_grid_times():
    values=scenario();before=copy.deepcopy(values)
    review=build_probe_plan_review(*values)
    assert review['energy_after_proposed_batch']==2
    assert review['training_energy_capacity_preserving_two']==2
    assert review['suggested_delayed_launch_times']==[6.,18.]
    assert review['duplicate_proposed_indexes']==[0,1]
    reused=review['recommended_same_state_time_control']
    assert reused['existing_probe_id']=='p'
    assert reused['probes'][0]==values[3]['probes'][0]
    assert reused['t0_location']=='batch_top_level'
    assert 't0' not in reused['probes'][0]
    assert review['tool_executed'] is False
    assert values==before


def test_advice_respects_horizon_and_maximum_duration():
    records,budget,task,args=scenario()
    task.update(physical_time_range=[0,8.003],maximum_single_trajectory_duration=1.2,time_grid=.1)
    review=build_probe_plan_review(records,budget,task,args)
    assert review['suggested_delayed_launch_times']==[6.,6.8]
    assert all(t+review['legal_time_constraints']['suggested_window_duration']<=8.003
               and t/.1==pytest.approx(round(t/.1)) for t in review['suggested_delayed_launch_times'])


def test_time_contrast_is_complete_state_control_and_avoids_unnecessary_review():
    records,budget,task,args=scenario()
    records['probe']['delayed']=probe(6.)
    args['probes']=[{'r0':[2.,1.],'v0':[.5,.1],'properties':{'mass':1.}},
                    {'r0':[-2.,1.],'v0':[.5,.1],'properties':{'mass':1.}}]
    assert build_probe_plan_review(records,budget,task,args) is None
    records['probe']['delayed']['initial_conditions']['properties']['mass']=2.
    assert build_probe_plan_review(records,budget,task,args) is not None


def test_longer_or_denser_sampling_is_not_labeled_complete_duplicate():
    records,budget,task,args=scenario();args['probes']=args['probes'][:1]
    budget['energy_remaining']=3
    args.update(dt=.5,n_samples=5)
    review=build_probe_plan_review(records,budget,task,args)
    assert review['duplicate_proposed_indexes']==[]
    assert 'spending_last_training_energy_without_delayed_same_state_control' in review['reasons']


@pytest.mark.parametrize('change',[{'energy_remaining':10},{'wall_seconds_remaining':20},{'session_ended':True}])
def test_no_review_before_trigger_or_after_deadline(change):
    records,budget,task,args=scenario();budget.update(change)
    assert build_probe_plan_review(records,budget,task,args) is None


def test_validation_worsening_and_acceleration_induced_scale_are_exposed():
    records,budget,task,_=scenario()
    records['probe']['check']=probe(4.,speed=100.)
    records['law']['selected']={'train_probe_ids':['p'],'fit_status':'converged',
                                'errors':{'overall':{'position_rmse':.001}}}
    records['validation']['v']={'law_id':'selected','errors':{'per_probe':[{'probe_id':'check','position_rmse':.01}]}}
    review=build_review(records,budget,task,law_id='selected')
    evidence=review['validation_evidence'][0]
    assert evidence['relative_to_observed_change']<.001
    assert evidence['relative_to_departure_from_uniform_motion']>.2
    assert evidence['relative_to_training_residual']==10.
    assert 'validation_at_least_five_times_training_residual' in evidence['diagnostic_cues']
    assert 'not an official threshold' in evidence['interpretation']


def test_training_relative_warning_does_not_override_noise_or_numerical_floor():
    records,budget,task,_=scenario();records['law']['selected']={'train_probe_ids':['p'],
        'errors':{'overall':{'position_rmse':1e-12}}}
    records['validation']['v']={'law_id':'selected','errors':{'per_probe':[{'probe_id':'p','position_rmse':1e-10}]}}
    assert build_review(records,budget,task,law_id='selected')['validation_evidence']==[]
    task['position_noise_sigma']=.1
    records['validation']['v']['errors']['per_probe'][0]['position_rmse']=.1
    assert build_review(records,budget,task,law_id='selected')['validation_evidence']==[]


def test_nearly_free_motion_numerical_error_is_not_an_adverse_validation():
    records,budget,task,_=scenario()
    records['probe']['p']['r_obs']=[[1.,0.],[2.,0.],[3.,0.]]
    records['law']['selected']={'train_probe_ids':['p'],'errors':{'overall':{'position_rmse':1e-12}}}
    records['validation']['v']={'law_id':'selected','errors':{'per_probe':[{'probe_id':'p','position_rmse':1e-8}]}}
    assert build_review(records,budget,task,law_id='selected')['validation_evidence']==[]
    records['validation']['v']['errors']['per_probe'][0]['position_rmse']=.01
    evidence=build_review(records,budget,task,law_id='selected')['validation_evidence']
    assert len(evidence)==1
    assert evidence[0]['numerical_position_floor']>1e-8
