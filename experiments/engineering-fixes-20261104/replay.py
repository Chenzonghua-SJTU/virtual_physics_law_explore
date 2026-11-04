"""Offline regression using archived runs; no model calls or archive mutations.

Run from the project root with `.venv/bin/python experiments/engineering-fixes-20261104/replay.py`.
The original runs are local-only and intentionally excluded from Git.
"""
import ast
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from shore_agent.expressions import Expression
from shore_agent.model import DeepSeekClient
from shore_agent.numerics import fit, rollout
from shore_agent.schemas import SCHEMAS


def read(path):
    return json.loads(path.read_text())


def lines(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s]


def archive_hashes():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for d in directories for p in d.rglob('*') if p.is_file()}


batch = read(ROOT / 'experiments/seven-worlds-v0.1.0-20261103/summary.json')
directories = [ROOT / 'runs' / row['run_id'] for row in batch['worlds']]
before = archive_hashes()
dsl = []
for directory in directories:
    for index, event in enumerate(lines(directory / 'tools.jsonl'), 1):
        error = event['result'].get('error') or {}
        if '100 total AST nodes' not in str(error):
            continue
        args = event['arguments']
        Expression(args['law_spec'], args['parameter_spec'])
        dsl.append({'run_id': directory.name, 'tool_index': index,
                    'ast_nodes': sum(len(list(ast.walk(ast.parse(s, mode='eval'))))
                                     for s in args['law_spec'].values()),
                    'accepted_now': True})
assert len(dsl) == 6

directory = ROOT / 'runs/web-20261103-153234-0c6d5b0b'
previous = lines(directory / 'model_messages.jsonl')[-1]
events = [r for r in lines(directory / 'model_events.jsonl') if r.get('event') == 'request']
config = read(directory / 'config.json')['model']
messages = read(directory / 'messages.json')
context = {'model': config['model'], 'stream': False, 'thinking': {'type': 'enabled'},
           'reasoning_effort': config['reasoning_effort'], 'tools': SCHEMAS, 'tool_choice': 'auto'}
# Exercise the production estimator without constructing an HTTP client.
client = object.__new__(DeepSeekClient)
client._prompt_reference = {'context': context, 'messages': previous['messages'],
                            'prompt_tokens': events[-1]['usage']['prompt_tokens']}
estimate = client._prompt_estimate(dict(context, messages=messages))
usage = read(directory / 'result.json')['model_usage']
remaining = config['max_total_tokens'] - usage['total_tokens'] - usage['conservative_reserved_tokens']
budget = dict(estimate, available_tokens=remaining,
              allowed_output_tokens=min(config['max_tokens_per_call'], remaining-estimate['estimated_prompt_tokens']),
              replay_only=True, request_sent=False)
assert estimate['method'] == 'reported_prefix_plus_utf8_suffix'
assert estimate['utf8_upper_bound'] == 450025 > remaining
assert budget['allowed_output_tokens'] == 65536

directory = ROOT / 'runs/web-20261103-151802-c2293873'
law = read(directory / 'records/law/law_1.json')
probes = [read(directory / 'records/probe' / (pid+'.json')) for pid in law['train_probe_ids']]
sigma = read(directory / 'mission.json')['task']['position_noise_sigma']
result = fit(law['law_spec'], law['parameter_spec'], probes, [], position_noise_sigma=sigma)
assert result['refinement']['status'] == 'refined'
evaluation = read(directory / 'evaluation.json')


def analytic(params, ic):
    k = np.array([[params['p1'], params['p2']], [params['p2'], params['p4']]])
    center = np.linalg.solve(k, [params['p3'], params['p5']])
    eigenvalues, eigenvectors = np.linalg.eigh(k)
    w = np.sqrt(eigenvalues)
    t = np.arange(ic['n_samples']) * ic['dt']
    q, u = (np.asarray(ic['r0'])-center) @ eigenvectors, np.asarray(ic['v0']) @ eigenvectors
    return (np.cos(t[:, None]*w)*q + np.sin(t[:, None]*w)*u/w) @ eigenvectors.T + center


# Post-session diagnostic reference only. Never supplied to the fitter or Agent.
reference = dict(zip(('p1', 'p2', 'p3', 'p4', 'p5'), (.35, .08, .08, .2, .2)))
old_errors, new_errors, integrated_errors = [], [], []
for ic in evaluation['initial_conditions']:
    truth = analytic(reference, ic)
    old_errors.append(np.mean(np.sum((analytic(law['fitted_parameters'], ic)-truth)**2, axis=1)))
    new_errors.append(np.mean(np.sum((analytic(result['fitted_parameters'], ic)-truth)**2, axis=1)))
    probe = {'probe_id': ic['probe_id'],
             'initial_conditions': {k: ic[k] for k in ('r0', 'v0', 't0', 'properties')},
             'times': (ic['t0']+np.arange(ic['n_samples'])*ic['dt']).tolist()}
    predicted = rollout(law['law_spec'], result['fitted_parameters'], probe, [])
    integrated_errors.append(np.mean(np.sum((np.asarray(predicted['r_pred'])-truth)**2, axis=1)))
numerics = {'run_id': directory.name, 'training_unchanged': True, 'independent_trajectory_count': len(old_errors),
            'old_archived_independent_rmse': evaluation['overall']['position_rmse'],
            'old_analytic_rmse': float(np.sqrt(np.mean(old_errors))),
            'refined_analytic_rmse': float(np.sqrt(np.mean(new_errors))),
            'refined_production_rollout_rmse_vs_analytic': float(np.sqrt(np.mean(integrated_errors))),
            'old_objective_calls': law['objective_calls'], 'new_objective_calls': result['objective_calls'],
            'training_rmse': result['errors']['overall']['position_rmse'],
            'fitted_parameters': result['fitted_parameters'], 'refinement': result['refinement']}
assert numerics['refined_production_rollout_rmse_vs_analytic'] < 1e-6
assert numerics['refined_analytic_rmse'] < numerics['old_analytic_rmse']/10
unchanged = before == archive_hashes()
assert unchanged
report = {'kind': 'offline_engineering_regression_not_autonomous_discovery',
          'new_model_calls': 0, 'original_archives_unchanged': unchanged,
          'previous_ast_rejections': dsl, 'world5_budget': budget, 'world2_numerics': numerics}
(Path(__file__).parent / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
print(json.dumps(report, ensure_ascii=False, indent=2))
