import hashlib
import json
from pathlib import Path

import pytest

from shore_agent.web_jobs import RunManager, ValidationError, _write

PROJECT = Path(__file__).resolve().parents[1]


def test_code_toggle_requires_ready_environment_and_does_not_accept_host_paths(tmp_path, monkeypatch):
    manager = RunManager(PROJECT, runs_dir=tmp_path)
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-key')
    monkeypatch.setattr('shore_agent.code_execution.sandbox_info', lambda *_: {'available': False})
    assert manager._config({'code_enabled': False})[0]['code_execution']['enabled'] is False
    with pytest.raises(ValidationError, match='code_sandbox_unavailable'):
        manager._config({'code_enabled': True})
    with pytest.raises(ValidationError):
        manager._config({'code_enabled': 'true'})
    with pytest.raises(ValidationError):
        manager._config({'code_enabled': True, 'image': 'untrusted'})
    monkeypatch.setattr('shore_agent.code_execution.sandbox_info', lambda *_: {'available': True})
    config, _ = manager._config({'code_enabled': True})
    assert config['code_execution']['enabled']
    assert manager.client_configuration()['code_sandbox']['available']
    manager.close()


def test_artifact_download_is_registered_unchanged_and_never_symlink(tmp_path):
    manager = RunManager(PROJECT, runs_dir=tmp_path)
    run = tmp_path / 'demo'
    folder = run / 'code_executions' / 'code_abcdef123456' / 'artifacts'
    folder.mkdir(parents=True)
    (run / 'records' / 'code_execution').mkdir(parents=True)
    content = b'legitimate data'
    file = folder / 'data.txt'
    file.write_bytes(content)
    record = {'artifacts': [{'name': 'data.txt', 'sha256': hashlib.sha256(content).hexdigest()}]}
    _write(run / 'records/code_execution/code_abcdef123456.json', record)
    assert manager.code_artifact('demo', 'code_abcdef123456', 'data.txt')[0] == content
    with pytest.raises(FileNotFoundError):
        manager.code_artifact('demo', 'code_abcdef123456', '../data.txt')
    file.write_bytes(b'changed')
    with pytest.raises(FileNotFoundError):
        manager.code_artifact('demo', 'code_abcdef123456', 'data.txt')
    file.unlink()
    outside = tmp_path / 'other.txt'
    outside.write_bytes(content)
    file.symlink_to(outside)
    with pytest.raises(FileNotFoundError):
        manager.code_artifact('demo', 'code_abcdef123456', 'data.txt')
    manager.close()
