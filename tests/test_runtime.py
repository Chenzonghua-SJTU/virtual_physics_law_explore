import copy
import json
import numpy as np
import pytest
from shore_agent.environment import Environment
from shore_agent.runtime import ToolRuntime
from shore_agent.schemas import SCHEMAS


@pytest.fixture
def runtime(tmp_path):
    env = Environment({'noise': False, 'seed': 12})
    rt = ToolRuntime(env, tmp_path)
    mission = rt.mission()
    assert mission['ok'], mission
    yield rt
    env.close()


def call(rt, name, **args):
    reply = rt.execute(name, args)
    assert reply['ok'], reply
    return reply['data']


def fit_fixture(rt):
    ids = list(rt.store.records['probe'])
    # Manually specified generic affine structure for engineering tests only.
    return call(rt, 'fit_law_and_rollout', law_spec={'ax': 'a*x+b*y+c', 'ay': 'b*x+d*y+e'},
                parameter_spec=[{'name': n, 'initial': 0, 'lower': -2, 'upper': 2} for n in 'abcde'],
                train_probe_ids=ids)


def test_exact_surface_and_cache(runtime):
    assert len(SCHEMAS) == 7
    original = copy.deepcopy(runtime.store.records)
    initial = runtime.budget()
    runtime.mission()
    assert runtime.store.records == original
    assert runtime.budget()['energy_remaining'] == initial['energy_remaining']
    assert not runtime.execute('shell', {'command': 'ls'})['ok']
    invalid = runtime.execute('observe_body', {'times': [float('nan')]})
    assert not invalid['ok'] and invalid['error']
    assert not runtime.execute('call_back', {'detail': 'full'})['ok']
    rid = next(iter(runtime.store.records['probe']))
    full = call(runtime, 'call_back', record_type='probe', record_ids=[rid], detail='full')
    assert len(full['records'][0]['content']['r_obs']) == 8
    assert full == call(runtime, 'call_back', record_type='probe', record_ids=[rid], detail='full')


def test_removed_summary_tool_is_unavailable(runtime):
    assert not hasattr(runtime, 'analyst')
    assert not hasattr(runtime, 'summarize_data')
    assert 'summarize_data' not in {s['function']['name'] for s in SCHEMAS}
    before = runtime.budget()
    reply = runtime.execute('summarize_data', {'probe_ids': list(runtime.store.records['probe'])})
    assert not reply['ok'] and reply['data'] is None
    assert reply['error']['message'] == 'Unknown tool'
    assert runtime.budget()['energy_remaining'] == before['energy_remaining']


def test_validation_freeze_submission_and_residual(runtime):
    law = fit_fixture(runtime)
    assert law['fit_status'] != 'failed'
    law_id = law['law_id']
    assert law_id == 'law_1'
    before = runtime.store.get('law', law_id)
    second = fit_fixture(runtime)
    assert second['law_id'] == 'law_2'
    assert runtime.store.get('law', law_id) == before
    assert json.loads((runtime.store.directory / 'law' / 'law_1.json').read_text()) == before
    overlap = runtime.execute('validate_law', {'law_id': law_id, 'test_probe_ids': before['train_probe_ids']})
    assert not overlap['ok']
    probes = call(runtime, 'insert_probe', probes=[{'r0': [3, -2], 'v0': [0.5, 1], 'properties': {}}],
                  t0=2, dt=0.1, n_samples=30)['probes']
    pid = probes[0]['probe_id']
    validation = call(runtime, 'validate_law', law_id=law_id, test_probe_ids=[pid])
    assert validation['errors']['overall']['position_rmse'] < 1e-5
    assert runtime.store.get('law', law_id) == before
    residual = call(runtime, 'analyze_residual', law_id=law_id, probe_ids=[pid])
    full = runtime.store.get('residual', residual['residual_id'])
    assert not full['trajectories'][0]['used_for_fit']
    assert len(full['trajectories'][0]['residuals']['a']) == 28
    explanation = '观测支持：独立轨迹与仿射候选一致。\n数学推论：各线性系数的单位为时间的负二次方。\n局限：不能由拟合唯一识别作用源。'
    assert not runtime.execute('submit', {'law_id': law_id, 'physical_explanation': explanation, 'claims': {'dynamics_order': True,
                 'hidden_matter': False, 'time_dependence': False}})['ok']
    args = {'law_id': law_id, 'claims': {'dynamics_order': 2, 'hidden_matter': False, 'time_dependence': False}}
    for invalid in ({}, {'physical_explanation': ''}, {'physical_explanation': ' \n\t\u3000'},
                    {'physical_explanation': None}, {'physical_explanation': {'text': explanation}},
                    {'physical_explanation': 'x' * 20001}):
        reply = runtime.execute('submit', dict(args, **invalid))
        assert not reply['ok'], reply
        assert not runtime.session_ended and not runtime.budget()['session_ended']
        assert not runtime.store.records['submission']
        assert not (runtime.run_dir / 'submissions').exists()
    submitted = call(runtime, 'submit', **args, physical_explanation=explanation)
    assert submitted['status'] == 'accepted', submitted
    assert submitted['session_ended']
    assert submitted['physical_explanation'] == explanation
    archived = runtime.store.get('submission', submitted['submission_id'])
    assert archived['physical_explanation'] == explanation
    exported = runtime.run_dir / 'submissions' / submitted['submission_id']
    assert (exported / 'physical_explanation.txt').read_text(encoding='utf-8') == explanation
    assert explanation not in (exported / 'law.py').read_text(encoding='utf-8')
    assert not runtime.execute('observe_body', {'times': [0]})['ok']


def test_small_sample_and_constant_correlation(runtime):
    law = call(runtime, 'fit_law_and_rollout', law_spec={'ax': '0', 'ay': '0'}, parameter_spec=[],
               train_probe_ids=list(runtime.store.records['probe']))
    p = call(runtime, 'insert_probe', probes=[{'r0': [0, 0], 'v0': [0, 0], 'properties': {}}],
             t0=0, dt=0.1, n_samples=1)['probes'][0]
    res = call(runtime, 'analyze_residual', law_id=law['law_id'], probe_ids=[p['probe_id']])
    full = runtime.store.get('residual', res['residual_id'])['trajectories'][0]
    assert full['statistics']['a']['rmse'] is None
    assert full['correlations']['r']['x']['x']['value'] is None


def test_no_truth_imports_and_no_answer_in_prompts():
    from pathlib import Path
    import ast
    package = Path(__file__).parents[1] / 'shore_agent'
    for path in package.glob('*.py'):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or '').startswith('shore_sim')
            if isinstance(node, ast.Import):
                assert not any(a.name.startswith('shore_sim') for a in node.names)
    for path in (package/'prompts').glob('*.txt'):
        text = path.read_text()
        assert '0.1 * sum' not in text and '0.3' not in text and '简谐' not in text
