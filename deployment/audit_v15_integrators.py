"""Developer-only, truth-informed numerical audit; never an Agent tool or baseline.

Reads the six public fixed suites, compares exact public-force DSLs with their
references, and optionally diagnoses archived candidates without changing them.
Only the explicitly requested new audit JSON is written. No model is called,
no candidate is fitted/submitted, and no run/evaluation archive is rewritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shore_agent import numerics
from shore_agent.expressions import Expression
from shore_v15.evaluation import _visible_positions
from shore_v15.source import (DevelopmentSimulator, DT, NUMERICS_VERSION, catalog,
                             agent_properties, source_inputs, rollout)
from development_worlds.worlds import EPSILON
from rift_numerics.rollout import diagnostic_rollout


def public_formula(world, simulator):
    """Independent DSL transcription for auditing; these are not discovered laws."""
    p = simulator.parameters
    radius = 'sqrt(x**2+y**2)'
    rho = 'sqrt(x**2+y**2+s)'
    if world in ('1', '4'):
        params = {'g': p['G'] / ((4 if world == '1' else 2) * math.pi), 's': EPSILON**2}
        factor = '' if world == '1' else f'*exp(-{rho}/h)'
        if world == '4':
            params['h'] = p['lambda']
        return {axis: f'-g*q("charge"){factor}*{coord}/(q("mass")*{rho}*{radius})'
                for axis, coord in (('ax', 'x'), ('ay', 'y'))}, params
    if world == '2':
        return {'ax': '-k*q("charge")*x/q("mass")',
                'ay': '-k*q("charge")*y/q("mass")'}, {'k': p['k']}
    if world == '3':
        c, s = math.cos(p['angle']), math.sin(p['angle'])
        return {'ax': '-a*x-b*y', 'ay': '-b*x-c*y'}, {
            'a': p['kx']*c*c+p['ky']*s*s, 'b': (p['kx']-p['ky'])*c*s,
            'c': p['kx']*s*s+p['ky']*c*c}
    if world == '5':
        return {'ax': '-a*x-c*x**3-d*x*y**2', 'ay': '-b*y-c*y**3-d*y*x**2'}, dict(p)
    phase = '(w*t+p)'
    return {'ax': f'-(a*cos({phase})**2+b*sin({phase})**2)*x-(a-b)*cos({phase})*sin({phase})*y',
            'ay': f'-(a-b)*cos({phase})*sin({phase})*x-(a*sin({phase})**2+b*cos({phase})**2)*y'}, {
                'a': p['kx'], 'b': p['ky'], 'w': math.pi/p['period'], 'p': p['phase']}


def instrumented_rollout(spec, params, probe, body_provider):
    """Instrument this audit process only; all production numerical limits remain active."""
    stats = {'rhs_calls': 0, 'minimum_rhs_radius': None, 'maximum_rhs_acceleration': 0.,
             'last_rhs_time': None, 'last_rhs_state': None}
    original = numerics.solve_ivp

    def solve(fun, *args, **kwargs):
        def rhs(t, state):
            stats['rhs_calls'] += 1
            radius = float(np.linalg.norm(state[:2]))
            stats['minimum_rhs_radius'] = min(radius, stats['minimum_rhs_radius'] or float('inf'))
            stats['last_rhs_time'] = float(t)
            stats['last_rhs_state'] = state.tolist()
            value = fun(t, state)
            stats['maximum_rhs_acceleration'] = max(stats['maximum_rhs_acceleration'],
                                                     float(np.linalg.norm(value[2:])))
            return value
        result = original(rhs, *args, **kwargs)
        stats['solver_success'] = bool(result.success)
        stats['solver_message'] = str(result.message)
        stats['solver_reported_nfev'] = int(result.nfev)
        return result

    started = time.monotonic()
    numerics.solve_ivp = solve
    try:
        prediction = numerics.rollout(spec, params, probe, body_provider)
        stats.update(status='completed', total_acceleration_calls=stats['rhs_calls']+len(probe['times']))
        return prediction, stats
    except (ValueError, OverflowError, FloatingPointError) as exc:
        stats.update(status='failed', error_code=getattr(exc, 'code', type(exc).__name__),
                     reason=str(exc))
        return None, stats
    finally:
        numerics.solve_ivp = original
        stats['elapsed_seconds'] = time.monotonic() - started


def background_audit(simulator, maximum_time):
    """Compare provider grid epochs and half-grid interpolation to an independent finer rollout."""
    initial = simulator.background_initial_state()
    history = rollout(simulator._background_acceleration, initial['positions'], initial['velocities'],
                      t_launch=0., duration=maximum_time)
    fine = diagnostic_rollout(simulator._background_acceleration, initial['positions'], initial['velocities'],
                              t_launch=0., duration=maximum_time, dt=DT/2)
    provider = _visible_positions(simulator, maximum_time)
    grid_indices = np.unique(np.rint(np.linspace(0, len(history['times'])-1, 97)).astype(int))
    grid_error = max(float(np.max(np.abs(provider(float(index*DT))-history['positions'][index])))
                     for index in grid_indices)
    half_indices = np.unique(np.rint(np.linspace(0, len(history['times'])-2, 97)).astype(int))
    half_error = max(float(np.max(np.abs(provider(float((index+.5)*DT))-fine['positions'][2*index+1])))
                     for index in half_indices)
    return {'body_count': len(initial['ids']), 'maximum_absolute_time': maximum_time,
            'grid_checks': len(grid_indices), 'half_grid_checks': len(half_indices),
            'grid_max_coordinate_error': grid_error, 'half_grid_vs_finer_rollout_max_coordinate_error': half_error,
            'initial_state_matches': bool(np.array_equal(provider(0), initial['positions'])),
            'last_time_covered': bool(np.isfinite(provider(maximum_time)).all()),
            'meaning': 'Half-grid error includes linear interpolation plus the much smaller integration difference.'}


def run_audit(archive_inputs=None):
    started = time.monotonic()
    all_probes, world_reports = {}, []
    for world in map(str, range(1, 7)):
        simulator = DevelopmentSimulator(world)
        cases = catalog.validation_cases(world)
        maximum_time = max(c['t_launch']+c['readout'][-1] for c in cases)
        spec, params = public_formula(world, simulator)
        expression = Expression(spec, [{'name': name, 'initial': value} for name, value in params.items()])
        provider = _visible_positions(simulator, maximum_time)
        probes, predictions, stats, bridge_checks = [], [], [], []
        acceleration_error = 0.
        for case in cases:
            reference = simulator.launch(case['probes'], case['t_launch'], case['readout'],
                                         source_properties=case['source_properties'])
            for index, source in enumerate(case['probes']):
                properties = agent_properties(world, case['source_properties'], source['properties'])
                round_trip = source_inputs(world, properties) == (case['source_properties'], source['properties'])
                times_correct = np.allclose(reference['times'], case['t_launch']+np.asarray(case['readout']),
                                            rtol=0, atol=1e-12)
                probe = {'probe_id': f"v15_{case['name']}_{index+1}",
                         'initial_conditions': {'r0': source['pos'], 'v0': source['vel'],
                                                't0': case['t_launch'], 'properties': properties},
                         'times': reference['times'].tolist(), 'r_obs': reference['positions'][:, index].tolist(),
                         'v_obs': reference['velocities'][:, index].tolist()}
                probes.append(probe)
                bridge_checks.append({'probe_id': probe['probe_id'], 'property_round_trip_matches': round_trip,
                                      'absolute_times_match': bool(times_correct), 'properties': properties,
                                      't0': case['t_launch'], 'first_sample': probe['times'][0],
                                      'last_sample': probe['times'][-1]})
                for t, r, v in zip(probe['times'], probe['r_obs'], probe['v_obs']):
                    actual = expression.acceleration(t, r, v, [], properties, params)
                    expected = simulator.acceleration(t, [r], source_properties=case['source_properties'],
                                                      probe_properties=source['properties'])[0]
                    acceleration_error = max(acceleration_error, float(np.max(np.abs(actual-expected))))
                prediction, measured = instrumented_rollout(spec, params, probe, provider)
                stats.append(dict(measured, probe_id=probe['probe_id']))
                if prediction is not None:
                    predictions.append(prediction)
        all_probes[world] = {probe['probe_id']: probe for probe in probes}
        metrics = numerics.errors_for_rollouts(probes, predictions) if len(predictions) == len(probes) else None
        # A mathematically zero body term forces every normal adapter lookup,
        # including one cold lazy background integration, without changing the force.
        body_spec = dict(spec, ax='(' + spec['ax'] + ')+sum_b(0*bx)')
        body_provider = _visible_positions(simulator, maximum_time)
        body_predictions, body_stats = [], []
        for probe in probes:
            prediction, measured = instrumented_rollout(body_spec, params, probe, body_provider)
            body_stats.append(dict(measured, probe_id=probe['probe_id']))
            if prediction is not None:
                body_predictions.append(prediction)
        body_metrics = (numerics.errors_for_rollouts(probes, body_predictions)
                        if len(body_predictions) == len(probes) else None)
        report = {'world_id': 'world_'+world, 'n_cases': len(cases), 'n_probes': len(probes),
                  'formula_is_public_truth_for_audit_only': True, 'formula': spec, 'parameters': params,
                  'formula_uses_bodies': expression.uses_bodies, 'acceleration_max_abs_error': acceleration_error,
                  'reference_state_acceleration_checks': sum(len(p['times']) for p in probes),
                  'normal': {'complete': metrics is not None, 'metrics': metrics['overall'] if metrics else None,
                             'max_rollout_seconds': max(r['elapsed_seconds'] for r in stats),
                             'max_rhs_calls': max(r['rhs_calls'] for r in stats), 'per_probe': stats},
                  'forced_body_lookup_zero_force': {'complete': body_metrics is not None,
                      'metrics': body_metrics['overall'] if body_metrics else None,
                      'max_rollout_seconds': max(r['elapsed_seconds'] for r in body_stats),
                      'cold_rollout_seconds': body_stats[0]['elapsed_seconds'],
                      'max_rhs_calls': max(r['rhs_calls'] for r in body_stats), 'per_probe': body_stats},
                  'bridge_checks': bridge_checks, 'background': background_audit(simulator, maximum_time)}
        world_reports.append(report)
        print(json.dumps({'world': world, 'complete': report['normal']['complete'],
                          'rmse': report['normal']['metrics']['position_rmse'] if metrics else None,
                          'max_rhs_calls': report['normal']['max_rhs_calls'],
                          'body_complete': report['forced_body_lookup_zero_force']['complete']}), flush=True)
    failed_candidates = []
    for item in (archive_inputs or {}).get('candidates', []):
        world = item['world_id'].removeprefix('world_')
        spec, params = item['law_spec'], item['fitted_parameters']
        expression = Expression(spec, [{'name': name, 'initial': value} for name, value in params.items()])
        rows = []
        # One representative of each archived failure reason suffices here;
        # a separate archive audit replays all 24 real submissions without changes.
        seen = set()
        for failure in item['failures']:
            if failure['reason'] in seen:
                continue
            seen.add(failure['reason'])
            probe = all_probes[world][failure['probe_id']]
            provider = _visible_positions(DevelopmentSimulator(world), max(p['times'][-1] for p in all_probes[world].values()))
            predicted, measured = instrumented_rollout(spec, params, probe, provider)
            initial = probe['initial_conditions']
            actual = expression.acceleration(initial['t0'], initial['r0'], initial['v0'], [],
                                             initial['properties'], params)
            source, props = source_inputs(world, initial['properties'])
            expected = DevelopmentSimulator(world).acceleration(initial['t0'], [initial['r0']],
                        source_properties=source, probe_properties=props)[0]
            measured.update(probe_id=probe['probe_id'], archived_failure_reason=failure['reason'],
                            initial_predicted_acceleration=actual.tolist(), initial_true_acceleration=expected.tolist(),
                            initial_acceleration_abs_error=float(np.linalg.norm(actual-expected)))
            if world == '4' and 'c' in params and params['c'] < 0:
                measured.update(candidate_pole_radius=math.sqrt(-params['c']),
                    last_rhs_denominator=float(np.dot(measured['last_rhs_state'][:2], measured['last_rhs_state'][:2])+params['c']))
            rows.append(measured)
        failed_candidates.append({'run_id': item['run_id'], 'law_spec': spec, 'fitted_parameters': params,
                                  'archived_failures': len(item['failures']), 'diagnostics': rows})
    source_files = ['shore_v15/evaluation.py', 'shore_v15/source.py', 'shore_agent/numerics.py',
                    'shore_agent/expressions.py', 'shore_v15/vendor/development_worlds/worlds.py',
                    'shore_v15/vendor/development_worlds/catalog.py', 'shore_v15/vendor/rift_numerics/rollout.py']
    hashes = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in source_files}
    return {'kind': 'offline_truth_informed_developer_numerical_audit_not_agent_experiment',
            'created_at': datetime.now(timezone.utc).isoformat(), 'source_sha256': hashes,
            'archive_input_source_sha256': (archive_inputs or {}).get('source_sha256'),
            'source_matches_archive_server': (hashes == archive_inputs.get('source_sha256') if archive_inputs else None),
            'catalog_version': catalog.VERSION, 'truth_numerics_version': NUMERICS_VERSION,
            'production_limits_unchanged': {'MAX_RHS_CALLS': numerics.MAX_RHS_CALLS,
                'MAX_ROLLOUT_SECONDS': numerics.MAX_ROLLOUT_SECONDS,
                'MAX_STATE': numerics.MAX_STATE, 'MAX_PHYSICAL_SPAN': numerics.MAX_PHYSICAL_SPAN},
            'worlds': world_reports, 'incomplete_candidate_diagnostics': failed_candidates,
            'archived_runs_changed': False, 'model_calls': 0, 'fits_or_submissions': 0,
            'elapsed_seconds': time.monotonic()-started,
            'limitations': ['Developer formulas are copied/transcribed from public truth for evaluator verification only; never supplied to the Agent.',
                'This audit does not measure autonomous discovery or unseen-world generalization.',
                'Wall timings are local measurements, not worst-case guarantees under arbitrary server load.',
                'Worlds 1/4 DSL radial forms are checked at nonzero radii in the fixed cases; the source separately defines zero acceleration at the exact origin.',
                'Zero body terms exercise coverage, cold startup and adapter overhead; interpolation error is measured separately and is not a proof for arbitrary ill-conditioned body-dependent candidate formulas.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--archive-inputs', type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Refusing to overwrite audit output')
    inputs = json.loads(args.archive_inputs.read_text()) if args.archive_inputs else None
    result = run_audit(inputs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({'audit_output': str(args.output.resolve()), 'elapsed_seconds': result['elapsed_seconds']}))


if __name__ == '__main__':
    main()
