"""Synthetic real-exponent integration smoke; independent of every contest world."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy.integrate import solve_ivp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from deployment.replay_symbolic import _candidate_check
from shore_agent.symbolic_service import search_remote


def make_probe(name, x0, vx0):
    times = np.linspace(0, 1, 41)
    # This function is solely a synthetic observation generator. No acceleration
    # truth, formula, exponent, coefficients or derivative labels go to search.
    def rhs(t, state):
        return [state[2], state[3], .09 * state[0] ** 1.7, 0]
    initial = [x0, 0, vx0, 0]
    state = solve_ivp(rhs, (0, 1), initial, t_eval=times,
                      rtol=1e-11, atol=1e-13, method='DOP853').y.T
    return {'probe_id': name, 'times': times.tolist(),
            'r_obs': state[:, :2].tolist(), 'v_obs': state[:, 2:].tolist(),
            'initial_conditions': {'r0': initial[:2], 'v0': initial[2:], 't0': 0,
                                   'properties': {'mass': 1, 'charge': 1}}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--budget', type=int, default=30, choices=(30, 40, 60))
    args = parser.parse_args()
    training = [make_probe('synthetic_power_' + str(i), x, v)
                for i, (x, v) in enumerate(((.7, .03), (1.4, -.04), (2.8, .06), (4.2, -.03)))]
    heldout = [make_probe('synthetic_heldout_' + str(i), x, v)
               for i, (x, v) in enumerate(((1.0, -.08), (3.5, .10)))]
    report = {'kind': 'synthetic_power_smoke_not_agent_or_contest_result',
              'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'generation': {'ax': '.09*x**1.7', 'ay': '0', 'description': 'Synthetic generator only; no true acceleration labels passed to search'},
              'train_probe_ids': [p['probe_id'] for p in training],
              'heldout_probe_ids': [p['probe_id'] for p in heldout],
              'source_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in
                  ('shore_agent/symbolic_regression.py', 'shore_agent/symbolic_service.py')},
              'physical_missions_started': 0, 'status': 'started'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as output:
        json.dump(report, output, indent=2)
    started = time.monotonic()
    try:
        result = search_remote(training, args.budget, random_state=741)
        report['result'] = result
        report['search_client_seconds'] = time.monotonic() - started
        report['candidate_diagnostics'] = []
        for candidate in result['candidates']:
            parameters = {p['name']: p['initial'] for p in candidate['parameter_spec']}
            report['candidate_diagnostics'].append({
                'law_spec': candidate['law_spec'], 'parameter_spec': candidate['parameter_spec'],
                'component_sources': candidate.get('component_sources'),
                'training': _candidate_check(candidate, training, parameters, 1),
                'heldout': _candidate_check(candidate, heldout, parameters, 1)})
        report['status'] = 'completed'
    finally:
        report['total_seconds'] = time.monotonic() - started
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'status': report['status'], 'candidates': len(report['result']['candidates']),
                      'elapsed_seconds': report['search_client_seconds']}))


if __name__ == '__main__':
    main()
