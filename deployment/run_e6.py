"""Bounded preregistered no-new-tool prompt comparison, without per-world retries."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmark_v15 import configuration, run


def quality(summaries):
    worlds = [w for s in summaries for w in s['worlds']]
    scores = [w.get('evaluation_score', {}).get('total', 0)
              if isinstance(w.get('evaluation_score'), dict) and w.get('evaluation_complete') else 0
              for w in worlds]
    return [sum(score >= 90 for score in scores),
            sum(bool(w.get('evaluation_complete')) for w in worlds), sum(scores)/len(scores)]


def main():
    outcome = ROOT/'experiments/E5/e6-selection.json'
    if outcome.exists():
        raise SystemExit('Selection already exists: no automatic repeat or overwrite')
    results = {}
    endpoints = [f'http://127.0.0.1:{p}/v1' for p in range(8000, 8004)]

    def batch(profile, seed):
        config = configuration(ROOT, config_path=ROOT/f'deployment/config.e6.{profile}-s{seed}.json',
                               thinking=False, ruleset='e5')
        name = f'e6-qwen38-{profile}-s{seed}-20261107'
        output = ROOT/'experiments/E5'/name
        summary = run(output, config, '', workers=4, model_endpoints=endpoints)
        if not isinstance(summary, dict):
            summary = json.loads((output/'summary.json').read_text())
        results.setdefault(profile, []).append(summary)
        print(json.dumps({'event':'batch_finished','batch':name,'quality':quality([summary])}),flush=True)

    for profile in ('baseline', 'e3', 'concise'):
        batch(profile, 42)
    challenger = max(('e3', 'concise'), key=lambda p: quality(results[p]))
    for profile in ('baseline', challenger):
        batch(profile, 43)
    selected = challenger if quality(results[challenger]) > quality(results['baseline']) else 'baseline'
    data = {'selected_profile': selected, 'challenger': challenger,
            'selection_uses_complete_batches_only': True,
            'quality_order': ['count_score_ge_90','evaluation_complete','mean_score_incomplete_as_zero'],
            'profiles': {p:{'quality':quality(s),'batches':[b['experiment_id'] for b in s]}
                         for p,s in results.items()},
            'limitations': 'Two repeats for selected comparison; development-world selection, not evidence of hidden-world generalization.'}
    outcome.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'event':'phase1_finished',**data},ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
