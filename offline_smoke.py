"""MANUAL ENGINEERING SMOKE TEST. This is NOT autonomous model discovery.

Runs one manually chosen generic affine candidate through the real observation,
fitting, validation, residual and submission tools, without calling a model.
"""
import argparse
import json
from pathlib import Path
from shore_agent.environment import Environment
from shore_agent.runtime import ToolRuntime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--noise', action='store_true')
    args = parser.parse_args()
    directory = Path(args.run_dir)
    if directory.exists() and any(directory.iterdir()):
        parser.error('Use a new empty directory')
    directory.mkdir(parents=True, exist_ok=True)
    config = {'noise': args.noise, 'seed': 20261101}
    (directory/'config.json').write_text(json.dumps({'environment': config, 'mode': 'manual_engineering_smoke'}))
    with Environment(config) as env:
        rt = ToolRuntime(env, directory)
        assert rt.mission()['ok']
        def call(name, **kwargs):
            result = rt.execute(name, kwargs)
            if not result['ok']:
                raise RuntimeError(result['error'])
            return result['data']
        train = call('insert_probe', probes=[{'r0': r, 'v0': v, 'properties': {}}
                    for r,v in [([-3,-2],[1,0]), ([3,2],[-1,1]), ([1,-3],[0,2]), ([-2,3],[1,-1])]],
                     t0=0, dt=0.1, n_samples=40)
        law = call('fit_law_and_rollout', law_spec={'ax': 'a*x+b*y+c', 'ay': 'b*x+d*y+e'},
                   parameter_spec=[{'name': n, 'initial': 0, 'lower': -2, 'upper': 2} for n in 'abcde'],
                   train_probe_ids=[p['probe_id'] for p in train['probes']])
        test = call('insert_probe', probes=[{'r0': r, 'v0': v, 'properties': {}}
                    for r,v in [([4,-1],[-1,-2]), ([-4,4],[2,1]), ([1,2],[0,-1])]], t0=4, dt=0.1, n_samples=50)
        ids = [p['probe_id'] for p in test['probes']]
        val = call('validate_law', law_id=law['law_id'], test_probe_ids=ids)
        call('analyze_residual', law_id=law['law_id'], probe_ids=ids)
        submission = call('submit', law_id=law['law_id'], claims={'dynamics_order': 2, 'hidden_matter': False, 'time_dependence': False},
                          physical_explanation='手工工程检查：候选加速度是位置的仿射函数，线性项描述加速度随位置的变化，常数项描述均匀偏置。'
                          '线性系数单位为时间的负二次方，常数项单位为长度/时间平方。该候选不显式依赖速度或时间；'
                          '这是人工指定结构的数学解释，不是 Agent 自主发现，也不能据此唯一识别作用源。')
        result = {'status': 'submitted' if submission['status']=='accepted' else 'incomplete',
                  'mode': 'manual_engineering_smoke', 'autonomous_discovery': False,
                  'note': 'Manually selected affine structure and declarations. No LLM called; not evidence of autonomous discovery.',
                  'submission': submission, 'validation': val['errors'], 'budget': rt.budget()}
        (directory/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
