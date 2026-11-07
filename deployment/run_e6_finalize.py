"""One preregistered confirmation in the original unseeded sampling mode."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmark_v15 import configuration, run


def main():
    selected = ROOT/'experiments/E5/e6-selection.json'
    final = ROOT/'experiments/E5/e6-final-selection.json'
    if final.exists():
        raise SystemExit('Final selection exists; do not overwrite or rerun')
    deadline = time.monotonic()+3600
    while not selected.exists():
        if time.monotonic() >= deadline:
            raise SystemExit('E6 selection not ready; no confirmation started')
        time.sleep(2)
    choice = json.loads(selected.read_text())
    profile = choice['selected_profile']
    config_path = ROOT/'deployment/config.e6.final.json'
    config = configuration(ROOT, config_path=ROOT/f'deployment/config.e6.{profile}-s42.json',
                           thinking=False, ruleset='e5')
    config['model'].pop('sampling_seed', None)
    config_path.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
    output = ROOT/'experiments/E5/e6-qwen38-final-unseeded-20261107-r01'
    summary = run(output, config, '', workers=4,
                  model_endpoints=[f'http://127.0.0.1:{p}/v1' for p in range(8000,8004)])
    data = {'selected_profile':profile,'sampling_seed':None,'configuration':str(config_path.relative_to(ROOT)),
            'confirmation_batch':summary['experiment_id'],'selection_basis':choice,
            'note':'Best tested prompt by the preregistered seeded comparison, confirmed once under original unseeded sampling; no global or hidden-world optimality claim.'}
    final.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(data,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
