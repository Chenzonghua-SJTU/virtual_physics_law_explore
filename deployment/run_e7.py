"""Interleave two full repeats of the frozen E6 baseline +/- PySR.

All 24 attempts are retained, with at most one active mission per model endpoint.
Queues are outside mission time. No per-world retries or answer selection.
"""
import hashlib
import json
import signal
import sys
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmark_v15 import (configuration, prepare, launch, finished, terminate,
                           watchdog_expired, read_json, save_summary, _write)
from shore_agent.web_jobs import RunManager
from shore_worlds import V15_WORLD_IDS


ENDPOINTS = tuple(f'http://127.0.0.1:{p}/v1' for p in range(8000, 8004))
SYMBOLIC_ENDPOINT = 'http://127.0.0.1:8890'
MODEL = 'qwen3.8-27b'
MAX_PREFLIGHT_BYTES = 1024 * 1024


def plans(project):
    """Resolve every output path without reserving a directory or starting a mission."""
    result = []
    # Counterbalance enabled/disabled order across repeats in the job queue.
    for enabled, repeat in ((False, 1), (True, 1), (True, 2), (False, 2)):
        config = configuration(project, config_path=project/'deployment/config.e6.final.json',
                               thinking=False, ruleset='e5')
        config['model'].pop('sampling_seed', None)
        config.setdefault('numerics', {}).update(symbolic_regression_enabled=enabled,
            symbolic_regression_endpoint=SYMBOLIC_ENDPOINT, symbolic_regression_seed=42)
        name = f'e7-qwen38-pysr-{ "on" if enabled else "off"}-20261107-r{repeat:02d}'
        result.append({'output': project/'experiments/E5'/name, 'config': config,
                       'planned_runs': {world: project/'runs'/f'{name}-{world}' for world in V15_WORLD_IDS}})
    return result


def _check_fresh_paths(batches):
    paths = [path for batch in batches for path in (batch['output'], *batch['planned_runs'].values())]
    if any(path.exists() or path.is_symlink() for path in paths):
        raise ValueError('experiment_or_run_directory_already_exists_no_overwrite')


def _remote_json(url, opener):
    try:
        with opener(url, timeout=5) as response:
            if response.status != 200:
                raise ValueError('http_status')
            body = response.read(MAX_PREFLIGHT_BYTES + 1)
        if len(body) > MAX_PREFLIGHT_BYTES:
            raise ValueError('response_size')
        result = json.loads(body)
        if not isinstance(result, dict):
            raise ValueError('response_shape')
        return result
    except Exception:
        raise RuntimeError(f'E7 preflight endpoint unavailable or invalid: {url}') from None


def preflight(batches, endpoints=ENDPOINTS, *, opener=None):
    """Fail before creating any universe run if an endpoint or destination is unsuitable."""
    _check_fresh_paths(batches)
    opener = opener or urlopen
    for endpoint in endpoints:
        listing = _remote_json(endpoint.rstrip('/') + '/models', opener)
        models = listing.get('data')
        if not isinstance(models, list) or not any(
                isinstance(item, dict) and item.get('id') == MODEL for item in models):
            raise RuntimeError(f'E7 preflight expected {MODEL} at {endpoint}')
    health = _remote_json(SYMBOLIC_ENDPOINT + '/health', opener)
    if type(health.get('ready')) is not int or health['ready'] != 4 or type(health.get('busy')) is not int or health['busy'] != 0:
        raise RuntimeError('E7 preflight requires four ready, idle PySR workers')
    if any(batch.get('require_staged_warmup') for batch in batches):
        warmup=health.get('worker_warmup',[])
        if (health.get('actual_julia_threads')!=[4]*4 or len(warmup)!=4 or any(
                {(stage.get('stage'),stage.get('maxsize')) for stage in worker.get('warmup_stages',[])}
                !={('algebra',24),('full',48)} for worker in warmup)):
            raise RuntimeError('E8 requires actual four-thread workers warmed for algebra24 and full48')
    # Network checks take time. Recheck all arms before the first reservation.
    _check_fresh_paths(batches)


def _finish_attempt(item, *, reason=None):
    if item['terminal']:
        return
    process = item['process']
    elapsed = 0 if item['started'] is None else max(0, time.monotonic() - item['started'])
    finished(item['directory'], process.returncode if process is not None else None, elapsed, reason=reason)
    item['terminal'] = True


def _partial_preparation_summary(batch):
    """A failed prepare may have no manifest or even no complete config.json."""
    manifest = {'experiment_id': batch['output'].name, 'status': 'interrupted',
                'preparation_complete': False, 'configuration': batch['config'],
                'runs': {world: path.name for world, path in batch['runs'].items()},
                'unreserved_worlds': [world for world in batch['planned_runs'] if world not in batch['runs']]}
    worlds = []
    for world, directory in batch['runs'].items():
        result = read_json(directory/'result.json', {})
        worlds.append({'world_id': world, 'run_id': directory.name,
                       'status': result.get('status', 'interrupted'), 'reason': result.get('reason')})
    _write(batch['output']/'manifest.json', manifest)
    _write(batch['output']/'summary.json', dict(manifest, worlds=worlds))


def run_study(project=ROOT, *, opener=None, stop_requested=None, planned_batches=None,
              extra_source_paths=()):
    project = Path(project).resolve()
    deadline = time.monotonic() + 3600
    def checkpoint():
        if stop_requested is not None and stop_requested():
            raise KeyboardInterrupt('E7 stop requested')
        if time.monotonic() >= deadline:
            raise TimeoutError('E7 study exceeded one-hour orchestration deadline')

    if planned_batches is None:
        selection = read_json(project/'experiments/E5/e6-final-selection.json')
        if not isinstance(selection, dict) or not selection.get('selected_profile'):
            raise SystemExit('Complete E6 and freeze selection before E7')
        planned = plans(project)
    else:
        planned = list(planned_batches)
        if not planned:
            raise ValueError('at_least_one_predeclared_batch_required')
    source_hashes = {}
    for name in extra_source_paths:
        path = (project/name).resolve()
        if not path.is_relative_to(project):
            raise ValueError('source_path_outside_project')
        source_hashes[str(path.relative_to(project))] = hashlib.sha256(path.read_bytes()).hexdigest()
    preflight(planned, opener=opener)
    checkpoint()
    batches, attempts = [], {}
    active = {}
    dispatching = None
    manager = None
    completed = False
    try:
        manager = RunManager(project)
        for plan in planned:
            checkpoint()
            batch = dict(plan, manifest=None, runs={}, done=False, owns_output=False)
            batches.append(batch)
            preparation_error = None
            try:
                manifest, runs = prepare(batch['output'], batch['config'], workers=4,
                                         project=project, model_endpoints=ENDPOINTS)
                batch.update(manifest=manifest, runs=runs)
                if source_hashes:
                    manifest['source_sha256'].update(source_hashes)
                if batch.get('symbolic_runtime_preflight'):
                    manifest['symbolic_runtime_preflight']=batch['symbolic_runtime_preflight']
                if batch.get('protocol_metadata'):
                    manifest['protocol'].update(batch['protocol_metadata'])
                if batch.get('experiment_group'):
                    manifest['experiment_group'] = batch['experiment_group']
                    for directory in runs.values():
                        metadata = read_json(directory/'web.json')
                        metadata['experiment_group'] = batch['experiment_group']
                        _write(directory/'web.json', metadata)
                if source_hashes or batch.get('experiment_group') or batch.get('symbolic_runtime_preflight') or batch.get('protocol_metadata'):
                    _write(batch['output']/'manifest.json', manifest)
            except BaseException as exc:
                preparation_error = exc
                raise
            finally:
                # prepare can raise after reserving only part of the six directories.
                # If another driver wins the reservation race after preflight,
                # its output/runs must never enter this driver's cleanup registry.
                collision = (Path(preparation_error.filename) if isinstance(preparation_error, FileExistsError)
                             and preparation_error.filename else None)
                rejected = (isinstance(preparation_error, ValueError) and str(preparation_error) ==
                            'experiment_or_run_directory_already_exists_no_overwrite') or collision == batch['output']
                batch['owns_output'] = not rejected and batch['output'].is_dir() and not batch['output'].is_symlink()
                candidates = list(batch['planned_runs'].items()) if batch['owns_output'] else []
                if collision in [directory for _, directory in candidates]:
                    candidates = candidates[:next(index for index, (_, directory) in enumerate(candidates)
                                                 if directory == collision)]
                batch['runs'] = {world: directory for world, directory in candidates
                                 if directory.is_dir() and not directory.is_symlink()}
                for world, directory in batch['runs'].items():
                    attempts[directory.name] = dict(batch=batch, world=world, directory=directory,
                        process=None, started=None, endpoint=None, terminal=False)
        # Whole trajectories/worlds remain independent; this only shares GPU slots.
        pending = [attempts[batch['runs'][world].name] for world in V15_WORLD_IDS for batch in batches]
        while pending or active:
            checkpoint()
            while pending and len(active) < len(ENDPOINTS):
                checkpoint()
                occupied = {item['endpoint'] for item in active.values()}
                endpoint = next(p for p in ENDPOINTS if p not in occupied)
                # Keep this attempt in both the all-reserved registry and pending
                # until launch has returned and its process is registered as active.
                dispatching = pending[0]
                directory = dispatching['directory']
                dispatching['endpoint'] = endpoint
                effective = read_json(directory/'config.json')
                effective['model']['base_url'] = endpoint
                effective['model']['local_model_endpoints'][effective['model']['model']] = endpoint
                _write(directory/'config.json', effective)
                metadata = read_json(directory/'web.json')
                metadata['model_endpoint'] = endpoint
                _write(directory/'web.json', metadata)
                dispatching['started'] = time.monotonic()
                try:
                    dispatching['process'] = launch(directory, '', project)
                except Exception:
                    _finish_attempt(dispatching, reason='worker_start_failed')
                    pending.pop(0)
                    dispatching = None
                    continue
                active[directory.name] = dispatching
                pending.pop(0)
                dispatching = None
                checkpoint()
                print(json.dumps({'event':'started','run_id':directory.name,'endpoint':endpoint}),flush=True)
            for run_id, item in list(active.items()):
                process, directory = item['process'], item['directory']
                code = process.poll()
                if code is None:
                    if not watchdog_expired(read_json(directory/'web.json', {})):
                        continue
                    terminate(process)
                    _finish_attempt(item, reason='exploration_watchdog_timeout')
                else:
                    process.wait()
                    _finish_attempt(item)
                active.pop(run_id)
                print(json.dumps({'event':'finished','run_id':run_id}),flush=True)
            for batch in batches:
                if batch['done']:
                    continue
                unfinished = any(not item['terminal'] and item['batch'] is batch for item in attempts.values())
                save_summary(batch['output'], batch['manifest'], batch['runs'], manager,
                             status='running' if unfinished else 'completed')
                if not unfinished:
                    batch['done'] = True
            if active:
                time.sleep(2)
        completed = True
    finally:
        original_error = sys.exc_info()[1]
        cleanup_errors = []
        if not completed:
            for item in attempts.values():
                if item['terminal']:
                    continue
                process = item['process']
                if process is not None:
                    try:
                        terminate(process)
                    except BaseException:
                        cleanup_errors.append('terminate:' + item['directory'].name)
                try:
                    _finish_attempt(item, reason='study_interrupted' if process is not None
                                    else 'not_started_study_interrupted')
                except BaseException:
                    cleanup_errors.append('finish:' + item['directory'].name)
            for batch in batches:
                if not batch['done'] and batch['owns_output']:
                    try:
                        if batch['manifest'] is None:
                            _partial_preparation_summary(batch)
                        else:
                            save_summary(batch['output'], batch['manifest'], batch['runs'], manager, status='interrupted')
                    except BaseException:
                        cleanup_errors.append('summary:' + batch['output'].name)
        if manager is not None:
            try:
                manager.close()
            except BaseException:
                cleanup_errors.append('manager_close')
        if cleanup_errors:
            message = 'E7 cleanup incomplete: ' + ', '.join(cleanup_errors)
            if original_error is not None:
                if hasattr(original_error, 'add_note'):
                    original_error.add_note(message)
                else:  # The local development interpreter may still be Python 3.10.
                    print(message, file=sys.stderr, flush=True)
            else:
                raise RuntimeError(message)


def main():
    # Defer signals to a checkpoint: an immediate exception between Popen's
    # return and process registration could otherwise orphan our own worker.
    stopped = False
    def request_stop(*_args):
        nonlocal stopped
        stopped = True
    previous = {sig: signal.signal(sig, request_stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        run_study(stop_requested=lambda: stopped)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == '__main__':
    main()
