"""Exercise the real local HTTP boundary without starting models or simulations."""
import copy
import http.client
import json
import os
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from shore_agent.web import MAX_BODY, make_server
from shore_worlds import DEFAULT_WORLD_ID, WORLD_IDS, public_worlds


class FakeManager:
    def __init__(self):
        self.started = []
        self.stopped = []
        self.deleted = []
        self.restored = []
        self.closed = False
        self.start_error = None
        self.snapshot_error = None
        self.history_error = None
        self.client_settings = None

    def client_configuration(self):
        if self.client_settings is not None:
            return self.client_settings
        config = json.loads((Path(__file__).resolve().parents[1] / 'config.example.json').read_text())
        return {'api_key_configured': bool(os.environ.get('DEEPSEEK_API_KEY')),
                'api_key_required': True,
                'models': [{'id': 'deepseek-flash', 'name': 'DeepSeek Flash'}],
                'defaults': {**{key: config['model'][key] for key in
                              ('model', 'max_calls', 'max_total_tokens', 'max_tokens_per_call', 'thinking', 'reasoning_effort')},
                             **{key: config['environment'][key] for key in ('noise', 'seed', 'world_id')}}}

    def list_runs(self):
        return {'runs': [{'id': 'demo-1', 'status': 'submitted', 'world_id': 'world_3', 'world_name': '世界 03'}], 'active_run_id': None,
                'deleted_runs': [{'id': 'deleted-1', 'status': 'incomplete',
                                  'created_at': '2026-11-01T01:00:00+00:00',
                                  'deleted_at': '2026-11-01T02:00:00+00:00',
                                  'mode': 'autonomous_discovery', 'world_id': 'world_5', 'world_name': '世界 05'}]}

    def start(self, config):
        if self.start_error:
            raise self.start_error
        self.started.append(copy.deepcopy(config))
        return 'new-run'

    def stop(self, run_id):
        if run_id == 'missing':
            raise KeyError(run_id)
        self.stopped.append(run_id)

    def snapshot(self, run_id):
        if self.snapshot_error:
            raise self.snapshot_error
        if run_id == 'missing':
            raise FileNotFoundError(run_id)
        return {'run_id': run_id, 'status': 'submitted', 'progress': ['实验已完成'],
                'world_id': 'world_3', 'world_name': '世界 03'}

    def delete(self, run_id):
        if self.history_error:
            raise self.history_error
        if run_id == 'missing':
            raise FileNotFoundError(run_id)
        self.deleted.append(run_id)
        return {'deleted_run_id': run_id}

    def restore(self, run_id):
        if self.history_error:
            raise self.history_error
        if run_id == 'missing':
            raise FileNotFoundError(run_id)
        self.restored.append(run_id)
        return {'restored_run_id': run_id}

    def close(self):
        self.closed = True


@pytest.fixture
def local_server():
    manager = FakeManager()
    server = make_server(manager=manager)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    thread.start()
    try:
        yield server, manager
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert manager.closed
        assert not thread.is_alive()


def request(server, method='GET', path='/api/bootstrap', body=None, headers=None):
    supplied = dict(headers or {})
    if method == 'POST':
        supplied.setdefault('Content-Type', 'application/json')
        supplied.setdefault('X-Session-Token', server.session_token)
        if body is None:
            body = b'{}'
    if isinstance(body, dict):
        body = json.dumps(body).encode()
    connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
    try:
        connection.request(method, path, body=body, headers=supplied)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def assert_error(result, status, code):
    actual, headers, body = result
    assert actual == status
    assert json.loads(body) == {'error': code}
    assert headers['Content-Type'].startswith('application/json')
    assert 'Access-Control-Allow-Origin' not in headers


def test_local_baseline_summary_projects_only_result_fields(local_server, monkeypatch, tmp_path):
    import shore_agent.web as web
    monkeypatch.setattr(web, 'PROJECT', tmp_path)
    directory = tmp_path / 'experiments' / 'v15-local-test'
    directory.mkdir(parents=True)
    (directory / 'summary.json').write_text(json.dumps({
        'experiment_id': 'v15-local-test', 'status': 'running', 'updated_at': 'now',
        'configuration': {'model': {'model': 'qwen3.8-27b', 'thinking': False,
                                   'deployment': 'local', 'api_key': 'not-for-browser'}},
        'worlds': [{'world_id': 'world_1', 'run_id': 'test-world_1', 'status': 'running',
                    'evaluation_complete': False, 'evaluation_score': None,
                    'physical_explanation': 'not-in-overview'}]}))
    server, _ = local_server
    status, _, body = request(server, path='/api/baselines')
    assert status == 200
    batch = json.loads(body)['batches'][0]
    assert batch['thinking'] is False
    assert batch['worlds'][0]['evaluation_score'] is None
    assert b'not-for-browser' not in body
    assert b'not-in-overview' not in body


def test_e3_derived_summary_preferred_and_timed_profiles_kept_separate(local_server, monkeypatch, tmp_path):
    import shore_agent.web as web
    monkeypatch.setattr(web, 'PROJECT', tmp_path)
    base = {'experiment_id': 'v15-local-original', 'status': 'completed', 'updated_at': 'now',
            'configuration': {'environment': {'wall_seconds': 3600},
                              'model': {'model': 'qwen3.8-27b', 'thinking': False, 'deployment': 'local'}},
            'worlds': [{'world_id': 'world_1', 'run_id': 'original-world_1', 'status': 'submitted'}]}
    old = tmp_path / 'experiments/v15-local-original/summary.json'
    old.parent.mkdir(parents=True); old.write_text(json.dumps(base))
    derived = copy.deepcopy(base)
    derived['worlds'][0]['exploration_seconds'] = 297
    archived = tmp_path / 'experiments/E3/R01/summary.json'
    archived.parent.mkdir(parents=True); archived.write_text(json.dumps(derived))
    new = copy.deepcopy(base)
    new['experiment_id'] = 'new-e4'
    new['configuration']['environment'].update(ruleset='e4', noise=True, wall_seconds=300)
    new['worlds'][0]['run_id'] = 'e4-world_1'
    e4 = tmp_path / 'experiments/E4/R01/summary.json'
    e4.parent.mkdir(parents=True); e4.write_text(json.dumps(new))
    clean = copy.deepcopy(new)
    clean['experiment_id'] = 'new-e5'
    clean['configuration']['environment'].update(ruleset='e5', noise=False)
    clean['worlds'][0]['run_id'] = 'e5-world_1'
    e5 = tmp_path / 'experiments/E5/R01/summary.json'
    e5.parent.mkdir(parents=True); e5.write_text(json.dumps(clean))
    server, _ = local_server
    status, _, body = request(server, path='/api/baselines')
    assert status == 200
    batches = {b['experiment_group']: b for b in json.loads(body)['batches']}
    assert set(batches) == {'E3', 'E4', 'E5'}
    assert batches['E3']['worlds'][0]['exploration_seconds'] == 297
    assert batches['E3']['worlds'][0]['run_id'] == 'original-world_1'
    assert batches['E4']['energy_budget'] == 10 and batches['E4']['wall_seconds'] == 300
    assert batches['E5']['energy_budget'] == 10 and batches['E5']['noise'] is False
    assert batches['E5']['worlds'][0]['run_id'] == 'e5-world_1'
    assert old.read_text() == json.dumps(base)


def test_bootstrap_listing_and_start(local_server, monkeypatch):
    server, manager = local_server
    secret = 'synthetic-test-secret-never-a-real-key'
    monkeypatch.setenv('DEEPSEEK_API_KEY', secret)
    status, headers, body = request(server)
    data = json.loads(body)
    assert status == 200
    assert data['token'] == server.session_token
    assert data['api_key_configured'] is True
    assert data['runs'] == manager.list_runs()['runs']
    assert data['deleted_runs'] == manager.list_runs()['deleted_runs']
    assert data['active_run_id'] is None
    assert data['defaults']['max_calls'] is None
    assert data['defaults']['max_total_tokens'] == 5000000
    assert data['defaults']['max_tokens_per_call'] == 65536
    assert data['defaults']['model']
    assert data['defaults']['reasoning_effort'] == 'low'
    assert data['models'] == manager.client_configuration()['models']
    assert data['api_key_required'] is True
    assert data['defaults']['world_id'] == DEFAULT_WORLD_ID
    assert data['worlds'] == public_worlds()
    assert all(set(world) == {'id', 'name'} for world in data['worlds'])
    assert [world['name'] for world in data['worlds']] == [f'世界 {i:02d}' for i in range(1, 8)]
    assert secret.encode() not in body
    assert headers['Cache-Control'] == 'no-store'
    assert json.loads(request(server, path='/api/runs')[2]) == manager.list_runs()
    config = {'api_key': secret, 'seed': 42, 'noise': False}
    status, _, body = request(server, 'POST', '/api/runs', config)
    assert status == 202
    assert json.loads(body) == {'run_id': 'new-run'}
    assert manager.started == [config]
    assert secret.encode() not in body


def test_bootstrap_uses_server_selected_local_configuration(local_server):
    server, manager = local_server
    manager.client_settings = {'models': [{'id': 'local-flash', 'name': 'local-flash'}],
                               'api_key_configured': False, 'api_key_required': False,
                               'defaults': {'model': 'local-flash', 'reasoning_effort': 'max',
                                            'max_total_tokens': 7000000, 'seed': 81, 'world_id': 'world_4'}}
    status, _, body = request(server)
    data = json.loads(body)
    assert status == 200
    for key, value in manager.client_settings.items():
        assert data[key] == value


def test_server_factory_reads_explicit_config_without_starting_a_model(tmp_path, monkeypatch):
    from shore_agent import web
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'config.example.json').write_bytes((web.PROJECT / 'config.example.json').read_bytes())
    config_path = tmp_path / 'local.json'
    config_path.write_text(json.dumps({'model': {'model': 'my-local-flash', 'reasoning_effort': 'high'}}))
    monkeypatch.setattr(web, 'PROJECT', project)
    monkeypatch.setattr(web, 'WebServer', lambda *_args: SimpleNamespace())
    server = make_server(config_path=config_path)
    try:
        assert server.manager.config_path == config_path.resolve()
        public = server.manager.client_configuration()
        assert public['models'] == [{'id': 'my-local-flash', 'name': 'my-local-flash'}]
        assert public['defaults']['reasoning_effort'] == 'high'
        assert not list(server.manager.runs_dir.iterdir())
    finally:
        server.manager.close()


@pytest.mark.parametrize('effort', ['low', 'high', 'max'])
def test_http_forwards_reasoning_choice(local_server, effort):
    server, manager = local_server
    status, _, body = request(server, 'POST', '/api/runs', {'reasoning_effort': effort})
    assert status == 202
    assert json.loads(body) == {'run_id': 'new-run'}
    assert manager.started == [{'reasoning_effort': effort}]


@pytest.mark.parametrize('world_id', WORLD_IDS)
def test_http_forwards_selected_world_without_starting_a_real_worker(local_server, world_id):
    server, manager = local_server
    status, _, body = request(server, 'POST', '/api/runs', {'world_id': world_id})
    assert status == 202
    assert json.loads(body) == {'run_id': 'new-run'}
    assert manager.started == [{'world_id': world_id}]


def test_world_validation_error_remains_a_safe_http_code(local_server):
    from shore_agent.web_jobs import ValidationError
    server, manager = local_server
    manager.start_error = ValidationError('invalid_world_id')
    assert_error(request(server, 'POST', '/api/runs', {'world_id': 'world_8'}), 400, 'invalid_world_id')
    assert manager.started == []


def test_snapshot_stop_and_export(local_server):
    server, manager = local_server
    status, headers, body = request(server, path='/api/runs/demo-1/export')
    assert status == 200
    assert json.loads(body) == manager.snapshot('demo-1')
    assert headers['Content-Disposition'] == 'attachment; filename="demo-1.json"'
    assert headers['Content-Type'] == 'application/json; charset=utf-8'
    assert headers['Cache-Control'] == 'no-store'
    assert headers['X-Content-Type-Options'] == 'nosniff'
    assert headers['X-Frame-Options'] == 'DENY'
    assert headers['Referrer-Policy'] == 'no-referrer'
    assert "frame-ancestors 'none'" in headers['Content-Security-Policy']
    assert len(body) == int(headers['Content-Length'])
    assert request(server, path='/api/runs/demo-1')[2] == body
    status, _, body = request(server, 'POST', '/api/runs/demo-1/stop')
    assert status == 200 and json.loads(body) == {'ok': True}
    assert manager.stopped == ['demo-1']
    assert_error(request(server, 'POST', '/api/runs/demo-1/stop', {'extra': True}),
                 400, 'stop_takes_no_arguments')


@pytest.mark.parametrize('token', ['', 'wrong-token', '\u00e9'])
def test_missing_or_invalid_session_token(local_server, token):
    server, manager = local_server
    assert_error(request(server, 'POST', '/api/runs', headers={'X-Session-Token': token}),
                 403, 'invalid_session_token')
    assert manager.started == []


@pytest.mark.parametrize('host', ['attacker.example:8765', '127.0.0.1', 'localhost:1', '127.0.0.1.evil:8765'])
def test_host_is_exact_loopback_and_port(local_server, host):
    server, manager = local_server
    assert_error(request(server, headers={'Host': host}), 403, 'invalid_host')
    assert_error(request(server, 'POST', '/api/runs', headers={'Host': host}), 403, 'invalid_host')
    assert manager.started == []


def test_localhost_origin_must_match_host(local_server):
    server, manager = local_server
    host = f'localhost:{server.server_port}'
    assert request(server, headers={'Host': host, 'Origin': f'http://{host}'})[0] == 200
    for origin in ('null', 'https://' + host, 'http://evil.example', f'http://127.0.0.1:{server.server_port}'):
        assert_error(request(server, 'POST', '/api/runs', headers={'Host': host, 'Origin': origin}),
                     403, 'invalid_origin')
    assert manager.started == []


@pytest.mark.parametrize('method', ['GET', 'POST'])
def test_fetch_metadata_rejects_cross_site(local_server, method):
    server, _ = local_server
    assert_error(request(server, method, '/api/runs', headers={'Sec-Fetch-Site': 'cross-site'}),
                 403, 'cross_site_request')


@pytest.mark.parametrize('payload,code', [(b'{broken', 'invalid_json'), (b'\xff', 'invalid_json'),
                                         (b'[]', 'json_object_required'), (b'null', 'json_object_required'),
                                         (b'{"seed":NaN}', 'invalid_json')])
def test_bad_json_has_structured_errors(local_server, payload, code):
    server, manager = local_server
    assert_error(request(server, 'POST', '/api/runs', body=payload), 400, code)
    assert manager.started == []


def test_deep_json_array_is_rejected_across_python_versions(local_server):
    server, manager = local_server
    status, headers, body = request(server, 'POST', '/api/runs', body=b'[' * 2000 + b']' * 2000)
    assert status == 400
    # Parser recursion limits differ between CPython builds. If parsing succeeds,
    # the object-only boundary still rejects this array without starting a job.
    assert json.loads(body)['error'] in {'invalid_json', 'json_object_required'}
    assert headers['Content-Type'].startswith('application/json')
    assert manager.started == []


def test_json_content_type_and_payload_limit(local_server):
    server, manager = local_server
    assert_error(request(server, 'POST', '/api/runs', headers={'Content-Type': 'text/plain'}),
                 415, 'json_required')
    assert_error(request(server, 'POST', '/api/runs', body=b' ' * (MAX_BODY + 1)),
                 413, 'request_too_large')
    assert manager.started == []


@pytest.mark.parametrize('lengths,extra', [([], []), (['-1'], []), (['abc'], []),
                                         (['2', '2'], []), (['2'], [('Transfer-Encoding', 'chunked')])])
def test_ambiguous_content_length_rejected(local_server, lengths, extra):
    server, manager = local_server
    connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
    try:
        connection.putrequest('POST', '/api/runs')
        connection.putheader('Content-Type', 'application/json')
        connection.putheader('X-Session-Token', server.session_token)
        for length in lengths:
            connection.putheader('Content-Length', length)
        for name, value in extra:
            connection.putheader(name, value)
        connection.endheaders()
        response = connection.getresponse()
        assert response.status == 400
        assert json.loads(response.read()) == {'error': 'invalid_content_length'}
    finally:
        connection.close()
    assert manager.started == []


@pytest.mark.parametrize('path', ['/../README.md', '/%2e%2e/README.md', '/web/../config.example.json',
                                  '/api/runs/../../config.json', '/api/runs/demo-1%2fexport',
                                  '/shore_agent/model.py', '/runs/demo-1/messages.json',
                                  '/api/runs/demo-1/unexpected', 'http://evil.example/api/bootstrap', 'http://['])
def test_traversal_and_nonallowlisted_files_are_not_served(local_server, path):
    server, _ = local_server
    assert_error(request(server, path=path, headers={'Host': f'127.0.0.1:{server.server_port}'}),
                 404, 'not_found')


def test_missing_run_and_unknown_route(local_server):
    server, _ = local_server
    assert_error(request(server, path='/api/runs/missing'), 404, 'run_not_found')
    assert_error(request(server, 'POST', '/api/runs/missing/stop'), 404, 'run_not_found')
    assert_error(request(server, 'POST', '/unknown'), 404, 'not_found')
    assert_error(request(server, 'OPTIONS', '/api/runs'), 403, 'cross_origin_access_disabled')


@pytest.mark.parametrize('error,status,code', [(ValueError('synthetic-secret-value'), 400, 'invalid_run_configuration'),
                                             (RuntimeError('synthetic-secret-value'), 409, 'run_already_active'),
                                             (Exception('synthetic-secret-value'), 500, 'server_error')])
def test_start_exception_messages_are_not_exposed(local_server, error, status, code):
    server, manager = local_server
    manager.start_error = error
    result = request(server, 'POST', '/api/runs', {'api_key': 'synthetic-secret-value'})
    assert_error(result, status, code)
    assert b'synthetic-secret-value' not in result[2]


def test_snapshot_exception_messages_are_not_exposed(local_server):
    server, manager = local_server
    manager.snapshot_error = Exception('synthetic-secret-value /private/config/key')
    assert_error(request(server, path='/api/runs/demo-1'), 500, 'server_error')


def test_delete_and_restore_history_without_running_models(local_server):
    server, manager = local_server
    status, _, body = request(server, 'POST', '/api/runs/demo-1/delete')
    assert status == 200
    assert json.loads(body) == {'deleted_run_id': 'demo-1'}
    status, _, body = request(server, 'POST', '/api/runs/deleted-1/restore')
    assert status == 200
    assert json.loads(body) == {'restored_run_id': 'deleted-1'}
    assert manager.deleted == ['demo-1']
    assert manager.restored == ['deleted-1']
    assert manager.started == []
    assert manager.stopped == []


@pytest.mark.parametrize('action', ['delete', 'restore'])
def test_history_mutations_reject_arguments_and_missing_runs(local_server, action):
    server, manager = local_server
    assert_error(request(server, 'POST', f'/api/runs/demo-1/{action}', {'force': True}),
                 400, f'{action}_takes_no_arguments')
    assert_error(request(server, 'POST', f'/api/runs/missing/{action}'), 404, 'run_not_found')
    assert manager.deleted == manager.restored == manager.started == manager.stopped == []


@pytest.mark.parametrize('action', ['delete', 'restore'])
@pytest.mark.parametrize('headers,code', [({'X-Session-Token': ''}, 'invalid_session_token'),
                                         ({'Host': 'evil.example'}, 'invalid_host'),
                                         ({'Origin': 'https://evil.example'}, 'invalid_origin'),
                                         ({'Sec-Fetch-Site': 'cross-site'}, 'cross_site_request')])
def test_history_mutations_require_same_request_protections(local_server, action, headers, code):
    server, manager = local_server
    assert_error(request(server, 'POST', f'/api/runs/demo-1/{action}', headers=headers), 403, code)
    assert manager.deleted == manager.restored == manager.started == manager.stopped == []


@pytest.mark.parametrize('action,code', [('delete', 'run_is_active'), ('restore', 'run_already_exists')])
def test_history_conflicts_expose_only_safe_codes(local_server, action, code):
    server, manager = local_server
    error = RuntimeError('synthetic-secret-value /private/account')
    error.code = code
    manager.history_error = error
    result = request(server, 'POST', f'/api/runs/demo-1/{action}')
    assert_error(result, 409, code)
    assert b'synthetic-secret-value' not in result[2]
    assert manager.deleted == manager.restored == manager.started == manager.stopped == []


@pytest.mark.parametrize('action', ['delete', 'restore'])
def test_history_errors_never_echo_exception_text_or_unsafe_codes(local_server, action):
    server, manager = local_server
    conflict = RuntimeError('synthetic-secret-value')
    conflict.code = 'synthetic-secret-value /private/account'
    manager.history_error = conflict
    result = request(server, 'POST', f'/api/runs/demo-1/{action}')
    assert_error(result, 409, 'run_already_active')
    manager.history_error = Exception('synthetic-secret-value /private/account')
    assert_error(request(server, 'POST', f'/api/runs/demo-1/{action}'), 500, 'server_error')
    assert manager.deleted == manager.restored == manager.started == manager.stopped == []


@pytest.mark.parametrize('host', ['0.0.0.0', '::', '192.168.1.20', 'attacker.example'])
def test_server_cannot_bind_public_interfaces(host):
    with pytest.raises(ValueError, match='loopback'):
        make_server(host=host, manager=FakeManager())
