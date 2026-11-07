"""Isolated exact-label / velocity-difference PySR diagnostic, never Agent input.

Both arms use identical acquired trajectory states, discovery weights and direct
backend options. A uses exact acceleration; B uses observed velocity differences.
No equation, world identity, holdout labels or template is supplied to search.
The production tool remains observation-only. Nothing runs when imported.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FEATURES = ['t', 'x', 'y', 'vx', 'vy', 'mass', 'charge']
MODES = ('A_exact', 'B_velocity_difference')
SEARCH_SECONDS = 60
THREADS = 4
WORKERS = 4
SEED = 42


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def aligned_data(dataset, split):
    """Extract common states; check exact labels against every interior timestamp."""
    import numpy as np
    from shore_agent.symbolic_regression import prepare_dataset
    probes = dataset['train_probes' if split == 'train' else 'heldout_probes']
    prepared = prepare_dataset(probes)
    if prepared['feature_names'] != FEATURES:
        raise ValueError('Diagnostic requires all seven varying features in both splits')
    labels = []
    for probe in probes:
        exact = dataset['exact_acceleration'][split][probe['probe_id']]
        times, values = np.asarray(exact['times']), np.asarray(exact['values'])
        expected = np.asarray(probe['times'])[1:-1]
        if (times.shape != expected.shape or not np.array_equal(times, expected)
                or values.shape != (len(expected), 2) or not np.isfinite(values).all()):
            raise ValueError('Exact labels must align with each observed interior state')
        labels.append(values)
    return prepared, np.concatenate(labels)


def acceleration_metrics(predicted, truth, weights):
    import numpy as np
    predicted, truth, weights = np.asarray(predicted), np.asarray(truth), np.asarray(weights)
    if predicted.shape != truth.shape or not np.isfinite(predicted).all():
        return {'status': 'invalid_prediction', 'nrmse': None}
    weights = weights / weights.sum()
    mse = np.sum(weights[:, None] * (predicted-truth)**2, axis=0)
    signal = np.sum(weights[:, None] * truth**2, axis=0)
    return {'status': 'finite', 'mse_by_axis': mse.tolist(),
            'nrmse_by_axis': np.sqrt(mse / np.maximum(signal, 1e-30)).tolist(),
            'nrmse': float(np.sqrt(mse.sum() / max(float(signal.sum()), 1e-30))),
            'normalization': 'sqrt(weighted MSE / weighted mean exact acceleration squared)'}


def _axis_metrics(source, data, exact, axis):
    import numpy as np
    from shore_agent.symbolic_regression import _evaluate_array
    features = {name: data['X'][:, index] for index, name in enumerate(data['feature_names'])}
    try:
        prediction = np.broadcast_to(_evaluate_array(source, features), (len(exact),))[:, None]
        return acceleration_metrics(prediction, exact[:, axis:axis+1], data['weights'])
    except (ValueError, OverflowError, ZeroDivisionError, TypeError) as exc:
        return {'status': 'invalid_prediction', 'error': type(exc).__name__, 'nrmse': None}


def _pair_metrics(candidate, data, exact):
    import numpy as np
    from shore_agent.symbolic_regression import _evaluate_array
    context = {name: data['X'][:, index] for index, name in enumerate(data['feature_names'])}
    context.update({p['name']: p['initial'] for p in candidate['parameter_spec']})
    try:
        prediction = np.column_stack([np.broadcast_to(_evaluate_array(candidate['law_spec'][axis], context),
                                                      (len(exact),)) for axis in ('ax', 'ay')])
        return acceleration_metrics(prediction, exact, data['weights'])
    except (ValueError, OverflowError, ZeroDivisionError, TypeError) as exc:
        return {'status': 'invalid_prediction', 'error': type(exc).__name__, 'nrmse': None}


def _raw_pair_metrics(sources, data, exact):
    # No production exporter/parameter limit is allowed to hide backend accuracy.
    return _pair_metrics({'law_spec':sources, 'parameter_spec':[]}, data, exact)


def evaluate_search(result, dataset):
    """Score all raw rows; select only by training search loss, never holdout."""
    from shore_agent.symbolic_regression import export_candidate, MAX_INTERNAL_PARAMETERS
    train, train_exact = aligned_data(dataset, 'train')
    heldout, heldout_exact = aligned_data(dataset, 'heldout')
    axes, selected = {}, {}
    for index, axis in enumerate(('ax', 'ay')):
        source_rows = result.get('axis_equations', {}).get(axis, [])
        rows = []
        delivered = {row['source'] for row in result.get('axis_candidates', {}).get(axis, [])}
        for original in source_rows:
            row = dict(original)
            row['training_exact_acceleration'] = _axis_metrics(row['source'], train, train_exact, index)
            row['heldout_exact_acceleration'] = _axis_metrics(row['source'], heldout, heldout_exact, index)
            row['retained_as_axis_candidate'] = row['source'] in delivered
            try:
                exported = export_candidate(row['source'] if index == 0 else '0',
                                            row['source'] if index == 1 else '0', FEATURES,
                                            _parameter_limit=MAX_INTERNAL_PARAMETERS)
                row['export'] = {'status': 'exportable_component', 'parameter_count': len(exported['parameter_spec']),
                                 'within_five_parameter_limit': len(exported['parameter_spec']) <= 5}
            except ValueError as exc:
                row['export'] = {'status': 'rejected', 'reason': str(exc)}
            rows.append(row)
        finite = [r for r in rows if isinstance(r.get('loss'), (float, int)) and math.isfinite(r['loss'])]
        raw = [r for r in finite if r.get('origin') == 'pysr']
        frontier = [r for r in raw if not any(
            o['loss'] <= r['loss'] and o['complexity'] <= r['complexity']
            and (o['loss'] < r['loss'] or o['complexity'] < r['complexity']) for o in raw)]
        best = min(raw, key=lambda r: (r['loss'], r['complexity']), default=None)
        selected[axis] = best
        axes[axis] = {'all_candidates': rows, 'raw_pysr_frontier': frontier,
                      'lowest_training_loss_raw_pysr': best,
                      'selection_uses_holdout': False}
    best_pair = None
    if all(selected.values()):
        sources = {axis:selected[axis]['source'] for axis in ('ax','ay')}
        best_pair = {'raw_sources':sources,
                     'training':_raw_pair_metrics(sources,train,train_exact),
                     'heldout':_raw_pair_metrics(sources,heldout,heldout_exact)}
        try:
            candidate = export_candidate(selected['ax']['source'], selected['ay']['source'], FEATURES,
                                         _parameter_limit=MAX_INTERNAL_PARAMETERS)
            best_pair.update(export_status='exportable', **{'law_spec': candidate['law_spec'], 'parameter_spec': candidate['parameter_spec'],
                         'parameter_count': len(candidate['parameter_spec']),
                         'within_five_parameter_limit': len(candidate['parameter_spec']) <= 5})
        except ValueError as exc:
            best_pair.update(export_status='rejected', reason=str(exc))
    return {'axes': axes, 'raw_training_best_pair': best_pair,
            'production_pairs': [dict(candidate=candidate,
                                     training=_pair_metrics(candidate, train, train_exact),
                                     heldout=_pair_metrics(candidate, heldout, heldout_exact))
                                 for candidate in result.get('candidates', [])],
            'velocity_difference_label_error': {
                'training': acceleration_metrics(train['y'], train_exact, train['weights']),
                'heldout': acceleration_metrics(heldout['y'], heldout_exact, heldout['weights'])},
            'heldout_used_for_search_or_selection': False}


def _warmup(output):
    begin = time.monotonic()
    import numpy as np
    from pysr import PySRRegressor
    from shore_agent.symbolic_regression import BINARY_OPERATORS, UNARY_OPERATORS, SEARCH_MAXSIZE
    rng = np.random.default_rng(123)
    X = rng.uniform(.2, 1.2, (64, 7))
    y = (X[:, 0]**1.7 + np.sin(X[:, 1]) + np.cos(X[:, 2])
         + np.exp(X[:, 3]) + np.log(X[:, 4]) + np.sqrt(X[:, 5]))
    model = PySRRegressor(binary_operators=list(BINARY_OPERATORS), unary_operators=list(UNARY_OPERATORS),
                          constraints={'^': (-1, 1)}, maxsize=SEARCH_MAXSIZE, niterations=1,
                          populations=2, population_size=27, ncycles_per_iteration=10,
                          timeout_in_seconds=2, parallelism='multithreading', warm_start=False,
                          precision=64, verbosity=0, progress=False, output_directory=str(output/'warmup'))
    model.fit(X, y, weights=np.ones(len(y)), variable_names=FEATURES)
    return time.monotonic()-begin


def direct_search(dataset, mode, output, checkpoint, model_factory=None):
    """Only numerical X, y and weights reach the backend; no world templates."""
    import numpy as np
    from shore_agent.symbolic_regression import BINARY_OPERATORS, UNARY_OPERATORS, SEARCH_MAXSIZE
    if model_factory is None:
        from pysr import PySRRegressor
        model_factory = PySRRegressor
    prepared, exact = aligned_data(dataset, 'train')
    if mode not in MODES:
        raise ValueError('Unknown diagnostic arm')
    targets = exact if mode == 'A_exact' else prepared['y']
    begin = time.monotonic()
    axis_rows = [[], []]
    result = {'status':'running', 'backend':'direct_pysr',
              'target':'diagnostic_exact_acceleration' if mode == 'A_exact' else 'observed_velocity_finite_difference',
              'search_axes_completed':[], 'axis_search_seconds':[], 'candidates':[],
              'feature_names':FEATURES, 'search_configuration':{
                  'maxsize': SEARCH_MAXSIZE, 'binary_operators':list(BINARY_OPERATORS),
                  'unary_operators':list(UNARY_OPERATORS), 'random_state':SEED,
                  'time_budget_seconds':SEARCH_SECONDS, 'axis_timeout_seconds':SEARCH_SECONDS/2,
                  'parallelism':'multithreading', 'linear_seeds':False,
                  'world_identity_or_formula_passed_to_backend':False}}
    for index, axis in enumerate(('ax', 'ay')):
        options = dict(binary_operators=list(BINARY_OPERATORS), unary_operators=list(UNARY_OPERATORS),
            constraints={'^':(-1, 1)}, maxsize=SEARCH_MAXSIZE, niterations=1000000,
            populations=8, population_size=27, ncycles_per_iteration=100,
            timeout_in_seconds=SEARCH_SECONDS/2, random_state=SEED+index, parallelism='multithreading',
            warm_start=False, precision=64, verbosity=0, progress=False,
            output_directory=str(output/axis))
        started = time.monotonic()
        model = model_factory(**options)
        model.fit(prepared['X'], targets[:, index], weights=prepared['weights'], variable_names=FEATURES)
        result['axis_search_seconds'].append(time.monotonic()-started)
        for _, row in model.equations_.iterrows():
            loss, complexity, source = float(row['loss']), int(row['complexity']), str(row['sympy_format'])
            if math.isfinite(loss) and loss >= 0 and 1 <= complexity <= SEARCH_MAXSIZE and len(source) <= 4096:
                axis_rows[index].append({'source':source, 'loss':loss, 'complexity':complexity, 'origin':'pysr'})
        result['search_axes_completed'].append(axis)
        result['axis_equations'] = dict(zip(('ax','ay'), axis_rows))
        result['elapsed_seconds'] = time.monotonic()-begin
        checkpoint(result)
    result.update(status='completed', elapsed_seconds=time.monotonic()-begin,
                  search_budget_exceeded=time.monotonic()-begin > SEARCH_SECONDS)
    checkpoint(result)
    return result


def package_search(result, dataset, mode):
    """Same production selector for both raw searches, outside backend timing.

    Only discovery states and their arm-specific target labels are available.
    Fixed independent holdout data is reserved for evaluate_search below.
    """
    from shore_agent.symbolic_regression import _select_candidates
    prepared, exact = aligned_data(dataset, 'train')
    if mode == 'A_exact': prepared['y'] = exact
    started = time.monotonic()
    rows = [result.get('axis_equations',{}).get(axis,[]) for axis in ('ax','ay')]
    candidates, audit = _select_candidates(rows, prepared, 3, started+10, {})
    # Preserve raw HOF rows even if production DSL/export validation rejects them.
    raw_rows = result.get('axis_equations', {})
    return dict(result, **{key:value for key,value in audit.items() if key != 'axis_equations'},
                axis_equations=raw_rows, packaging_axis_equations=audit.get('axis_equations'),
                candidates=candidates, packaging_seconds=time.monotonic()-started,
                packaging_budget_seconds=10, packaging_is_separate_diagnostic=True)


def worker(dataset_file, mode, output):
    # This process is launched with 4 Julia threads and one BLAS/OpenMP thread.
    # Existing production PySR workers and GPU inference services are untouched.
    dataset = json.loads(Path(dataset_file).read_text())
    output = Path(output)
    started = time.monotonic()
    report = {'mode':mode, 'status':'warming', 'world_id':dataset['world_id'], 'model_calls':0}
    write_json(output/'progress.json', report)
    try:
        report['warmup_seconds'] = _warmup(output)
        report.update(status='searching', search_started_at=datetime.now(timezone.utc).isoformat())
        write_json(output/'progress.json', report)
        def checkpoint(result):
            report['search_result'] = result
            write_json(output/'progress.json', report)
        begin = time.monotonic()
        result = direct_search(dataset, mode, output, checkpoint)
        report.update(search_result=result, search_seconds=time.monotonic()-begin, status='postprocessing')
        write_json(output/'progress.json', report)
        result = package_search(result, dataset, mode)
        report.update(search_result=result, packaging_seconds=result['packaging_seconds'], status='evaluating')
        write_json(output/'progress.json', report)
        evaluation_started = time.monotonic()
        report['diagnostics'] = evaluate_search(result, dataset)
        report.update(evaluation_seconds=time.monotonic()-evaluation_started, status='completed')
    except Exception as exc:
        report.update(status='error', error={'type':type(exc).__name__, 'message':str(exc)[:1000]})
    finally:
        report['total_seconds'] = time.monotonic()-started
        write_json(output/'result.json', report)


def _read(path, default=None):
    try: return json.loads(Path(path).read_text())
    except (OSError, ValueError): return default


def _stop(process):
    if process.poll() is None:
        try: os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError: pass
    process.wait(timeout=10)


def launch_job(dataset_file, mode, output, stop_requested=None):
    output.mkdir()
    env = dict(os.environ, JULIA_NUM_THREADS=str(THREADS), OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
               MKL_NUM_THREADS='1', PYTHONPATH=str(ROOT))
    started, search_started, evaluation_started = time.monotonic(), None, None
    process = None
    reason = None
    try:
        if stop_requested is not None and stop_requested():
            result = {'mode':mode, 'world_id':_read(dataset_file)['world_id'],
                      'status':'not_started', 'reason':'study_interrupted'}
            write_json(output/'result.json', result)
            return result
        with (output/'worker.log').open('wb') as log:
            process = subprocess.Popen([sys.executable, '-u', __file__, '--worker', '--dataset',str(dataset_file),
                                        '--mode',mode,'--output',str(output)], cwd=ROOT, env=env,
                                       stdout=log, stderr=log, start_new_session=True)
            while process.poll() is None:
                progress = _read(output/'progress.json', {})
                status = progress.get('status')
                if status == 'searching' and search_started is None: search_started = time.monotonic()
                if status in ('postprocessing','evaluating') and evaluation_started is None: evaluation_started = time.monotonic()
                if search_started is None and time.monotonic()-started > 900: reason='warmup_timeout'
                if status == 'searching' and search_started and time.monotonic()-search_started > SEARCH_SECONDS+3:
                    reason='search_hard_timeout'
                if status in ('postprocessing','evaluating') and evaluation_started and time.monotonic()-evaluation_started > 120:
                    reason='diagnostic_evaluation_timeout'
                if stop_requested is not None and stop_requested(): reason='study_interrupted'
                if reason: _stop(process); break
                time.sleep(.1)
            process.wait()
    finally:
        if process is not None and process.poll() is None: _stop(process)
    result = _read(output/'result.json')
    if result is None:
        result = _read(output/'progress.json', {'mode':mode})
        result.update(status='interrupted', reason=reason or 'worker_exited_without_result',
                      total_seconds=time.monotonic()-started)
        write_json(output/'result.json', result)
    return result


def run(bundle_file, output, stop_requested=None):
    bundle = json.loads(Path(bundle_file).read_text())
    datasets = bundle['datasets']
    if len(datasets) != 6 or {d['world_id'] for d in datasets} != {f'world_{i}' for i in range(1,7)}:
        raise ValueError('Expected one immutable dataset for each of six development worlds')
    for dataset in datasets:
        aligned_data(dataset, 'train'); aligned_data(dataset, 'heldout')
        if {p['probe_id'] for p in dataset['train_probes']} & {p['probe_id'] for p in dataset['heldout_probes']}:
            raise ValueError('Training and holdout IDs must be disjoint')
    output = Path(output).resolve()
    if output == ROOT/'runs' or output.is_relative_to(ROOT/'runs') or any(
            output == ROOT/name or output.is_relative_to(ROOT/name)
            for name in ('shore_agent','shore_v15','shore_sim')):
        raise ValueError('Diagnostic results must remain outside Agent runs and source packages')
    output.mkdir(parents=True, exist_ok=False)
    sources = ('deployment/check_symbolic_identifiability.py', 'deployment/check_symbolic_trajectory_data.py',
               'shore_agent/symbolic_regression.py', 'shore_agent/expressions.py',
               'shore_v15/vendor/development_worlds/worlds.py', 'experiments/E5/symbolic-identifiability-protocol.json')
    report = {'kind':'isolated_symbolic_identifiability_not_agent_score', 'status':'running',
              'created_at':datetime.now(timezone.utc).isoformat(), 'model_calls':0, 'physical_missions':0,
              'cpu_workers':WORKERS, 'julia_threads_per_worker':THREADS,
              'dataset_sha256':hashlib.sha256(Path(bundle_file).read_bytes()).hexdigest(),
              'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources if (ROOT/p).is_file()},
              'protocol':{'modes':MODES,'attempts_per_world_per_mode':1,'budget_seconds':SEARCH_SECONDS,
                          'pysr_seed':SEED,'holdout_used_for_selection':False,'automatic_retries':False}, 'results':[]}
    write_json(output/'summary.json', report)
    jobs = []
    for index, dataset in enumerate(datasets):
        data_file = output/f'dataset_{index+1}.json'
        write_json(data_file, dataset)
        # Alternate A/B order across worlds; every planned attempt is retained.
        for mode in MODES if index % 2 == 0 else MODES[::-1]:
            jobs.append((data_file,mode,output/f'{dataset["world_id"]}_{mode}'))
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(launch_job,*job,stop_requested):job for job in jobs}
        for future in as_completed(futures):
            result = future.result()
            report['results'].append(result)
            write_json(output/'summary.json', report)
            print(json.dumps({k:result.get(k) for k in ('world_id','mode','status','warmup_seconds','search_seconds','total_seconds')}), flush=True)
    report.update(status='interrupted' if stop_requested is not None and stop_requested() else 'completed',
                  total_seconds=time.monotonic()-started)
    write_json(output/'summary.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--mode', choices=MODES)
    args = parser.parse_args()
    if args.worker:
        if args.mode is None: parser.error('--worker requires --mode')
        worker(args.dataset, args.mode, args.output)
    else:
        stopped = threading.Event()
        previous = {sig:signal.signal(sig,lambda *_:stopped.set()) for sig in (signal.SIGINT,signal.SIGTERM)}
        try:
            run(args.dataset, args.output, stop_requested=stopped.is_set)
        finally:
            for sig,handler in previous.items(): signal.signal(sig,handler)


if __name__ == '__main__':
    main()
