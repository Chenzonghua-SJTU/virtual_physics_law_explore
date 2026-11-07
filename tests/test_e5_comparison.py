"""Synthetic archive evidence for off/on comparison; no physics or model calls."""
import copy
import json
from pathlib import Path

import pytest

from deployment.compare_e5_ab import (CLEAN_REFERENCE, E3_PROMPT_SHA256, WORLDS,
                                      compare, main, report, sha)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def mutate(path, fn):
    value = json.loads(path.read_text())
    fn(value)
    write(path, value)


def jsonl(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row)+'\n' for row in value))


def fixture(root, name, enabled, scores=None):
    batch = root / name
    scores = scores or ([95, 95, 95, 95, 95, 80] if enabled else [95, 95, 95, 80, 80, 80])
    config = {'environment': {'ruleset': 'e5', 'energy_budget': 10, 'wall_seconds': 300, 'noise': False},
              'model': {'thinking': False, 'max_tokens_per_call': 4096, 'sampling_seed': 42},
              'agent': {'guidance_profile': 'e3'}, 'numerics': {'diagnostics_enabled': enabled, 'max_nfev': 80}}
    manifest = {'experiment_id': name, 'experiment_group': 'E5', 'ruleset': 'e5', 'status': 'completed',
                'created_at': '2026-11-07T00:00:00+00:00', 'finished_at': '2026-11-07T00:08:00+00:00',
                'configuration': config, 'workers': 2,
                'protocol': {'attempts_per_world': 1, 'diagnostics_enabled': enabled},
                'model_endpoints': ['http://127.0.0.1:8002/v1'] if enabled else ['http://127.0.0.1:8000/v1'],
                'source_sha256': {'shore_agent/prompts/main.txt': E3_PROMPT_SHA256, 'source.py': 'same'},
                'runs': {w: name+'-'+w for w in WORLDS}}
    write(batch/'manifest.json', manifest)
    summary = copy.deepcopy(manifest)
    summary['worlds'] = []
    audited = {'experiment_id': name, 'experiment_group': 'E5', 'ruleset': 'e5', 'all_finished': True,
               'manifest_sha256': sha(batch/'manifest.json'), 'errors': [], 'worlds': []}
    for world, score in zip(WORLDS, scores):
        run_id = manifest['runs'][world]
        summary['worlds'].append({'world_id': world, 'run_id': run_id, 'status': 'submitted', 'running': False,
            'evaluation_complete': True, 'evaluation_score': {'total': score}, 'calls': 2,
            'energy_used': 8, 'exploration_seconds': 100., 'evaluation_seconds': 2.,
            'wall_seconds_including_evaluation': 103.})
        tool_rows = [{'tool': 'diagnose_dynamics', 'ok': True}] if enabled else []
        model = {'calls': 2, 'usage_complete': True, 'completion_tokens_reported': 600,
                 'per_call': [{'call_number': i, 'sampling_seed': 42, 'requested_max_tokens': 4096,
                               'usage_complete': True, 'usage': {'completion_tokens': tokens}}
                              for i, tokens in ((1, 100), (2, 500))]}
        audited['worlds'].append({'world_id': world, 'run_id': run_id, 'status': 'submitted',
            'diagnostics_enabled': enabled, 'energy_used': 8, 'model': model,
            'submission': {'timely_pair': True}, 'evaluation': {'score': score, 'complete': True, 'failures_count': 0,
                'checks': {'all_fixed_cases': True, 'no_noise_truth_reference': True, 'all_cases_completed': True}},
            'timing': {'exploration_seconds': 100., 'evaluation_seconds': 2., 'total_seconds_including_evaluation': 103.},
            'tools': {'per_call': tool_rows, 'unfinished_tool_calls': []}})
        directory = root/'runs'/run_id
        jsonl(directory/'model_events.jsonl', [{'event': event, 'call_number': i, 'seed': 42, 'max_tokens': 4096}
            for i in (1, 2) for event in ('request_started', 'request')])
        jsonl(directory/'tools.jsonl', [{'tool': 'diagnose_dynamics', 'result': {'ok': True}}] if enabled else [])
        jsonl(directory/'events.jsonl', [{'event': 'tool_started', 'name': 'diagnose_dynamics', 'tool_call_id': 'd1'},
                                        {'event': 'tool_finished', 'tool_call_id': 'd1'}] if enabled else [])
        write(directory/'evaluation.json', {'truth_reference': CLEAN_REFERENCE, 'complete': True,
                                          'score': {'total': score}})
    write(batch/'summary.json', summary)
    write(batch/'audit.json', audited)
    return batch


def refresh_manifest_digest(batch):
    mutate(batch/'audit.json', lambda d: d.update(manifest_sha256=sha(batch/'manifest.json')))


def pair(root):
    return fixture(root, 'off', False), fixture(root, 'on', True)


def test_comparison_is_read_only_and_reports_fixed_single_batch_evidence(tmp_path):
    off, on = pair(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    result = compare(off, on, tmp_path/'runs')
    assert result['errors'] == [] and result['comparison_verified']
    assert result['observed_primary_winner'] == 'on' and result['on_minus_off_success_count'] == 2
    a, b = result['arms']['off']['aggregate'], result['arms']['on']['aggregate']
    assert a['worlds_at_or_above_90'] == 3 and b['worlds_at_or_above_90'] == 5
    assert a['batch_wall_seconds'] == b['batch_wall_seconds'] == 480
    assert a['mean_total_seconds_per_experiment'] == 103
    assert a['average_output_tokens_per_call'] == 300
    assert a['diagnostic_tool']['calls'] == 0 and b['diagnostic_tool']['successful'] == 6
    assert a['five_world_target_met'] is False and b['five_world_target_met'] is True
    assert '稳定因果' in report(result) and '未知分数补成 0' in report(result)
    assert {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()} == before


def test_each_world_is_listed_without_merging_best_runs(tmp_path):
    off = fixture(tmp_path, 'off', False, [91, 91, 91, 10, 10, 10])
    on = fixture(tmp_path, 'on', True, [10, 10, 10, 91, 91, 89.999999])
    result = compare(off, on)
    assert result['observed_primary_winner'] == 'off'
    assert result['arms']['off']['aggregate']['worlds_at_or_above_90'] == 3
    assert result['arms']['on']['aggregate']['worlds_at_or_above_90'] == 2
    assert result['arms']['on']['worlds'][-1]['at_or_above_90'] is False


@pytest.mark.parametrize('field,value', [('max_nfev', 100), ('extra', True)])
def test_other_configuration_differences_invalidate_comparison(tmp_path, field, value):
    off, on = pair(tmp_path)
    for name in ('manifest.json', 'summary.json'):
        mutate(on/name, lambda d: d['configuration']['numerics'].update({field: value}))
    refresh_manifest_digest(on)
    result = compare(off, on)
    assert 'numerics.'+field in result['configuration_differences_other_than_toggle']
    assert not result['comparison_verified'] and result['observed_primary_winner'] is None


def test_source_mismatch_and_stale_audit_digest_are_detected(tmp_path):
    off, on = pair(tmp_path)
    for name in ('manifest.json', 'summary.json'):
        mutate(on/name, lambda d: d['source_sha256'].update({'source.py': 'different'}))
    result = compare(off, on)
    assert 'comparison:same_frozen_source_hashes' in result['errors']
    assert 'on:audit_manifest_digest_mismatch' in result['errors']


def test_duplicate_or_cross_arm_run_ids_are_rejected(tmp_path):
    off, on = pair(tmp_path)
    mutate(on/'manifest.json', lambda d: d['runs'].update(world_2=d['runs']['world_1']))
    refresh_manifest_digest(on)
    result = compare(off, on)
    assert 'on:requires_six_distinct_world_runs' in result['errors']
    assert not result['comparison_verified']
    off2 = fixture(tmp_path, 'off2', False)
    on2 = fixture(tmp_path, 'on2', True)
    shared = 'off2-world_1'
    mutate(on2/'manifest.json', lambda d: d['runs'].update(world_1=shared))
    for name in ('summary.json', 'audit.json'):
        mutate(on2/name, lambda d: d['worlds'][0].update(run_id=shared))
    refresh_manifest_digest(on2)
    assert 'comparison:disjoint_six_world_attempts' in compare(off2, on2)['errors']


def test_missing_usage_stays_unknown_without_zero_or_false_full_max(tmp_path):
    off, on = pair(tmp_path)
    def missing(d):
        model = d['worlds'][0]['model']
        model.update(usage_complete=False, completion_tokens_reported=100)
        model['per_call'][1].update(usage=None, usage_complete=False)
    mutate(on/'audit.json', missing)
    result = compare(off, on)
    row = result['arms']['on']['worlds'][0]
    assert row['average_output_tokens_per_call'] is None and row['max_call_output_tokens'] is None
    assert row['max_call_output_tokens_reported'] == 100 and row['completion_tokens_reported'] == 100
    assert row['output_cap_compliant'] is None
    assert result['arms']['on']['aggregate']['average_output_tokens_per_call'] is None
    assert result['arms']['on']['aggregate']['five_world_target_met'] is False


def test_unfinished_or_incomplete_world_does_not_count_even_with_stale_score(tmp_path):
    off, on = pair(tmp_path)
    mutate(on/'summary.json', lambda d: d['worlds'][0].update(status='incomplete', evaluation_complete=False))
    mutate(on/'audit.json', lambda d: d['worlds'][0]['evaluation'].update(complete=False))
    result = compare(off, on)
    assert result['arms']['on']['worlds'][0]['at_or_above_90'] is False
    assert result['arms']['on']['aggregate']['worlds_at_or_above_90'] == 4


def test_five_high_scores_with_one_incomplete_does_not_claim_full_audited_target(tmp_path):
    off = fixture(tmp_path, 'off', False)
    on = fixture(tmp_path, 'on', True, [95]*6)
    mutate(on/'summary.json', lambda d: d['worlds'][5].update(status='incomplete', evaluation_complete=False))
    mutate(on/'audit.json', lambda d: d['worlds'][5]['evaluation'].update(complete=False))
    mutate(on/'audit.json', lambda d: d['worlds'][5]['submission'].update(timely_pair=False))
    aggregate = compare(off, on)['arms']['on']['aggregate']
    assert aggregate['worlds_at_or_above_90'] == 5
    assert aggregate['five_world_target_met'] is False


def test_per_call_seed_and_noise_evidence_are_required(tmp_path):
    off, on = pair(tmp_path)
    mutate(on/'audit.json', lambda d: d['worlds'][0]['model']['per_call'][1].update(sampling_seed=None))
    mutate(on/'audit.json', lambda d: d['worlds'][1]['evaluation']['checks'].update(no_noise_truth_reference=False))
    result = compare(off, on)
    assert 'on:world_1:per_call_seed_not_verified_42' in result['errors']
    assert 'on:world_2:evaluation_not_verified_noise_free' in result['errors']
    assert not result['comparison_verified']


def test_raw_tool_calls_override_claim_of_unused_tool_and_seed_checks(tmp_path):
    off, on = pair(tmp_path)
    jsonl(tmp_path/'runs'/'on-world_1'/'tools.jsonl', [])
    jsonl(tmp_path/'runs'/'on-world_2'/'model_events.jsonl', [{'event': 'request', 'call_number': 1, 'seed': 7, 'max_tokens': 4096}])
    result = compare(off, on, tmp_path/'runs')
    assert 'on:world_1:raw_diagnostic_call_count_mismatch' in result['errors']
    assert 'on:world_2:raw_request_seed_not_verified_42' in result['errors']


def test_cli_writes_only_fresh_output_and_refuses_overwriting_inputs(tmp_path, monkeypatch):
    off, on = pair(tmp_path)
    output = tmp_path/'comparison'
    monkeypatch.setattr('sys.argv', ['compare_e5_ab.py', '--off', str(off), '--on', str(on), '--output', str(output)])
    assert main() == 0
    assert sorted(p.name for p in output.iterdir()) == ['comparison.json', 'report.md']
    before = (output/'comparison.json').read_bytes()
    with pytest.raises(SystemExit):
        main()
    assert (output/'comparison.json').read_bytes() == before
