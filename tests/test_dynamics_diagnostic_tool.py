"""E5 tool access boundaries use synthetic observations, never simulator truth."""
import copy
import json
import sys
import time
from types import SimpleNamespace

import pytest

from shore_agent.runtime import ToolRuntime
from shore_agent.schemas import SCHEMAS, tool_schemas
from shore_agent.store import Store


class Environment:
    def __init__(self, ruleset='e5'):
        self.ruleset = ruleset
        self.requests = []
        self.remaining = 280.
        self.ended = False

    def request(self, method, **kwargs):
        self.requests.append(method)
        assert method == 'budget', 'A diagnostic must not request new observations or truth.'
        return {'ok': True, 'data': None, 'error': None,
                'budget': {'energy_remaining': 7, 'observations_remaining': 19,
                           'wall_seconds_remaining': self.remaining, 'session_ended': self.ended}}


def probe(pid):
    return {'probe_id': pid, 'times': [0., .1, .2],
            'initial_conditions': {'r0': [1., 2.], 'v0': [0., 0.], 't0': 0., 'properties': {'mass': 1.}},
            'r_obs': [[1., 2.], [1.01, 2.], [1.04, 2.]], 'v_obs': [[0., 0.], [.2, 0.], [.4, 0.]]}


def runtime(tmp_path, ruleset='e5', diagnostics_enabled=True):
    rt = ToolRuntime(Environment(ruleset), tmp_path, config={'diagnostics_enabled': diagnostics_enabled})
    rt.task = {'allowed_properties': ['mass'], 'property_controls': {'mass': {'default': 1.}},
               'position_noise_sigma': 0., 'velocity_noise_sigma': 0.}
    rt.store.add('probe', probe('selected'), 'selected')
    rt.store.add('probe', probe('unselected'), 'unselected')
    return rt


def stub_diagnose(monkeypatch, function):
    # Exercise the runtime boundary independently of numerical diagnostics tests.
    monkeypatch.setitem(sys.modules, 'shore_agent.diagnostics', SimpleNamespace(diagnose=function))


def test_only_e5_adds_diagnostic_schema_and_requires_explicit_ids():
    assert tool_schemas() == SCHEMAS and len(SCHEMAS) == 8
    e4 = tool_schemas(ruleset='e4')
    assert tool_schemas(ruleset='e5') == e4
    assert tool_schemas(ruleset='e5', diagnostics_enabled=False) == e4
    e5 = tool_schemas(ruleset='e5', diagnostics_enabled=True)
    assert [s['function']['name'] for s in e4] == [s['function']['name'] for s in SCHEMAS] + ['save_draft']
    assert e5[:-1] == e4 and e5[-1]['function']['name'] == 'diagnose_dynamics'
    parameters = e5[-1]['function']['parameters']
    assert parameters['required'] == ['probe_ids']
    assert set(parameters['properties']) == {'probe_ids'}
    assert parameters['additionalProperties'] is False
    assert 'default' not in parameters['properties']['probe_ids']
    assert tool_schemas(ruleset='e3', diagnostics_enabled=True) == SCHEMAS
    assert tool_schemas(ruleset='e4', diagnostics_enabled=True) == e4


def test_diagnostic_selects_only_acquired_data_and_saves_separate_public_record(tmp_path, monkeypatch):
    rt = runtime(tmp_path)
    original_probes, original_task = copy.deepcopy(rt.store.records['probe']), copy.deepcopy(rt.task)
    original_budget = rt.budget()
    original_draft = rt.last_valid_draft
    (tmp_path / 'evaluation.json').write_text('PRIVATE HIDDEN EVALUATION')
    (rt.store.directory / 'probe' / 'unregistered.json').write_text(json.dumps(probe('unregistered')))
    other = Store(tmp_path / 'other-session' / 'records')
    other.add('probe', {'probe_id': 'selected', 'secret': 'HISTORICAL ANSWER'}, 'selected')
    called = []

    def diagnose(probes, public_task):
        assert probes == [original_probes['selected']]
        assert public_task == original_task
        probes[0]['r_obs'][0][0] = 999
        public_task['allowed_properties'].append('private_mutation')
        called.append(True)
        time.sleep(.01)
        return {'status': 'descriptive', 'basis': list(range(8)), 'evidence': 'synthetic only'}

    stub_diagnose(monkeypatch, diagnose)
    reply = rt.execute('diagnose_dynamics', {'probe_ids': ['selected']})
    assert reply['ok'], reply
    assert called == [True]
    result = reply['data']
    rid = result['diagnostic_id']
    assert result['diagnostic_kind'] == 'integral_observation_regression'
    assert result['probe_ids'] == ['selected'] and 'law_id' not in result
    assert result['source'] == 'current_session_acquired_observations_only'
    assert 'not true dynamics' in result['meaning'] and 'development data' in result['meaning']
    assert result['workspace_files'] == [f'diagnostics/{rid}.json']
    assert result['diagnostics']['basis']['truncated'] is True
    saved = rt.store.get('diagnostic', rid)
    assert saved['diagnostics']['basis'] == list(range(8))
    assert json.loads(rt.read_file(f'diagnostics/{rid}.json')['content']) == saved
    assert json.loads((rt.store.directory / 'diagnostic' / f'{rid}.json').read_text()) == saved
    assert rt.list_files('diagnostics')['entries'] == [{'path': f'diagnostics/{rid}.json', 'type': 'file'}]
    assert rt.store.records['probe'] == original_probes and rt.task == original_task
    assert rt.last_valid_draft is original_draft and not rt.session_ended
    assert all(not rt.store.records[kind] for kind in ('law', 'residual', 'submission', 'validation'))
    assert rt.budget() == original_budget and set(rt.environment.requests) == {'budget'}
    logged = json.loads((tmp_path / 'tools.jsonl').read_text().splitlines()[0])
    assert logged['tool'] == 'diagnose_dynamics' and logged['elapsed_seconds'] >= .01
    assert 'PRIVATE HIDDEN' not in json.dumps(saved) and 'HISTORICAL ANSWER' not in json.dumps(saved)
    with pytest.raises(ValueError, match='No acquired law'):
        rt._law(rid)
    with pytest.raises(ValueError):
        rt.read_file('evaluation.json')


@pytest.mark.parametrize('ruleset', ['e3', 'e4'])
def test_prior_profiles_reject_diagnostic_even_when_called_directly(tmp_path, monkeypatch, ruleset):
    rt = runtime(tmp_path, ruleset)
    stub_diagnose(monkeypatch, lambda *a: pytest.fail('prior profile invoked diagnostics'))
    reply = rt.execute('diagnose_dynamics', {'probe_ids': ['selected']})
    assert not reply['ok'] and reply['error']['message'] == 'Unknown tool'
    with pytest.raises(ValueError, match='require E5'):
        rt.diagnose_dynamics(['selected'])
    assert not rt.store.records['diagnostic']


def test_e5_diagnostic_switch_defaults_off_and_cannot_be_bypassed(tmp_path, monkeypatch):
    default = ToolRuntime(Environment(), tmp_path / 'default')
    assert default.diagnostics_enabled is False
    assert 'diagnose_dynamics' not in [s['function']['name'] for s in default.schemas]
    rt = runtime(tmp_path / 'explicit-off', diagnostics_enabled=False)
    stub_diagnose(monkeypatch, lambda *a: pytest.fail('disabled diagnostic was called'))
    reply = rt.execute('diagnose_dynamics', {'probe_ids': ['selected']})
    assert not reply['ok'] and reply['error']['message'] == 'Unknown tool'
    with pytest.raises(ValueError, match='diagnostics_enabled=true'):
        rt.diagnose_dynamics(['selected'])
    assert not rt.store.records['diagnostic']


def test_compact_diagnostic_preserves_full_evidence_and_returns_summary(tmp_path, monkeypatch):
    rt = runtime(tmp_path)
    rt.diagnostics_compact = True
    full = {'synthetic': list(range(12)), 'meaning': 'descriptive evidence'}
    seen = []
    def summarize(value):
        seen.append(copy.deepcopy(value))
        return {'status': 'summary', 'source_count': len(value['synthetic'])}
    monkeypatch.setitem(sys.modules, 'shore_agent.diagnostics',
                        SimpleNamespace(diagnose=lambda *args: copy.deepcopy(full), summarize=summarize))
    reply = rt.execute('diagnose_dynamics', {'probe_ids': ['selected']})
    assert reply['ok']
    data = reply['data']
    assert 'diagnostics' not in data
    assert data['diagnostic_summary'] == {'status': 'summary', 'source_count': 12}
    assert seen == [full]
    assert rt.store.get('diagnostic', data['diagnostic_id'])['diagnostics'] == full
    assert data['workspace_files'] == [data['full_evidence']]
    read = rt.read_file(data['full_evidence'])
    assert json.loads(read['content'])['diagnostics'] == full
    assert not rt.store.records['law'] and not rt.session_ended


def test_compact_guidance_requires_e5_and_enabled_diagnostic():
    for ruleset in ('e3', 'e4'):
        assert tool_schemas(ruleset=ruleset, diagnostics_enabled=True, diagnostics_compact=True) == tool_schemas(ruleset=ruleset)
    assert tool_schemas(ruleset='e5', diagnostics_compact=True) == tool_schemas(ruleset='e5')
    schemas = tool_schemas(ruleset='e5', diagnostics_enabled=True, diagnostics_compact=True)
    by_name = {s['function']['name']: s['function'] for s in schemas}
    full = tool_schemas(ruleset='e5', diagnostics_enabled=True)
    assert [s['function']['parameters'] for s in schemas] == [s['function']['parameters'] for s in full]
    assert 'sqrt' in by_name['fit_law_and_rollout']['description']
    assert '交叉验证' in by_name['diagnose_dynamics']['description']


@pytest.mark.parametrize('flag', [None, 0, 1, 'true', [], {}])
def test_compact_option_requires_boolean(tmp_path, flag):
    with pytest.raises(ValueError, match='diagnostics_compact must be boolean'):
        ToolRuntime(Environment(), tmp_path, config={'diagnostics_compact': flag})


@pytest.mark.parametrize('flag', [None, 0, 1, 'true', 'false', [], {}])
def test_diagnostic_switch_requires_an_actual_boolean(tmp_path, flag):
    with pytest.raises(ValueError, match='numerics.diagnostics_enabled must be boolean'):
        ToolRuntime(Environment(), tmp_path, config={'diagnostics_enabled': flag})


@pytest.mark.parametrize('arguments', [{}, {'probe_ids': []}, {'probe_ids': ['selected', 'selected']},
    {'probe_ids': ['missing']}, {'probe_ids': ['unregistered']}, {'probe_ids': ['../other-session/selected']},
    {'probe_ids': ['selected'], 'world_id': 'world_1'}, {'probe_ids': ['selected'], 'law_id': 'law_1'}])
def test_invalid_or_unacquired_selection_never_runs_diagnostics(tmp_path, monkeypatch, arguments):
    rt = runtime(tmp_path)
    (rt.store.directory / 'probe' / 'unregistered.json').write_text(json.dumps(probe('unregistered')))
    stub_diagnose(monkeypatch, lambda *a: pytest.fail('invalid selection reached diagnostics'))
    reply = rt.execute('diagnose_dynamics', arguments)
    assert not reply['ok'] and reply['data'] is None
    assert not rt.store.records['diagnostic']


@pytest.mark.parametrize('ended', [False, True])
def test_diagnostic_cannot_start_after_session_or_time_limit(tmp_path, monkeypatch, ended):
    rt = runtime(tmp_path)
    rt.environment.ended = ended
    rt.environment.remaining = 280. if ended else 0.
    stub_diagnose(monkeypatch, lambda *a: pytest.fail('ended session reached diagnostics'))
    reply = rt.execute('diagnose_dynamics', {'probe_ids': ['selected']})
    assert not reply['ok'] and 'Session ended or wall time exhausted' in reply['error']['message']
    assert not rt.store.records['diagnostic']


def test_diagnostic_that_expires_during_computation_is_not_archived(tmp_path, monkeypatch):
    rt = runtime(tmp_path)

    def late_diagnostic(*args):
        rt.environment.remaining = 0.
        return {'status': 'descriptive'}

    stub_diagnose(monkeypatch, late_diagnostic)
    reply = rt.execute('diagnose_dynamics', {'probe_ids': ['selected']})
    assert not reply['ok'] and 'wall time exhausted' in reply['error']['message']
    assert not rt.store.records['diagnostic']


@pytest.mark.parametrize('bad_result', [{'value': float('nan')}, {'law_id': 'fake_law'}, ['not an object']])
def test_nonfinite_or_law_like_diagnostic_is_not_archived(tmp_path, monkeypatch, bad_result):
    rt = runtime(tmp_path)
    stub_diagnose(monkeypatch, lambda *a: bad_result)
    reply = rt.execute('diagnose_dynamics', {'probe_ids': ['selected']})
    assert not reply['ok']
    assert not rt.store.records['diagnostic'] and not rt.store.records['law']
    assert not (rt.store.directory / 'diagnostic').exists()


def test_real_observation_diagnostics_integrate_without_creating_a_law(tmp_path):
    rt = runtime(tmp_path)
    reply = rt.execute('diagnose_dynamics', {'probe_ids': ['selected']})
    assert reply['ok'], reply
    record = json.loads(rt.files.read_bytes(reply['data']['workspace_files'][0]))
    output = record['diagnostics']
    assert output['probe_ids'] == ['selected']
    assert output['method_version'] == 'observation_diagnostics_v1'
    assert 'space_regression' in output and 'radial_diagnostic' in output
    assert not rt.store.records['law'] and not rt.store.records['submission']
    assert 'law_id' not in record and 'law_id' not in output
    json.dumps(record, allow_nan=False)
