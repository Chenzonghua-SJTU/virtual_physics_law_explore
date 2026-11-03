import copy
import json
from pathlib import Path

import benchmark_reasoning as bench


def test_registered_design_is_balanced_and_varies_only_effort_within_world():
    jobs = bench.schedule()
    assert jobs == bench.schedule()
    assert len({job['run_id'] for job in jobs}) == 45
    base = json.loads((bench.PROJECT / 'config.example.json').read_text())
    unchanged = copy.deepcopy(base)
    for world in bench.WORLDS:
        configs = []
        for effort in bench.EFFORTS:
            cell = [j for j in jobs if j['world_id'] == world and j['effort'] == effort]
            assert {j['repeat'] for j in cell} == set(range(1, 6))
            for job in cell:
                config = bench.configuration(base, job)
                assert config['model']['max_total_tokens'] == 5000000
                assert config['model']['max_tokens_per_call'] == 393216
                assert config['model'].pop('reasoning_effort') == effort
                configs.append(config)
        assert all(config == configs[0] for config in configs)
    assert base == unchanged


def test_failed_attempt_is_retained_in_denominator_and_missing_score_not_zero():
    rows = [{**j, 'status': 'pending'} for j in bench.schedule()]
    low3 = [r for r in rows if r['effort'] == 'low' and r['world_id'] == 'world_3']
    for row in low3:
        row.update(returncode=0, elapsed_seconds=12, status='incomplete', reason='model_token_budget_exhausted')
    low3[0].update(status='submitted', reason='submission_accepted_locally', accepted_submission=True,
                   independent_evaluation_complete=True, high_precision=True, position_rmse=1e-8,
                   score={'total': 99})
    group = next(g for g in bench.aggregate(rows) if g['world_id'] == 'world_3' and g['effort'] == 'low')
    assert group['scheduled'] == group['finished'] == 5
    assert group['high_precision'] == group['submitted'] == group['evaluated'] == group['score_n'] == 1
    assert group['mean_score_scored_only'] == 99
    assert group['termination_reasons']['model_token_budget_exhausted'] == 4


def test_complete_driver_keeps_45_attempts_and_publishes_closed_runs_only(tmp_path, monkeypatch):
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'config.example.json').write_text((bench.PROJECT / 'config.example.json').read_text())
    monkeypatch.setattr(bench, 'source_hashes', lambda _project: {'main.txt': 'frozen'})
    monkeypatch.setattr(bench.subprocess, 'check_output', lambda *a, **k: 'test-commit\n')
    monkeypatch.setattr(bench.time, 'sleep', lambda _: None)
    calls = []
    secret = 'test-credential-memory-only'

    class Input:
        def write(self, value):
            assert json.loads(value) == {'api_key': secret}

        def close(self):
            pass

    class Process:
        def __init__(self, argv, **kwargs):
            directory = Path(argv[-1])
            assert directory.parent.name == '.E1-active'
            assert not (project / 'runs' / directory.name).exists()
            assert 'DEEPSEEK_API_KEY' not in kwargs['env']
            assert all(kwargs['env'][name] == '1' for name in bench.THREAD_VARS)
            calls.append(directory.name)
            self.pid = 1000 + len(calls)
            self.stdin = Input()
            (directory / 'result.json').write_text(json.dumps({'status': 'incomplete',
                'reason': 'http_status_503', 'model_usage': {'calls': 2, 'total_tokens': 0}}))

        def poll(self):
            return 0

    monkeypatch.setattr(bench.subprocess, 'Popen', Process)
    monkeypatch.setenv('DEEPSEEK_API_KEY', secret)
    output = tmp_path / 'reports'
    summary = bench.run(output, secret, project=project)
    assert summary['status'] == 'completed_all_attempts'
    assert len(calls) == len(set(calls)) == 45
    assert len(list((project / 'runs').iterdir())) == 45
    assert not (project / 'runs' / '.E1-active').exists()
    assert all(r['reason'] == 'http_status_503' for r in summary['rows'])
    assert all(secret not in path.read_text() for path in tmp_path.rglob('*.json'))
    manifest = json.loads((output / 'manifest.json').read_text())
    assert manifest['source_unchanged'] is True
    assert all(row['state'] == 'finished' for row in manifest['rows'])
