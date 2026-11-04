"""Collect public results from the completed real rerun, without model calls."""
from collections import Counter
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
PREVIOUS = ROOT / 'experiments/seven-worlds-v0.1.0-20261103'


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def lines(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s] if path.exists() else []


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


summary = read(OUT / 'summary.json')
assert summary['status'] == 'completed_all_attempts', 'Wait until all seven attempts finish.'
source = read(Path('/private/tmp/shore-seven-worlds-fixes-source.json'))
source['changed_tracked_files'] = [f for f, h in source['tracked_file_sha256'].items()
                                  if hashlib.sha256((ROOT/f).read_bytes()).hexdigest() != h]
source['source_unchanged'] = not source['changed_tracked_files']
assert source['source_unchanged']
write('source-provenance.json', source)
old_rows = {row['world_id']: row for row in read(PREVIOUS/'summary.json')['worlds']}
rows = []
for row in summary['worlds']:
    directory = ROOT/'runs'/row['run_id']
    evaluation = read(directory/'evaluation.json', {})
    result = read(directory/'result.json', {})
    tools = lines(directory/'tools.jsonl')
    requests = [e for e in lines(directory/'model_events.jsonl') if e.get('event') == 'request']
    laws = [read(f) for f in sorted((directory/'records/law').glob('*.json'))]
    validations = [read(f) for f in sorted((directory/'records/validation').glob('*.json'))]
    old = old_rows[row['world_id']]
    old_eval = read(ROOT/'runs'/old['run_id']/'evaluation.json', {})
    metrics = evaluation.get('overall') or {}
    current = dict(row,
        score=evaluation.get('score'),
        tool_counts=dict(Counter(e['tool'] for e in tools)),
        tool_errors=[{'index': i, 'tool': e['tool'], 'error': e['result'].get('error'),
                      'arguments': {k: v for k, v in e['arguments'].items() if k != 'physical_explanation'}}
                     for i, e in enumerate(tools, 1) if not e['result'].get('ok')],
        api_requests=[{k: e.get(k) for k in ('call_number', 'http_status', 'error', 'finish_reason', 'usage', 'elapsed_seconds')}
                      for e in requests],
        prompt_estimates=[{'call': e.get('call_number'),
                           **(e.get('budget_usage', {}).get('request_budget') or {})} for e in requests],
        laws=[{k: law.get(k) for k in ('law_id', 'law_spec', 'parameter_spec', 'fitted_parameters',
                                      'train_probe_ids', 'fit_status', 'converged', 'refinement', 'objective_calls')}
              | {'errors': (law.get('errors') or {}).get('overall')} for law in laws],
        validations=[{k: v.get(k) for k in ('validation_id', 'law_id', 'test_probe_ids')}
                     | {'errors': (v.get('errors') or {}).get('overall')} for v in validations],
        final_budget=result.get('budget'), final_model_usage=result.get('model_usage'),
        previous={'run_id': old['run_id'], 'status': old['status'], 'calls': old.get('calls'), 'tokens': old.get('tokens'),
                  'score': (old_eval.get('score') or {}).get('total'),
                  'position_rmse': (old_eval.get('overall') or {}).get('position_rmse')})
    rows.append(current)

report = {'kind': 'seven_real_autonomous_attempts_after_engineering_fixes',
          'commit': source['commit'], 'source_unchanged': True,
          'started_at': summary['started_at'], 'finished_at': summary.get('finished_at'),
          'locally_submitted': sum(bool(r['accepted_submission']) for r in rows),
          'independently_evaluated': sum(bool(r['independent_evaluation_complete']) for r in rows),
          'calls': sum(r.get('calls') or 0 for r in rows), 'tokens': sum(r.get('tokens') or 0 for r in rows),
          'previous_calls': sum(r.get('calls') or 0 for r in old_rows.values()),
          'previous_tokens': sum(r.get('tokens') or 0 for r in old_rows.values()),
          'scope': 'One attempt per world, no manual candidates, retries of entire sessions or explanation changes. Provider HTTP retries retain existing policy.',
          'worlds': rows}
write('diagnostics.json', report)


def num(value, fmt):
    return format(value, fmt) if isinstance(value, (int, float)) else '—'


text = ['# 修复版七世界真实探索复测', '',
        f"代码版本：`{source['commit']}`。七次运行期间已跟踪文件哈希保持不变。", '',
        '每世界一次真实自主探索，DeepSeek Flash、thinking=true、reasoning_effort=low、无噪声、种子42；'
        '总预算每世界2,000,000 token、单次输出65,536、模型调用次数不限。每次提交后独立评测20组隐藏初态，评测种子1871。'
        '原始会话均保留在工作台历史中，不以手工拟合或补提交替代失败结果。', '',
        '| 世界 | 旧得分 → 新得分 | 旧位置 RMSE → 新位置 RMSE | 调用数 | Token | 状态 |',
        '|---|---|---|---:|---:|---|']
for row in rows:
    old = row['previous']
    score = (row.get('score') or {}).get('total')
    rmse = (row.get('independent_rmse') or {}).get('position_rmse')
    text.append(f"| {row['world_id']} | {num(old['score'], '.2f')} → {num(score, '.2f')} | "
                f"{num(old['position_rmse'], '.3e')} → {num(rmse, '.3e')} | {row['calls']} | {row['tokens']:,} | {row['status']} |")
text += ['', f"合计 {report['calls']} 次 API 请求，{report['tokens']:,} token；上一轮 {report['previous_calls']} 次、"
         f"{report['previous_tokens']:,} token。实际提交 {report['locally_submitted']}/7，完成独立评测 {report['independently_evaluated']}/7。", '',
         '同一仿真种子固定环境及评测条件，不固定服务商模型回复；每世界只有一个样本，不能据此估计成功率或将全部差异归因于代码修复。'
         '得分采用题目公式；RMSE是额外诊断，不另设通关阈值。物理解释的正确性仍不参与评分。', '', '## 各世界记录', '']
for row in rows:
    text += [f"### {row['world_id']} · `{row['run_id']}`", '',
             f"结束原因：`{row.get('reason')}`；工具错误 {len(row['tool_errors'])} 次。", '']
    law = row.get('law')
    if law:
        text += ['```text', f"ax = {law['law_spec']['ax']}", f"ay = {law['law_spec']['ay']}",
                 json.dumps(law['fitted_parameters'], ensure_ascii=False), '```', '']
    if row['tool_errors']:
        text += [f"- 工具步骤 {e['index']} / `{e['tool']}`：{json.dumps(e['error'], ensure_ascii=False)}" for e in row['tool_errors']]
        text += ['']
text += ['详细工具错误、参数精修状态、预算预估及实际 API 用量见 [diagnostics.json](diagnostics.json)。', '']
(OUT/'comparison.md').write_text('\n'.join(text))
print(json.dumps({k: v for k, v in report.items() if k != 'worlds'}, ensure_ascii=False, indent=2))
for r in rows:
    print(json.dumps({'world': r['world_id'], 'status': r['status'], 'score': (r.get('score') or {}).get('total'),
                      'rmse': r.get('independent_rmse'), 'calls': r['calls'], 'tokens': r['tokens'],
                      'tool_errors': len(r['tool_errors'])}, ensure_ascii=False))
