"""Run exactly one real discovery session per world through the local RunManager.

No simulator definitions or candidate formulas are loaded by this driver. It
never retries POST /api/runs, resumes a failed session, expands a budget, or stops
someone else's work. Completed run artifacts remain in the console's runs/.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import getpass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

import httpx

from shore_worlds import WORLD_IDS, public_worlds
from shore_agent.schemas import SCHEMAS

PROJECT = Path(__file__).resolve().parent
SETTINGS = {'model': 'deepseek-flash', 'thinking': True, 'max_calls': None,
            'max_total_tokens': 2000000, 'max_tokens_per_call': 65536, 'noise': False, 'seed': 42}
EVALUATION = {'seed': 1871, 'n_probes': 20}
ROLE_LIMITS = {'main_max_calls': None}
RUN_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}')


class BenchmarkError(RuntimeError):
    """Fixed error codes, never request bodies, credentials, or HTTP dumps."""


class LocalService:
    def __init__(self, base_url, api_key=None, *, transport=None):
        url = urlsplit(base_url)
        if (url.scheme != 'http' or url.hostname not in ('127.0.0.1', 'localhost')
                or url.username or url.password or url.query or url.fragment
                or url.path not in ('', '/')):
            raise BenchmarkError('base_url_must_be_loopback_http')
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.token = None
        self.client = httpx.Client(base_url=self.base_url, transport=transport,
                                   timeout=30, follow_redirects=False)

    def close(self):
        self.api_key = self.token = None
        self.client.close()

    def _request(self, method, path, body=None):
        headers = {'X-Session-Token': self.token} if self.token else {}
        try:
            response = self.client.request(method, path, json=body, headers=headers)
        except httpx.HTTPError:
            # A failed POST could still have started a run: caller must not retry.
            raise BenchmarkError('local_http_transport_failed_no_retry') from None
        if response.status_code not in (200, 202):
            raise BenchmarkError(f'local_http_status_{response.status_code}')
        try:
            result = response.json()
        except ValueError:
            raise BenchmarkError('local_http_invalid_json') from None
        if not isinstance(result, dict):
            raise BenchmarkError('local_http_invalid_response')
        return result

    def bootstrap(self):
        data = self._request('GET', '/api/bootstrap')
        token = data.get('token')
        if not isinstance(token, str) or not token:
            raise BenchmarkError('local_session_token_missing')
        self.token = token
        if not data.get('api_key_configured') and not self.api_key:
            raise BenchmarkError('api_key_missing_use_server_environment_or_ask_key')
        return data

    def listing(self):
        return self._request('GET', '/api/runs')

    def start(self, world_id):
        body = dict(SETTINGS, world_id=world_id)
        if self.api_key:
            body['api_key'] = self.api_key
        try:
            result = self._request('POST', '/api/runs', body)
        finally:
            body.pop('api_key', None)
        run_id = result.get('run_id')
        if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
            raise BenchmarkError('invalid_created_run_id_no_retry')
        return run_id

    def snapshot(self, run_id):
        return self._request('GET', '/api/runs/' + run_id)


def _write(path, value):
    path = Path(path)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temp.replace(path)


def _timestamp():
    return datetime.now(timezone.utc).isoformat()


def _prompt_hashes(project):
    return {name: hashlib.sha256((project / 'shore_agent' / 'prompts' / name).read_bytes()).hexdigest()
            for name in ('main.txt',)}


def _configuration(project, run_id=None):
    path = project / 'runs' / run_id / 'config.json' if run_id else project / 'config.example.json'
    config = json.loads(path.read_text(encoding='utf-8'))
    allowed = {
        'environment': ('world_id', 'physics_version', 'noise', 'seed', 'reference_length', 'position_limit',
                        'velocity_limit', 'time_max', 'wall_seconds'),
        'model': ('base_url', 'model', 'thinking', 'reasoning_effort',
                  'timeout_seconds', 'main_timeout_seconds',
                  'max_calls', 'main_max_calls', 'max_tokens_per_call',
                  'max_total_tokens', 'max_retries'),
        'agent': ('max_no_action', 'max_turns', 'max_rounds'),
        'numerics': ('max_nfev',),
    }
    result = {group: {key: config.get(group, {}).get(key) for key in keys if key in config.get(group, {})}
              for group, keys in allowed.items()}
    # A configured API URL cannot smuggle credentials into reproducibility files.
    parsed = urlsplit(result['model'].get('base_url', ''))
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise BenchmarkError('credential_bearing_model_url_not_allowed')
    return result


def _validate_configuration(config, world_id=None):
    model = config.get('model', {})
    if any(model.get(key) is not None for key in ('max_calls', 'main_max_calls')):
        raise BenchmarkError('server_call_limits_must_be_unlimited')
    if any(config.get('agent', {}).get(key) is not None for key in ('max_turns', 'max_rounds')):
        raise BenchmarkError('server_round_limits_must_be_unlimited')
    if world_id is not None:
        expected = {'environment': {'world_id': world_id, 'noise': False, 'seed': 42},
                    'model': {k: v for k, v in SETTINGS.items() if k not in ('noise', 'seed')}}
        if any(config.get(group, {}).get(k) != v for group, values in expected.items() for k, v in values.items()):
            raise BenchmarkError('created_run_configuration_mismatch')


def _config_hash(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def summarize_snapshot(snapshot, world_id, configuration, elapsed_seconds):
    """Pure projection of completed, public evidence; never invents a submission."""
    result = snapshot.get('result') or {}
    usage = snapshot.get('model_usage') or result.get('model_usage') or {}
    budget = snapshot.get('budget') or result.get('budget') or {}
    records = snapshot.get('records') or {}
    accepted = [s for s in records.get('submissions', [])
                if s.get('status') == 'accepted' and s.get('session_ended') is True]
    submission = accepted[0] if len(accepted) == 1 and snapshot.get('status') == 'submitted' else None
    law = next((law for law in records.get('laws', []) if submission and law.get('law_id') == submission.get('law_id')), None)
    evaluation = snapshot.get('evaluation')
    if evaluation and evaluation.get('world_id', 'world_1') != world_id:
        raise BenchmarkError('evaluation_world_identity_mismatch')
    physics_version = configuration.get('environment', {}).get('physics_version')
    if evaluation and physics_version and evaluation.get('physics_version') != physics_version:
        raise BenchmarkError('evaluation_physics_version_mismatch')
    if evaluation and (evaluation.get('seed') != EVALUATION['seed'] or evaluation.get('n_trajectories') != EVALUATION['n_probes']):
        raise BenchmarkError('evaluation_protocol_mismatch')
    evaluated = bool(submission and evaluation and evaluation.get('complete') and evaluation.get('overall'))
    remaining = budget.get('energy_remaining')
    wall_remaining = budget.get('wall_seconds_remaining')
    wall_limit = configuration.get('environment', {}).get('wall_seconds')
    return {'world_id': world_id, 'physics_version': physics_version,
            'run_id': snapshot.get('id'), 'status': snapshot.get('status', 'unknown'),
            'reason': result.get('reason'), 'calls': usage.get('calls'),
            'main_calls': usage.get('roles', {}).get('main', {}).get('calls'),
            'analyst_calls': usage.get('roles', {}).get('analyst', {}).get('calls', 0),
            'tokens': usage.get('total_tokens'), 'prompt_tokens': usage.get('prompt_tokens'),
            'completion_tokens': usage.get('completion_tokens'),
            'conservative_reserved_tokens': usage.get('conservative_reserved_tokens'),
            'energy_remaining': remaining, 'energy_used': 100 - remaining if isinstance(remaining, (int, float)) else None,
            'law': {'law_id': law.get('law_id'), 'law_spec': law.get('law_spec'),
                    'fitted_parameters': law.get('fitted_parameters')} if law else None,
            'law_versions': len(records.get('laws', [])), 'accepted_submission': bool(submission),
            'independent_evaluation_complete': evaluated,
            'independent_rmse': evaluation.get('overall') if evaluated else None,
            'evaluation_status': snapshot.get('evaluation_status') or ('complete' if evaluated else 'unavailable'),
            'evaluation_failures': evaluation.get('failures') if evaluation else None,
            'session_wall_seconds': max(0, wall_limit - wall_remaining)
                if isinstance(wall_limit, (int, float)) and isinstance(wall_remaining, (int, float)) else None,
            'wall_seconds_including_evaluation': elapsed_seconds}


def _markdown(summary):
    lines = ['# Five-world real Agent benchmark', '',
             'One scheduled attempt per world; incomplete and failed sessions remain in the comparison. '
             'Local acceptance and prediction error are reported separately; no success threshold is imposed.', '',
             '| World | Run | Status / reason | Calls | Tokens | Energy used | Submitted law | Position RMSE | Velocity RMSE | Wall seconds |',
             '|---|---|---|---:|---:|---:|---|---:|---:|---:|']
    def cell(value):
        if value is None:
            return '—'
        return str(value).replace('|', '\\|').replace('\n', ' ')
    for row in summary['worlds']:
        metric = row.get('independent_rmse') or {}
        values = [row['world_id'], row.get('run_id'), row['status'] + ' / ' + str(row.get('reason') or ''),
                  row.get('calls'), row.get('tokens'), row.get('energy_used'),
                  (row.get('law') or {}).get('law_id'), metric.get('position_rmse'), metric.get('velocity_rmse'),
                  round(row['wall_seconds_including_evaluation'], 2) if row.get('wall_seconds_including_evaluation') is not None else None]
        lines.append('| ' + ' | '.join(cell(value) for value in values) + ' |')
    lines += ['', 'Full law expressions, configurations, prompt hashes and evaluation status are in summary.json and manifest.json.',
              'A missing RMSE is not a zero error. No failed session is replaced by a rerun or a manually supplied law.', '']
    return '\n'.join(lines)


def run_benchmark(service, output_dir, *, project_root=PROJECT, poll_seconds=2, wait_seconds=3900,
                  sleep=time.sleep, monotonic=time.monotonic):
    project = Path(project_root).resolve()
    output = Path(output_dir).resolve()
    if output.exists() and any(output.iterdir()):
        raise BenchmarkError('output_directory_must_be_new_or_empty')
    base_config = _configuration(project)
    _validate_configuration(base_config)
    hashes = _prompt_hashes(project)
    bootstrap = service.bootstrap()
    if bootstrap.get('active_run_id') is not None:
        raise BenchmarkError('active_run_exists_no_work_stopped')
    output.mkdir(parents=True, exist_ok=True)
    manifest = {'benchmark_kind': 'real_agent_once_per_world', 'started_at': _timestamp(),
                'status': 'running', 'base_url': service.base_url, 'settings': dict(SETTINGS),
                'role_limits': dict(ROLE_LIMITS), 'evaluation': dict(EVALUATION),
                'tool_names': [tool['function']['name'] for tool in SCHEMAS],
                'agent_architecture': 'single_agent',
                'prompt_sha256': hashes, 'base_configuration': base_config,
                'automatic_reruns': False, 'automatic_budget_expansion': False,
                'worlds': [{'world_id': w['id'], 'name': w['name'], 'status': 'not_started', 'run_id': None}
                           for w in public_worlds()]}
    summary = {'benchmark_kind': manifest['benchmark_kind'], 'started_at': manifest['started_at'],
               'status': 'running', 'worlds': copy.deepcopy(manifest['worlds']),
               'interpretation': 'No success threshold; failed/incomplete runs are retained, not counted as discoveries.'}

    def checkpoint():
        summary['locally_submitted_count'] = sum(bool(row.get('accepted_submission')) for row in summary['worlds'])
        summary['independently_evaluated_count'] = sum(bool(row.get('independent_evaluation_complete')) for row in summary['worlds'])
        _write(output / 'manifest.json', manifest)
        _write(output / 'summary.json', summary)
        (output / 'comparison.md').write_text(_markdown(summary), encoding='utf-8')

    checkpoint()
    try:
        for index, world_id in enumerate(WORLD_IDS):
            if service.listing().get('active_run_id') is not None:
                raise BenchmarkError('active_run_exists_no_work_stopped')
            if _prompt_hashes(project) != hashes:
                raise BenchmarkError('prompts_changed_between_runs')
            entry = manifest['worlds'][index]
            entry['status'] = 'starting'
            entry['started_at'] = _timestamp()
            checkpoint()
            start = monotonic()
            run_id = service.start(world_id)  # Deliberately one POST, no retry.
            entry.update(run_id=run_id, status='running')
            summary['worlds'][index].update(run_id=run_id, status='running')
            checkpoint()
            print(f'BENCHMARK {index + 1}/{len(WORLD_IDS)} world={world_id} run_id={run_id} started', flush=True)
            configuration = _configuration(project, run_id)
            _validate_configuration(configuration, world_id)
            expected = copy.deepcopy(base_config)
            expected['environment'].update(world_id=world_id, noise=False, seed=42)
            expected['model'].update({k: v for k, v in SETTINGS.items() if k not in ('noise', 'seed')})
            if configuration != expected:
                raise BenchmarkError('server_configuration_changed_no_further_runs')
            entry.update(configuration=configuration, configuration_sha256=_config_hash(configuration),
                         prompt_sha256=hashes)
            checkpoint()
            prior = None
            while True:
                snapshot = service.snapshot(run_id)
                if snapshot.get('id') != run_id or type(snapshot.get('running')) is not bool:
                    raise BenchmarkError('invalid_run_snapshot')
                if snapshot.get('world_id', world_id) != world_id:
                    raise BenchmarkError('snapshot_world_identity_mismatch')
                usage = snapshot.get('model_usage') or {}
                state = (snapshot.get('status'), usage.get('calls', 0), usage.get('total_tokens', 0))
                if state != prior:
                    print(f'BENCHMARK world={world_id} run_id={run_id} status={state[0]} calls={state[1]} tokens={state[2]}', flush=True)
                    prior = state
                if not snapshot['running']:
                    break  # The owned worker includes post-session evaluation.
                if monotonic() - start > wait_seconds:
                    raise BenchmarkError('monitor_deadline_reached_run_left_untouched')
                sleep(poll_seconds)
            row = summarize_snapshot(snapshot, world_id, configuration, monotonic() - start)
            summary['worlds'][index] = row
            entry.update(status=row['status'], finished_at=_timestamp())
            checkpoint()
            print(f'BENCHMARK world={world_id} run_id={run_id} finished reason={row["reason"]}', flush=True)
        manifest['status'] = summary['status'] = 'completed_all_attempts'
    except (BenchmarkError, KeyboardInterrupt) as exc:
        manifest['status'] = summary['status'] = 'interrupted_no_automatic_retry'
        manifest['error'] = summary['error'] = str(exc) if isinstance(exc, BenchmarkError) else 'monitor_interrupted'
        manifest['finished_at'] = summary['finished_at'] = _timestamp()
        checkpoint()
        raise
    except (OSError, ValueError, KeyError, TypeError):
        manifest['status'] = summary['status'] = 'artifact_or_protocol_error_no_automatic_retry'
        manifest['finished_at'] = summary['finished_at'] = _timestamp()
        checkpoint()
        raise BenchmarkError('artifact_or_protocol_error_no_automatic_retry') from None
    manifest['finished_at'] = summary['finished_at'] = _timestamp()
    checkpoint()
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8765', help='Existing local console; it must be idle.')
    parser.add_argument('--output-dir', help='New/empty benchmark report directory; actual sessions stay in runs/.')
    parser.add_argument('--ask-key', action='store_true', help='Read API key without echo; keep only in memory. Otherwise reuse server key or environment.')
    parser.add_argument('--poll-seconds', type=float, default=2, help='Read-only console polling interval, 0.25..60 seconds.')
    parser.add_argument('--wait-seconds', type=float, default=3900, help='Per-run monitor limit; expiry leaves the session untouched.')
    args = parser.parse_args()
    if not math.isfinite(args.poll_seconds) or not 0.25 <= args.poll_seconds <= 60:
        parser.error('--poll-seconds must be between 0.25 and 60')
    if not math.isfinite(args.wait_seconds) or args.wait_seconds <= 0:
        parser.error('--wait-seconds must be positive and finite')
    output = args.output_dir or str(PROJECT / 'experiments' / datetime.now(timezone.utc).strftime('five-worlds-%Y%m%d-%H%M%S'))
    api_key = getpass.getpass('DeepSeek API key (not saved): ') if args.ask_key else os.environ.get('DEEPSEEK_API_KEY')
    service = None
    try:
        service = LocalService(args.base_url, api_key)
        api_key = None
        result = run_benchmark(service, output, poll_seconds=args.poll_seconds, wait_seconds=args.wait_seconds)
        print(f'BENCHMARK complete reports={Path(output).resolve()} submitted={result["locally_submitted_count"]}/{len(WORLD_IDS)}', flush=True)
    except BenchmarkError as exc:
        parser.exit(2, f'Benchmark stopped: {exc}. No existing session was stopped or retried.\n')
    except KeyboardInterrupt:
        parser.exit(130, 'Benchmark monitoring interrupted; active session was left untouched.\n')
    finally:
        api_key = None
        if service is not None:
            service.close()


if __name__ == '__main__':
    main()
