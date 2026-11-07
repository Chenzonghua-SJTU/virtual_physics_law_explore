"""Read-only log audit must not turn weak provenance into stronger evidence."""
import copy
import json

import pytest

from deployment.audit_symbolic_strategy import (
    Archive, build_audit, context_delivery, coverage, match_formula, source_class,
)


def dump(path, value, lines=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(v) for v in value) if lines else json.dumps(value))


@pytest.fixture
def saved_run(tmp_path):
    run = tmp_path/'runs'/'test-world_1'
    candidate = {'law_spec': {'ax': '-c1*x', 'ay': '-c2*y'},
                 'parameter_spec': [{'name': 'c1', 'initial': .12}, {'name': 'c2', 'initial': .24}],
                 'component_sources': ['pysr', 'linear_least_squares'],
                 'acceleration_search_mse_by_axis': [.001, .002]}
    probes = {}
    for n in range(1, 5):
        probes[f'p{n}'] = {'probe_id': f'p{n}',
                          'initial_conditions': {'r0': [2, 1], 'v0': [.1, -.1],
                                                 'properties': {'mass': 1 if n != 3 else 2},
                                                 't0': 7 if n == 2 else 0},
                          'times': [0, .1, .2], 'r_obs': [[2, 1], [2.01, .99], [2.02, .98]],
                          'v_obs': [[.1, -.1]]*3}
        dump(run/'records'/'probe'/f'p{n}.json', probes[f'p{n}'])
    search = {'search_id': 'sr_abc', 'status': 'timeout', 'used_probe_ids': ['p1', 'p2', 'p3'],
              'candidates': [candidate], 'search_configuration': {'operator_scope': 'algebra then full'},
              'search_stages': [{'stage': 'axis_0_algebra', 'elapsed_seconds': 5}],
              'axis_candidates': {}, 'axis_equations': {'ax': [], 'ay': []}}
    law = dict(candidate, law_id='law_1', train_probe_ids=['p1', 'p2', 'p3'], fit_status='converged',
               fitted_parameters={'c1': .1, 'c2': .2}, errors={'overall': {'position_rmse': 1e-5}})
    validation = {'validation_id': 'val_1', 'law_id': 'law_1', 'test_probe_ids': ['p4'],
                  'errors': {'overall': {'position_rmse': .1},
                             'per_probe': [{'probe_id': 'p4', 'position_rmse': .1}]}}
    for kind, identifier, record in [('symbolic_search','sr_abc',search), ('law','law_1',law),
                                      ('validation','val_1',validation)]:
        dump(run/'records'/kind/f'{identifier}.json', record)
    tools = [
        {'tool': 'symbolic_regression', 'arguments': {'train_probe_ids': ['p1','p2','p3'], 'time_budget_seconds':47},
         'result': {'ok': True, 'data': search}, 'elapsed_seconds': 46},
        {'tool': 'fit_law_and_rollout', 'arguments': dict(candidate, train_probe_ids=['p1','p2','p3']),
         'result': {'ok': True, 'data': {'law_id':'law_1'}}},
        {'tool': 'validate_law', 'arguments': {'law_id':'law_1', 'test_probe_ids':['p4']},
         'result': {'ok': True, 'data': validation}},
    ]
    dump(run/'tools.jsonl', tools, True)
    dump(run/'events.jsonl', [{'event':'symbolic_submission_review', 'reasons':['large_residual'],
                              'budget':{'wall_seconds_remaining':130}, 'evidence':{}}], True)
    dump(run/'model_events.jsonl', [
        {'event':'request_started', 'call_number':1},
        {'event':'request', 'call_number':1, 'usage':{'completion_tokens':123}, 'elapsed_seconds':10, 'max_tokens':4096},
    ], True)
    messages = [{'role':'tool', 'content':json.dumps({'ok':True,'data':search}), 'tool_call_id':'call-sr'}]
    dump(run/'messages.json', messages)
    dump(run/'model_messages.jsonl', [{'call_number':1, 'messages':messages}], True)
    dump(run/'result.json', {'status':'submitted'})
    row = {'world_id':'world_1', 'run_id':run.name, 'status':'submitted', 'law':{'law_id':'law_1'},
           'evaluation_complete':True, 'evaluation_score':{'total':91}, 'calls':1, 'completion_tokens':123,
           'average_output_tokens_per_call':123, 'max_call_output_tokens':123, 'model_elapsed_seconds':10,
           'exploration_seconds':80, 'wall_seconds_including_evaluation':84}
    summary = tmp_path/'experiments'/'E5'/'test'/'summary.json'
    dump(summary, {'experiment_id':'test','status':'completed','worlds':[row]})
    return tmp_path, summary, run, candidate, probes


def test_complete_audit_preserves_actual_stages_and_exact_adoption(saved_run):
    root, summary, _, _, _ = saved_run
    report = build_audit(root, summary)
    world = report['worlds'][0]
    assert report['inputs_unchanged']
    assert world['tokens_from_summary']['average_output_tokens_per_call'] == 123
    assert all(value is True for value in world['summary_api_cross_checks'].values())
    search = world['searches'][0]
    assert [s['stage'] for s in search['search_stages']] == ['axis_0_algebra']
    assert search['candidates'][0]['source_class'] == 'mixed'
    assert search['candidates'][0]['fit_matches'][0]['relation'] == 'exact_formula_and_parameters'
    assert search['candidates'][0]['fit_matches'][0]['submitted_same_law_id'] is True
    assert search['context_delivery']['all_formula_parameter_specs_preserved'] is True
    assert world['validations'][0]['training_or_sr_discovery_overlap'] == []
    assert world['unresolved_evidence_at_submission'][0]['kind'].startswith('submitted_law_has_large')
    assert not list(root.glob('**/*audit*.json'))


def test_missing_usage_never_manufactures_verified_average(saved_run):
    root, summary, run, _, _ = saved_run
    dump(run/'model_events.jsonl', [{'event':'request_started','call_number':1},
                                  {'event':'request','call_number':1,'error':'api_timeout'}], True)
    world = build_audit(root, summary)['worlds'][0]
    assert world['tokens_from_summary']['average_output_tokens_per_call'] == 123
    assert world['token_log_audit']['average_output_tokens_per_call'] is None
    assert world['token_log_audit']['usage_complete'] is False
    assert world['summary_api_cross_checks']['average_output_tokens_per_call'] is None
    assert world['model_failures'][0]['error'] == 'api_timeout'


def test_malformed_usage_log_cannot_fall_back_to_summary_complete_claim(saved_run):
    root, summary, run, _, _ = saved_run
    (run/'model_events.jsonl').write_text('{broken')
    world = build_audit(root, summary)['worlds'][0]
    assert world['token_log_audit']['usage_complete'] is False
    assert world['token_log_audit']['average_output_tokens_per_call'] is None


def test_structural_rename_and_partial_component_are_not_exact(saved_run):
    _, _, _, candidate, _ = saved_run
    renamed = {'law_spec':{'ax':'-a*x','ay':'-b*y'},
               'parameter_spec':[{'name':'a','initial':10},{'name':'b','initial':20}]}
    assert match_formula(candidate, renamed) == 'same_structure_parameter_renaming_or_initial_changes'
    renamed['law_spec']['ay'] = 'b*y*y'
    assert match_formula(candidate, renamed) is None
    assert match_formula(candidate, renamed, component='ax') is not None
    assert source_class({'component_sources':['pysr','constant_initialization']},None) == 'mixed'
    assert source_class({'origin':'linear_least_squares'},'ax') == 'all_linear_least_squares'


def test_unmatched_single_axis_is_not_reported_as_reused(saved_run):
    root, summary, run, _, _ = saved_run
    path = run/'records'/'symbolic_search'/'sr_abc.json'
    search = json.loads(path.read_text())
    search['axis_candidates'] = {'ax': [{'law_spec':{'ax':'c1*x*x','ay':'0'},
        'parameter_spec':[{'name':'c1','initial':.12}], 'origin':'pysr'}]}
    dump(path, search)
    world = build_audit(root, summary)['worlds'][0]
    axis = next(c for c in world['searches'][0]['candidates'] if c['component'] == 'ax')
    assert axis['fit_matches'] == []
    assert all(link['candidate_reference'] != 'ax:0' for link in world['fits'][0]['candidate_links'])


def test_data_coverage_retains_time_and_property_controls(saved_run):
    *_, probes = saved_run
    result = coverage(probes, ['p1','p2','p3'])
    assert result['same_complete_initial_state_delayed_controls'] == [['p1','p2']]
    assert result['single_property_controls'] == [{'probe_ids':['p1','p3'],'property':'mass'}]
    assert result['property_values']['mass'] == [1,2]
    assert result['launch_times'] == [0,7]


def test_delivery_detects_formula_change_and_missing_search_identifier(saved_run):
    _, _, _, candidate, _ = saved_run
    search = {'search_id':'sr_abc','candidates':[candidate]}
    corrupted = copy.deepcopy(search)
    corrupted['candidates'][0]['law_spec']['ax'] = '0'
    messages = [{'role':'tool','content':json.dumps({'data':corrupted})}]
    assert context_delivery([],messages,'sr_abc',search)['all_formula_parameter_specs_preserved'] is False
    assert context_delivery([],messages,None,{})['source'] is None


@pytest.mark.parametrize('content', ['null', '{"data":null}', '{"data":[]}'])
def test_delivery_skips_tool_payloads_without_object_data(content):
    messages = [{'role':'tool','content':content}]
    assert context_delivery([],messages,'sr_abc',{'candidates':[]})['source'] is None


def test_archive_detects_input_change(saved_run):
    root, summary, *_ = saved_run
    archive = Archive(root)
    archive.read(summary)
    summary.write_text('{}')
    assert archive.unchanged() is False
