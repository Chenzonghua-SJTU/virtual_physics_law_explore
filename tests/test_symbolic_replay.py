"""Offline replay isolation: fixed acquired data, no hidden truth or new missions."""
import copy
import json

import numpy as np
import pytest

from deployment.replay_symbolic import replay


def setup_records(tmp_path):
    run = tmp_path / 'run'
    (run / 'records' / 'probe').mkdir(parents=True)
    (run / 'records' / 'symbolic_search').mkdir()
    for name, x0 in [('train', 0), ('heldout', 2)]:
        t = np.linspace(0, 1, 7)
        probe = {'probe_id': name, 'times': t.tolist(),
                 'r_obs': np.column_stack((x0+.5*t*t, np.zeros(len(t)))).tolist(),
                 'v_obs': np.column_stack((t, np.zeros(len(t)))).tolist(),
                 'initial_conditions': {'r0': [x0, 0], 'v0': [0, 0], 't0': 0, 'properties': {}}}
        (run / 'records' / 'probe' / (name + '.json')).write_text(json.dumps(probe))
    old = {'used_probe_ids': ['train'], 'candidates': [
        {'law_spec': {'ax': 'c1', 'ay': '0'}, 'parameter_spec': [{'name': 'c1', 'initial': 1}]}]}
    (run / 'records' / 'symbolic_search' / 'sr.json').write_text(json.dumps(old))
    # Must never be read by a replay, even though an actual run has such a file.
    (run / 'evaluation.json').write_text('THIS IS NOT JSON AND MUST NOT BE READ')
    return run, old


def test_replay_sends_only_original_search_probes_and_preserves_archives(tmp_path):
    run, old = setup_records(tmp_path)
    calls = []
    def search(probes, budget, **kwargs):
        calls.append((copy.deepcopy(probes), budget))
        return {'status': 'completed', 'candidates': old['candidates'],
                'axis_equations': {'ax': [{'source': '1.0', 'loss': 0}], 'ay': []}}
    output = tmp_path / 'diagnostic.json'
    result = replay(run, 'sr', output, heldout_probe_ids=['heldout'], budget=30,
                    search_function=search, fit_seconds=.5)
    assert [p['probe_id'] for p in calls[0][0]] == ['train']
    assert calls[0][1] == 30
    assert result['source_records_unchanged'] is True
    assert result['kind'] == 'offline_symbolic_replay_not_agent_result'
    candidate = result['new_candidate_diagnostics'][0]
    assert candidate['initial_heldout']['initial_domain_failures'] == []
    assert candidate['initial_heldout']['all_rollouts_completed'] is True
    assert candidate['initial_heldout']['trajectory_errors']['overall']['position_rmse'] < 1e-10
    assert candidate['refitted_heldout']['all_rollouts_completed'] is True
    assert json.loads(output.read_text())['new_search']['axis_equations']['ax'][0]['source'] == '1.0'


@pytest.mark.parametrize('case', ['overlap', 'overwrite', 'archive_output', 'traversal'])
def test_invalid_replay_cannot_call_service_or_overwrite_archive(tmp_path, case):
    run, old = setup_records(tmp_path)
    calls = []
    output = tmp_path / 'diagnostic.json'
    heldout, search_id = ['heldout'], 'sr'
    if case == 'overlap': heldout = ['train']
    if case == 'overwrite': output.write_text('existing')
    if case == 'archive_output': output = run / 'new-result.json'
    if case == 'traversal': search_id = '../sr'
    with pytest.raises(ValueError):
        replay(run, search_id, output, heldout_probe_ids=heldout,
               search_function=lambda *a, **k: calls.append(a))
    assert not calls
    if case == 'overwrite': assert output.read_text() == 'existing'
