import io
import json
import os
import sys

import pytest

from shore_agent import agent, environment, model, runtime, web_worker


@pytest.mark.parametrize('required,key', [(False, ''), (True, 'custom-test-key')])
def test_worker_supports_explicit_local_auth_and_cleans_key(tmp_path, monkeypatch, required, key):
    config = {'environment': {}, 'model': {'deployment': 'local', 'base_url': 'http://127.0.0.1:8000/v1',
              'api_key_env': 'E1_TEST_LOCAL_KEY', 'api_key_required': required}}
    (tmp_path / 'config.json').write_text(json.dumps(config))
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps({'api_key': key}) + '\n'))

    class FakeEnvironment:
        def __init__(self, config, *, secret_env_names):
            assert secret_env_names == ('E1_TEST_LOCAL_KEY',)

        def close(self):
            pass

    class FakeRuntime:
        def __init__(self, *a, **kw):
            pass

        def mission(self):
            return {'budget': {}}

    class FakeClient:
        def __init__(self, *a, **kw):
            assert os.environ.get('E1_TEST_LOCAL_KEY') == (key or None)

        def close(self):
            pass

    class FakeAgent:
        def __init__(self, *a, **kw):
            pass

        def run(self):
            return {'status': 'incomplete'}

    monkeypatch.setattr(environment, 'Environment', FakeEnvironment)
    monkeypatch.setattr(runtime, 'ToolRuntime', FakeRuntime)
    monkeypatch.setattr(model, 'DeepSeekClient', FakeClient)
    monkeypatch.setattr(agent, 'Agent', FakeAgent)
    assert web_worker.run(tmp_path) == 0
    assert 'E1_TEST_LOCAL_KEY' not in os.environ


def test_simulator_does_not_inherit_custom_model_key(monkeypatch):
    class Process:
        def __init__(self, *a, **kw):
            assert 'E1_TEST_LOCAL_KEY' not in kw['env']
            assert 'DEEPSEEK_API_KEY' not in kw['env']

    monkeypatch.setenv('E1_TEST_LOCAL_KEY', 'custom-test-key')
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'cloud-test-key')
    monkeypatch.setattr(environment.subprocess, 'Popen', Process)
    environment.Environment({}, secret_env_names=('E1_TEST_LOCAL_KEY',))
