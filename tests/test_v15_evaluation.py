"""Developer-authored laws verify integration; these are not Agent discoveries."""
import json
import math

import numpy as np
import pytest

from evaluate import evaluate_run, score_existing_evaluation


RHO = 'sqrt(x**2+y**2+s)'
RADIUS = 'sqrt(x**2+y**2)'
PHASE = '(w*t+p)'
CASES = [
    ('1', {'ax': f"-g*q('charge')*x/(q('mass')*{RHO}*{RADIUS})",
           'ay': f"-g*q('charge')*y/(q('mass')*{RHO}*{RADIUS})"},
     {'g': 1 / (4 * math.pi), 's': .05 ** 2}),
    ('2', {'ax': "-k*q('charge')*x/q('mass')", 'ay': "-k*q('charge')*y/q('mass')"},
     {'k': .06}),
    ('3', {'ax': '-a*x-b*y', 'ay': '-b*x-c*y'},
     {'a': .06, 'b': -.08 * math.sqrt(3) / 4, 'c': .10}),
    ('4', {'ax': f"-g*q('charge')*exp(-{RHO}/h)*x/(q('mass')*{RHO}*{RADIUS})",
           'ay': f"-g*q('charge')*exp(-{RHO}/h)*y/(q('mass')*{RHO}*{RADIUS})"},
     {'g': 1 / math.pi, 's': .05 ** 2, 'h': 4.}),
    ('5', {'ax': '-a*x-c*x**3-d*x*y**2', 'ay': '-b*y-c*y**3-d*y*x**2'},
     {'a': .06, 'b': .10, 'c': .002, 'd': .012}),
    ('6', {'ax': f'-(a*cos({PHASE})**2+b*sin({PHASE})**2)*x-(a-b)*cos({PHASE})*sin({PHASE})*y',
           'ay': f'-(a-b)*cos({PHASE})*sin({PHASE})*x-(a*sin({PHASE})**2+b*cos({PHASE})**2)*y'},
     {'a': .06, 'b': .18, 'w': math.pi / 16, 'p': .3}),
]


def archive(root, world='2', spec=None, parameters=None):
    selected = next(case for case in CASES if case[0] == world)
    (root / 'records/submission').mkdir(parents=True)
    (root / 'records/law').mkdir()
    submission = {'submission_id': 's1', 'law_id': 'law_1', 'status': 'accepted',
                  'session_ended': True,
                  'claims': {'dynamics_order': 2, 'hidden_matter': False, 'time_dependence': world == '6'}}
    law = {'law_id': 'law_1', 'law_spec': spec or selected[1],
           'fitted_parameters': parameters if parameters is not None else selected[2], 'known_bodies': []}
    environment = {'world_set': 'v15', 'world_id': f'world_{world}', 'physics_version': 'shore_v15'}
    records = {'records/submission/s1.json': submission, 'records/law/law_1.json': law,
               'config.json': {'environment': environment}, 'mission.json': {'task': environment},
               'result.json': {'status': 'submitted', 'submission': submission,
                               'budget': {'energy_remaining': 80}}}
    for path, value in records.items():
        (root / path).write_text(json.dumps(value), encoding='utf-8')
    return environment


@pytest.mark.parametrize('world,spec,parameters', CASES)
def test_all_six_native_catalogs_score_unchanged_agent_laws(tmp_path, world, spec, parameters):
    from shore_agent.web_jobs import _evaluation_projection

    environment = archive(tmp_path, world, spec, parameters)
    result = evaluate_run(tmp_path, seed=99, n_probes=1)
    assert result['complete'], result['failures']
    assert result['world_set'] == 'v15' and result['physics_version'] == 'shore_v15'
    assert result['n_trajectories'] == (32 if world == '6' else 24)
    assert result['n_successful'] == result['n_trajectories']
    assert result['overall']['position_rmse'] < 1e-5
    assert result['score']['prediction'] == pytest.approx(80, abs=1e-6)
    assert result['score']['total'] == pytest.approx(99, abs=1e-6)
    assert result['score']['energy_budget'] == 100
    assert result['score']['energy_used'] == 20
    assert result['score']['conservation'] == 4
    assert result['requested_n_probes'] == 1 and result['seed_used'] is False
    assert result['official_score'] is False
    projection = _evaluation_projection(tmp_path, 'submitted', {}, {'environment': environment}, evaluation=result)
    assert projection['evaluation_state'] == 'scored'
    if world in ('1', '2', '4'):
        assert {p['properties']['charge'] for p in result['initial_conditions']} == {.7, 1.7}
        assert {p['properties']['mass'] for p in result['initial_conditions']} == {.7, 1., 1.3, 1.6}


@pytest.mark.parametrize('file,field,value', [
    ('config.json', 'world_set', 'legacy'),
    ('config.json', 'world_set', 'unknown'),
    ('config.json', 'physics_version', 'v4'),
    ('mission.json', 'world_set', 'legacy'),
    ('mission.json', 'physics_version', 'v4'),
    ('mission.json', 'world_id', 'world_3'),
])
def test_v15_identity_mismatch_refused_before_truth(tmp_path, monkeypatch, file, field, value):
    archive(tmp_path)
    path = tmp_path / file
    saved = json.loads(path.read_text())
    saved['environment' if file == 'config.json' else 'task'][field] = value
    path.write_text(json.dumps(saved))
    monkeypatch.setattr('shore_v15.evaluation.evaluate_submission',
                        lambda *args, **kwargs: pytest.fail('Must refuse before v15 truth access'))
    with pytest.raises(ValueError):
        evaluate_run(tmp_path)


def test_v15_requires_accepted_ended_submission(tmp_path, monkeypatch):
    archive(tmp_path)
    path = tmp_path / 'records/submission/s1.json'
    saved = json.loads(path.read_text())
    saved['session_ended'] = False
    path.write_text(json.dumps(saved))
    monkeypatch.setattr('shore_v15.evaluation.evaluate_submission',
                        lambda *args, **kwargs: pytest.fail('Must refuse before v15 truth access'))
    with pytest.raises(ValueError, match='accepted submission'):
        evaluate_run(tmp_path)


@pytest.mark.parametrize('ruleset', ['e4', 'e5'])
def test_e4_evaluation_reads_actual_mission_energy_and_separate_formula(tmp_path, ruleset):
    archive(tmp_path)
    config_path = tmp_path / 'config.json'
    config = json.loads(config_path.read_text())
    config['environment'].update(ruleset=ruleset, energy_budget=10, wall_seconds=300, noise=(ruleset == 'e4'))
    config_path.write_text(json.dumps(config))
    mission_path = tmp_path / 'mission.json'
    mission = json.loads(mission_path.read_text())
    mission['task'].update(ruleset=ruleset, limits={'initial_energy': 10})
    mission_path.write_text(json.dumps(mission))
    result_path = tmp_path / 'result.json'
    result = json.loads(result_path.read_text())
    result['budget']['energy_remaining'] = 6
    result_path.write_text(json.dumps(result))
    evaluated = evaluate_run(tmp_path)
    assert evaluated['score']['energy_used'] == 4
    assert evaluated['score']['energy_budget'] == 10
    assert evaluated['score']['conservation'] == 3
    assert evaluated['score']['formula_version'] == 'shore_e4_10energy'
    assert evaluated['ruleset'] == ruleset


def test_v15_candidate_failure_zeroes_prediction_not_claims(tmp_path):
    archive(tmp_path, spec={'ax': '1/0', 'ay': '0'}, parameters={})
    result = evaluate_run(tmp_path)
    assert result['complete'] is False
    assert result['n_successful'] == 0 and len(result['failures']) == 24
    assert result['score']['total'] == 15
    assert result['score']['prediction'] == result['score']['conservation'] == 0
    assert result['score']['reason'] == 'candidate_prediction_invalid'


def test_v15_truth_failure_does_not_assign_a_candidate_score(tmp_path, monkeypatch):
    archive(tmp_path)

    def fail(*args, **kwargs):
        raise FloatingPointError('synthetic reference failure')

    monkeypatch.setattr('shore_v15.source.DevelopmentSimulator.launch', fail)
    result = evaluate_run(tmp_path)
    assert result['complete'] is False
    assert result['score']['status'] == 'unavailable'
    assert result['score']['reason'] == 'truth_reference_failed'


def test_v15_visible_state_is_the_native_grid_with_interpolation():
    from shore_v15.evaluation import _visible_positions
    from shore_v15.source import DevelopmentSimulator

    simulator = DevelopmentSimulator('3')
    provider = _visible_positions(simulator, .1)
    expected = simulator.background([0., .01, .015, .1])['positions']
    np.testing.assert_allclose(provider(0.), expected[0], atol=0.)
    np.testing.assert_allclose(provider(.01), expected[1], atol=0.)
    np.testing.assert_allclose(provider(.0125), (expected[1] + expected[2]) / 2, atol=1e-14)
    np.testing.assert_allclose(provider(.1), expected[3], atol=0.)


def test_v15_backfill_never_uses_legacy_truth(tmp_path, monkeypatch):
    archive(tmp_path)
    monkeypatch.setattr('shore_sim.worlds.truth_claims',
                        lambda *args, **kwargs: pytest.fail('No legacy truth for v15'))
    result = score_existing_evaluation(tmp_path, {})
    assert result['status'] == 'unavailable'
    assert result['reason'] == 'v15_requires_fresh_evaluation'


def test_v15_world2_real_ipc_runtime_fit_validate_submit_evaluate(tmp_path):
    """Hand-chosen hypothesis exercises real tools; no mock model discovery."""
    from shore_agent.environment import Environment
    from shore_agent.runtime import ToolRuntime

    configuration = {'world_set': 'v15', 'world_id': 'world_2',
                     'physics_version': 'shore_v15', 'noise': False, 'seed': 42}
    (tmp_path / 'config.json').write_text(json.dumps({'environment': configuration}))
    with Environment(configuration) as environment:
        runtime = ToolRuntime(environment, tmp_path)
        mission = runtime.mission()
        assert mission['ok'], mission
        assert mission['data']['task']['world_set'] == 'v15'
        fitted = runtime.execute('fit_law_and_rollout', {
            'law_spec': CASES[1][1],
            'parameter_spec': [{'name': 'k', 'initial': .05, 'lower': .001, 'upper': .5}],
            'train_probe_ids': list(runtime.store.records['probe']),
        })
        assert fitted['ok'], fitted
        law_id = fitted['data']['law_id']
        assert runtime.store.get('law', law_id)['fitted_parameters']['k'] == pytest.approx(.06, abs=1e-6)
        observed = runtime.execute('insert_probe', {
            'probes': [{'r0': [2., -1.], 'v0': [.2, .3], 'properties': {'mass': .7, 'charge': 1.7}},
                       {'r0': [-3., 2.], 'v0': [.4, -.1], 'properties': {'mass': 1.6, 'charge': .7}}],
            't0': 4., 'dt': .1, 'n_samples': 20,
        })
        assert observed['ok'], observed
        validation = runtime.execute('validate_law', {
            'law_id': law_id,
            'test_probe_ids': [probe['probe_id'] for probe in observed['data']['probes']],
        })
        assert validation['ok'], validation
        assert validation['data']['errors']['overall']['position_rmse'] < 1e-5
        submitted = runtime.execute('submit', {
            'law_id': law_id,
            'claims': {'dynamics_order': 2, 'hidden_matter': False, 'time_dependence': False},
            'physical_explanation': 'Engineering fixture: a central linear restoring law whose response '
                                    'scales with the controlled source strength and inverse probe inertia; '
                                    'independent observations validate the frozen coefficient.',
        })
        assert submitted['ok'], submitted
        assert submitted['data']['status'] == 'accepted', submitted
        assert submitted['data']['session_ended'] is True
        assert submitted['budget']['energy_remaining'] == 98
    evaluation = evaluate_run(tmp_path)
    assert evaluation['complete'], evaluation['failures']
    assert evaluation['n_trajectories'] == evaluation['n_successful'] == 24
    assert evaluation['overall']['position_rmse'] < 1e-5
    assert evaluation['score']['energy_used'] == 2
    assert evaluation['score']['energy_source'] == 'tools.jsonl:final_budget.energy_remaining'
    assert evaluation['score']['total'] == pytest.approx(99.9, abs=1e-6)
