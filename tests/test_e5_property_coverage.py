"""Coverage diagnostics use only synthetic acquired data, never world truth."""
import copy
import json

import pytest

from shore_agent.runtime import ToolRuntime


class Environment:
    def __init__(self, ruleset):
        self.ruleset = ruleset
        self.requests = []

    def request(self, method, **kwargs):
        self.requests.append(method)
        assert method == 'budget'  # Coverage must not launch or observe anything.
        return {'ok': True, 'data': None, 'error': None,
                'budget': {'wall_seconds_remaining': 290, 'energy_remaining': 8, 'session_ended': False}}


def probe(pid, properties, *, r0=(2., 0.), v0=(0., .1), t0=0., times=None):
    times = times or [t0, t0 + .1, t0 + .2]
    return {'probe_id': pid, 'initial_conditions': {'r0': list(r0), 'v0': list(v0),
            't0': t0, 'properties': properties}, 'times': times,
            'r_obs': [[r0[0] + v0[0] * (t - t0), r0[1] + v0[1] * (t - t0)] for t in times],
            'v_obs': [list(v0) for _ in times], 'a_est': [[0., 0.]],
            'a_est_times': [times[1]], 'a_est_method': 'synthetic'}


def runtime(tmp_path, ruleset='e5'):
    value = ToolRuntime(Environment(ruleset), tmp_path)
    value.task = {'allowed_properties': ['load', 'marker'],
                  'property_controls': {'load': {'default': 2}, 'marker': {'default': 7}},
                  'position_noise_sigma': 0}
    return value


def acquire(rt, *probes):
    for p in probes:
        rt.store.add('probe', p, p['probe_id'])


def fit(rt, ids):
    response = rt.execute('fit_law_and_rollout', {'law_spec': {'ax': '0', 'ay': '0'},
        'parameter_spec': [], 'train_probe_ids': ids})
    assert response['ok'], response
    return response['data']


def test_e5_reports_defaults_unvaried_controls_and_separate_training_validation(tmp_path):
    rt = runtime(tmp_path)
    base = probe('free', {})
    train = probe('train', {'load': 2, 'marker': 7}, r0=(3., 0.))
    acquire(rt, base, train)
    law = fit(rt, ['free', 'train'])
    saved_law = rt.store.get('law', law['law_id'])
    coverage = law['property_coverage']
    assert coverage['training']['property_values'] == {'load': [2], 'marker': [7]}
    assert coverage['training']['unvaried_controls'] == ['load', 'marker']
    assert coverage['all_acquired']['public_default_value_counts'] == {'load': 1, 'marker': 1}
    assert coverage['all_acquired']['single_control_pair_counts'] == {'load': 0, 'marker': 0}
    assert 'validation' not in coverage
    acquire(rt, probe('vary-load', {'load': 3, 'marker': 7}), probe('vary-marker', {'load': 2, 'marker': 8}))
    result = rt.execute('validate_law', {'law_id': law['law_id'], 'test_probe_ids': ['vary-load', 'vary-marker']})
    assert result['ok'], result
    validated = result['data']['property_coverage']
    assert validated['training'] == coverage['training']
    assert validated['validation']['probe_ids'] == ['vary-load', 'vary-marker']
    assert validated['validation']['single_control_pair_counts'] == {'load': 0, 'marker': 0}
    assert validated['all_acquired']['single_control_pair_counts'] == {'load': 1, 'marker': 1}
    assert validated['all_acquired']['unvaried_controls'] == []
    assert validated['all_acquired']['property_values'] == {'load': [2, 3], 'marker': [7, 8]}
    assert rt.store.get('law', law['law_id']) == saved_law  # No mutation of frozen training inputs.
    stored = rt.store.get('validation', result['data']['validation_id'])
    assert stored['property_coverage'] == validated
    assert set(rt.environment.requests) == {'budget'}
    assert 'do not establish a physical effect' in validated['interpretation']


@pytest.mark.parametrize('ruleset', ['e3', 'e4'])
def test_prior_profiles_do_not_receive_new_diagnostics(tmp_path, ruleset):
    rt = runtime(tmp_path, ruleset)
    acquire(rt, probe('train', {}), probe('test', {'load': 3, 'marker': 7}))
    law = fit(rt, ['train'])
    result = rt.execute('validate_law', {'law_id': law['law_id'], 'test_probe_ids': ['test']})
    assert result['ok']
    assert 'property_coverage' not in law and 'property_coverage' not in result['data']
    assert all('property_coverage' not in item for kind in ('law', 'validation')
               for item in rt.store.records[kind].values())


@pytest.mark.parametrize('change', [
    {'properties': {'load': 3, 'marker': 8}},
    {'properties': {'load': 3, 'marker': 7}, 'r0': (3., 0.)},
    {'properties': {'load': 3, 'marker': 7}, 'v0': (.1, 0.)},
    {'properties': {'load': 3, 'marker': 7}, 't0': 1.},
    {'properties': {'load': 3, 'marker': 7}, 'times': [0., .2, .4]},
])
def test_simultaneous_controls_or_different_initial_state_are_not_matched_pairs(tmp_path, change):
    rt = runtime(tmp_path)
    acquire(rt, probe('base', {}), probe('altered', **change))
    summary = rt._property_coverage(list(rt.store.records['probe'].values()))['all_acquired']
    assert summary['single_control_pair_counts'] == {'load': 0, 'marker': 0}
    assert 'load' not in summary['unvaried_controls']  # Variation alone is not controlled coverage.


def test_missing_properties_without_published_default_remain_unknown(tmp_path):
    rt = runtime(tmp_path)
    del rt.task['property_controls']['marker']['default']
    acquire(rt, probe('unknown', {}), probe('known', {'load': 3, 'marker': 7}))
    before = copy.deepcopy(rt.store.records)
    summary = rt._property_coverage(list(rt.store.records['probe'].values()))['all_acquired']
    assert summary['property_values'] == {'load': [2, 3], 'marker': [7]}
    assert summary['unknown_value_counts'] == {'load': 0, 'marker': 1}
    assert summary['public_default_value_counts'] == {'load': 1, 'marker': 0}
    assert summary['single_control_pair_counts'] == {'load': 0, 'marker': 0}
    assert rt.store.records == before
    json.dumps(summary, allow_nan=False)
