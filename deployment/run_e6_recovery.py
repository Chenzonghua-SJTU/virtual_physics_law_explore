"""Two complete repeats per no-extra-tool prompt after the user-directed bug fix."""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmark_v15 import configuration


def stop_runner(process):
    # The child benchmark needs time to reap its separately grouped worker.
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=15)
    except ProcessLookupError:
        pass
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def quality(rows):
    scores = [(r.get('evaluation_score') or {}).get('total', 0) if r.get('evaluation_complete') else 0 for r in rows]
    return [sum(s >= 90 for s in scores), sum(bool(r.get('evaluation_complete')) for r in rows), sum(scores)/len(scores)]


def main():
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    final = ROOT/'experiments/E5/e6-final-selection.json'
    if final.exists():
        raise SystemExit('Final selection already exists; no overwrite')
    cases = []
    for profile, repeat, port in (('baseline', 1, 8000), ('concise', 1, 8001),
                                  ('concise', 2, 8002), ('baseline', 2, 8003)):
        name = f'e6-qwen38-recovery-{profile}-20261107-r{repeat:02d}'
        output = ROOT/'experiments/E5'/name
        if output.exists():
            raise SystemExit('Study batch already exists; no retries')
        cases.append({'profile': profile, 'output': output, 'port': port})
    active = []
    completed = False
    deadline = time.monotonic() + 3600
    try:
        for case in cases:
            path = ROOT/f'deployment/config.e6.recovery-{case["profile"]}.json'
            log = (ROOT/'deployment'/f'{case["output"].name}.log').open('ab')
            command = [sys.executable, '-u', 'benchmark_v15.py', '--config', str(path),
                '--ruleset', 'e5', '--no-thinking', '--workers', '1',
                '--model-endpoints', f'http://127.0.0.1:{case["port"]}/v1', '--output', str(case['output'])]
            process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
            active.append((process, log))
        while any(p.poll() is None for p, _ in active):
            if time.monotonic() >= deadline:
                raise TimeoutError('Study exceeded one-hour orchestration deadline; preserve partial records')
            time.sleep(2)
        if any(p.returncode != 0 for p, _ in active):
            raise RuntimeError('A study runner failed; inspect preserved records')
        completed = True
    finally:
        for process, log in active:
            if not completed and process.poll() is None:
                stop_runner(process)
            log.close()
    results = {p: [] for p in ('baseline', 'concise')}
    batch_ids = {p: [] for p in results}
    for case in cases:
        summary = json.loads((case['output']/'summary.json').read_text())
        results[case['profile']].extend(summary['worlds'])
        batch_ids[case['profile']].append(summary['experiment_id'])
    selected = max(results, key=lambda p: quality(results[p]))
    config = configuration(ROOT, config_path=ROOT/f'deployment/config.e6.recovery-{selected}.json',
                           thinking=False, ruleset='e5')
    config_path = ROOT/'deployment/config.e6.final.json'
    config_path.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
    data = {'selected_profile': selected, 'sampling_seed': None, 'max_total_tokens': None,
            'loop_recovery': True, 'configuration': str(config_path.relative_to(ROOT)),
            'last_repeat_batch': batch_ids[selected][-1],
            'batches': batch_ids, 'quality': {p: quality(rows) for p, rows in results.items()},
            'selection_basis': 'Most complete worlds with raw score>=90 across both complete repeats; then completion; then mean with incomplete=0. No best-of-world aggregation.',
            'limitations': 'Best among these tested configurations; no claim of global or hidden-world optimality.'}
    final.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(data,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
