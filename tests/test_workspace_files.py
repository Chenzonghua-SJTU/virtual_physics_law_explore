import base64
import hashlib
import json

import pytest

from code_sandbox.runner import file_readers
from shore_agent.store import Store
from shore_agent.workspace import SessionFiles
from shore_agent.environment import Environment
from shore_agent.runtime import ToolRuntime
from shore_agent.code_execution import execute_code
from test_code_execution import docker_config


@pytest.fixture
def workspace(tmp_path):
    store = Store(tmp_path / 'records')
    store.add('probe', {'probe_id': 'probe_0001', 'text': '中文观测' * 100, 'times': [0, 1]}, 'probe_0001')
    # Private files and even unregistered record files must not enter the workspace.
    for name in ('evaluation.json', 'messages.json', 'config.json', 'law.py'):
        (tmp_path / name).write_text('private')
    (tmp_path / 'records/probe/probe_unregistered.json').write_text('unregistered')
    return SessionFiles(store, tmp_path)


def test_listing_pagination_and_full_unicode_roundtrip(workspace):
    assert workspace.list_files()['entries'] == [{'path': 'observations/', 'type': 'directory'}]
    assert workspace.list_files('observations/')['entries'][0]['path'] == 'observations/probe_0001.json'
    path = 'observations/probe_0001.json'
    text, offset = '', 0
    while True:
        part = workspace.read_file(path, offset, 17)
        text += part['content']
        offset = part['next_offset']
        if offset is None:
            break
    assert text.encode() == workspace.read_bytes(path)
    assert json.loads(text)['text'] == '中文观测' * 100
    assert part['sha256'] == hashlib.sha256(text.encode()).hexdigest()


@pytest.mark.parametrize('path', ['../evaluation.json', '/etc/passwd', '/', 'observations/../../messages.json',
    'observations\\probe_0001.json', 'runs/other/records/probe/probe_0001.json',
    'evaluation.json', 'config.json', 'messages.json', 'law.py', 'observations/probe_unregistered.json'])
def test_only_registered_current_session_files_are_readable(workspace, path):
    with pytest.raises(ValueError):
        workspace.read_bytes(path)


def test_identical_ids_in_another_session_are_not_visible(workspace, tmp_path):
    other = Store(tmp_path / 'other/records')
    other.add('probe', {'probe_id': 'probe_0001', 'secret_other_session': True}, 'probe_0001')
    assert 'secret_other_session' not in workspace.read_file('observations/probe_0001.json')['content']


def test_artifact_allowlist_hash_and_symlink_protection(workspace, tmp_path):
    rid = 'code_test'; output = tmp_path / 'code_executions' / rid / 'artifacts'
    output.mkdir(parents=True)
    blob = b'\x89PNG\r\n\x1a\n'
    (output / 'plot.png').write_bytes(blob)
    (output / 'unlisted.txt').write_text('not exported')
    workspace.store.add('code_execution', {'execution_id':rid, 'code':'result=1', 'result':{'value':1},
        'artifacts':[{'name':'plot.png','sha256':hashlib.sha256(blob).hexdigest()}]}, rid)
    key = 'analyses/code_test/artifacts/plot.png'
    assert workspace.read_bytes(key) == blob
    with pytest.raises(ValueError, match='Binary'):
        workspace.read_file(key)
    with pytest.raises(ValueError):
        workspace.read_bytes('analyses/code_test/artifacts/unlisted.txt')
    (output / 'plot.png').write_bytes(b'changed')
    with pytest.raises(ValueError, match='integrity'):
        workspace.read_bytes(key)
    (output / 'plot.png').unlink()
    (output / 'plot.png').symlink_to(tmp_path / 'config.json')
    with pytest.raises(ValueError, match='symlink'):
        workspace.read_bytes(key)


def test_snapshot_readers_are_complete_and_cannot_mutate_source():
    content = json.dumps({'rows':list(range(1000))}).encode()
    readers = file_readers({'observations/p.json':base64.b64encode(content).decode()})
    a = readers['read_json']('observations/p.json'); a['rows'][0] = 999
    assert readers['read_json']('observations/p.json')['rows'][0] == 0
    assert readers['read_bytes']('observations/p.json') == content
    with pytest.raises(ValueError, match='not included'):
        readers['read_file']('observations/not_selected.json')
    with pytest.raises(ValueError):
        file_readers({'../outside':base64.b64encode(b'bad').decode()})


def test_runtime_file_snapshot_and_new_analysis_paths(tmp_path, monkeypatch):
    env = Environment({'physics_version':'v4','noise':False})
    try:
        rt = ToolRuntime(env, tmp_path, code_config={'enabled':True})
        mission = rt.mission()['data']
        path = 'observations/probe_0001.json'
        assert path in mission['workspace']['files']
        assert not hasattr(rt, 'call_back')
        def run(code, inputs, schema, artifact_dir, config, timeout, files=None):
            assert inputs == {} and list(files) == [path]
            p = file_readers(files)['read_json'](path)
            assert len(p['r_obs']) == 8
            return {'status':'success','result':{'count':8},'stdout':'','stderr':'','artifacts':[]}
        monkeypatch.setattr('shore_agent.code_execution.execute_code', run)
        out = rt.execute('run_code', {'code':'result = len(read_json(available_files[0])["times"])', 'files':[path]})
        assert out['ok'], out
        rid = out['data']['execution_id']
        assert f'analyses/{rid}/result.json' in out['data']['workspace_files']
        record = rt.store.get('code_execution', rid)
        assert record['files'][0]['sha256'] == rt.read_file(path)['sha256']
        assert json.loads(rt.read_file(f'analyses/{rid}/result.json')['content']) == {'count':8}
        assert not rt.execute('run_code', {'code':'result=1','files':['evaluation.json']})['ok']
        assert not rt.execute('run_code', {'code':'result=1','inputs':{}})['ok']
    finally:
        env.close()


def test_real_container_file_access_and_selected_file_boundary(tmp_path, docker_config):
    path = 'observations/probe_0001.json'
    probe = {'times':[0.,1.,2.], 'r_obs':[[0.,0.],[1.,2.],[2.,4.]],
             'v_obs':[[1.,2.]]*3, 'a_est_times':[1.], 'a_est':[[0.,0.]]}
    files = {path:base64.b64encode(json.dumps(probe).encode()).decode()}
    code = '''p = read_json("observations/probe_0001.json")
s = probe_arrays(p, time_axis="acceleration")
p["r_obs"][0][0] = 999
result = {"r":s["r"], "raw":read_json(available_files[0])["r_obs"][0], "paths":available_files}
with open("output/copied.txt", "w") as f: f.write(read_file(available_files[0]))
'''
    r = execute_code(code, {}, {}, tmp_path/'run', docker_config, 30, files=files)
    assert r['status'] == 'success', r
    assert r['result']['r'] == [[1.,2.]] and r['result']['raw'] == [0.,0.]
    assert (tmp_path/'run/copied.txt').exists()
    denied = execute_code('result = read_file("evaluation.json")', {}, {}, tmp_path/'denied', docker_config, 30, files=files)
    assert denied['status'] == 'error' and 'not included' in denied['error']['message']
