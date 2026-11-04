import copy
import json
from pathlib import Path

import benchmark_code as bench


def test_e2_balanced_only_optional_code_differs():
    jobs = bench.schedule()
    assert jobs == bench.schedule()
    assert len(jobs) == len({j['run_id'] for j in jobs}) == 30
    base = json.loads((bench.PROJECT / 'config.example.json').read_text())
    original = copy.deepcopy(base)
    for world in bench.WORLDS:
        configurations = []
        for arm in bench.ARMS:
            cell = [j for j in jobs if j['arm'] == arm and j['world_id'] == world]
            assert {j['repeat'] for j in cell} == set(range(1, 6))
            for job in cell:
                config = bench.configuration(base, job)
                assert config['model']['reasoning_effort'] == 'high'
                assert config['model']['max_total_tokens'] == 5000000
                assert config['code_execution'].pop('enabled') is (arm == 'code')
                configurations.append(config)
        assert all(c == configurations[0] for c in configurations)
    assert base == original


def test_e2_failed_attempts_and_optional_nonuse_stay_in_denominator():
    rows = [{**j, 'status': 'pending'} for j in bench.schedule()]
    cell = [r for r in rows if r['arm'] == 'code' and r['world_id'] == 'world_3']
    for r in cell:
        r.update(returncode=0, status='incomplete', elapsed_seconds=12, reason='http_status_503')
    cell[0].update(accepted_submission=True, independent_evaluation_complete=True, high_precision=True,
                   position_rmse=1e-8, score={'total': 99}, code_execution_count=2, code_success_count=1)
    group = next(g for g in bench.aggregate(rows) if g['arm'] == 'code' and g['world_id'] == 'world_3')
    assert group['scheduled'] == group['finished'] == 5
    assert group['high_precision'] == group['evaluated'] == 1
    assert group['runs_using_code'] == 1
    assert group['code_calls'] == 2 and group['code_successes'] == 1
    assert group['mean_score_scored_only'] == 99


def test_e2_no_reruns_publishes_closed_sessions(tmp_path, monkeypatch):
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'config.example.json').write_text((bench.PROJECT / 'config.example.json').read_text())
    monkeypatch.setattr(bench, 'source_hashes', lambda _project: {'main.txt': 'frozen'})
    monkeypatch.setattr(bench.subprocess, 'check_output', lambda *a, **k: 'registered-commit\n')
    monkeypatch.setattr(bench.time, 'sleep', lambda _: None)
    monkeypatch.setattr('shore_agent.code_execution.sandbox_info', lambda *_: {'available': True, 'image_id': 'frozen'})
    calls = []
    secret = 'ephemeral-test-key'

    class Input:
        def write(self, value):
            assert json.loads(value) == {'api_key': secret}
        def close(self):
            pass

    class Process:
        def __init__(self, argv, **kwargs):
            directory = Path(argv[-1])
            assert directory.parent.name == '.E2-active'
            assert 'DEEPSEEK_API_KEY' not in kwargs['env']
            assert all(kwargs['env'][key] == '1' for key in bench.THREAD_VARS)
            self.pid = 1000 + len(calls)
            self.stdin = Input()
            calls.append(directory.name)
            (directory / 'result.json').write_text(json.dumps({'status': 'incomplete', 'reason': 'http_status_503'}))
        def poll(self):
            return 0

    monkeypatch.setattr(bench.subprocess, 'Popen', Process)
    output = tmp_path / 'report'
    result = bench.run(output, secret, project=project)
    assert len(calls) == len(set(calls)) == 30
    assert result['status'] == 'completed_all_attempts'
    assert len(list((project / 'runs').iterdir())) == 30
    assert json.loads((output / 'manifest.json').read_text())['source_unchanged']
    assert all(secret not in f.read_text() for f in tmp_path.rglob('*.json'))
