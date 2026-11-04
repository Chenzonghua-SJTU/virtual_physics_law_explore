"""Generate E3 tables from audited results; no model calls."""
import json
import re
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]


def read(p):return json.loads(p.read_text())


def main():
    s=read(OUT/'summary.json');d=read(OUT/'diagnostics.json');im=read(OUT/'interface_metrics.json')
    assert s['status']=='completed_all_attempts' and len(s['rows'])==15
    m=read(OUT/'manifest.json');groups=d['groups']
    allgroups={g['arm']:g for g in groups if g['world_id']=='all'}
    old=read(ROOT/'benchmarks/E2/combined_summary.json')
    lines=['# E2 R02：简化代码接口与结果返回', '',
        f'本轮按用户调整完成15次简化代码组复测，高精度 **{allgroups["code"]["high_precision"]}/15**。高精度是完整隐藏位置RMSE<1e-6；执行成功、局部验证和独立隐藏测评分别统计。','',
        '## 改了什么','',
        '普通脚本可直接使用inputs，将输出赋给result；不再要求analyze函数或输出schema。NumPy数组/标量及元组自动转JSON；'
        '非有限值明确报错。旧analyze函数可兼容，仅print的脚本不因缺少结构化输出而报错，但会返回明确提示。', '',
        '完整代码、输入来源哈希、结果与有界日志仍留档；模型默认只收到精简结果、日志、错误位置及输入形状。'
        '取消重复回传代码/schema，小型比较表不再按6行阈值截断，大结果标记truncated，可用call_back按字段/范围读取。'
        '日志每路完整记录上限仍为16000字符，默认预览1500字符；结果预览约8000字符。没有新增子Agent、强制研究状态、'
        '科学候选模板、自动改代码重试或对话历史压缩。最终仍用原fit/validate/submit提交受限表达式。','',
        '## 实验协议','',
        '世界3/4/5 × 简化code × 每世界5次，共15次。DeepSeek Flash、thinking=true、high，5M总Token、'
        '393216单次输出上限、无模型调用次数限制、每会话3600秒。3并发、数值库单线程；环境v4、seed=42、无噪声、固定布局。'
        '提交后20条隐藏轨迹，seed=1871。调度seed=2026110403。科学失败不补跑；账户401/402会停止后续排队。','',
        f'实现冻结提交`{m["git_commit"][:7]}`，镜像`{m["sandbox"]["image_id"]}`。原工具组main.txt和7个工具定义与E2 R01逐项核对相同；'
        '运行中不修改代码。E2 R01用于跨批次描述性比较，不能当作同一批随机对照或合并到本轮分母。', '',
        '最初误按完整对照安排了30次，用户明确缩减为15次代码组后立即停止原调度器，取消1次在途原工具组，剩余8次原工具组不再启动。此前完成的6次原工具组仅作为附加记录保留，不计入主结果。原始调度保存在original_schedule/，取消和范围调整见scope_change.json、excluded_baseline_summary.json；代码组未中断、未替换、未重跑。调整后仍最多3并发，但并发任务构成变化，因此耗时的跨批次比较仅供描述。', '',
        '## 科学结果', '',
        '| 世界 | E2 R01旧code | E2 R02简化code |',
        '|---|---:|---:|']
    for world in ['world_3','world_4','world_5','all']:
        oldg={g['arm']:g for g in old['groups'] if g['world_id']==world}
        newg={g['arm']:g for g in groups if g['world_id']==world}
        cells=[oldg['code'],newg['code']]
        lines.append('| '+world+' | '+' | '.join(f'{g["high_precision"]}/{g["scheduled"]}' for g in cells)+' |')
    lines+=['', '| 世界 | E2 R02组 | 已提交/计划 | 已完整评测/计划 | 已评分均分(n) | 总耗时中位数(s) | API时间中位数(s) | 工具时间中位数(s) | Token中位数(M) |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for g in groups:
        score=f'{g["mean_score_scored_only"]:.2f}（{g["score_n"]}）' if g['score_n'] else '—'
        lines.append(f'| {g["world_id"]} | {g["arm"]} | {g["submitted"]}/{g["scheduled"]} | {g["evaluated"]}/{g["scheduled"]} | '
            f'{score} | {g["median_seconds"]:.1f} | {g["median_api_seconds"]:.1f} | {g["median_tool_seconds"]:.1f} | {g["median_tokens"]/1e6:.3f} |')
    lines+=['', '分数沿用题目显示公式的本地实现，不代表官方成绩，也不能代替高精度门槛。缺失分数不计0且不进入均分分母。'
        '时间包含正常失败；API时间含网络和服务等待。各列独立取中位数，不应相加。', '',
        '## 代码错误与返回体积', '',
        '| 批次/世界 | 工具调用 | 执行成功 | 未成功调用 | 未成功比例 | 返回中位数(bytes) | 纯print提示次数 | 按字段读取次数 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for label in ['E2','E3']:
        display_label={'E2':'E2 R01','E3':'E2 R02'}[label]
        for g in im[label]:
            rate=f'{g["unsuccessful_fraction"]:.1%}' if g['invocations'] else '—'
            lines.append(f'| {display_label}/{g["world_id"]} | {g["invocations"]} | {g["successful_executions"]} | '
                f'{g["unsuccessful_invocations"]} | {rate} | {g["median_response_bytes"]:.0f} | {g["print_only_calls"]} | {g["field_reads"]} |')
    for label in ['E2','E3']:
        display_label={'E2':'E2 R01','E3':'E2 R02'}[label]
        g=im[label][-1]
        lines+=['',f'{display_label}错误类别：`{json.dumps(g["error_categories"],ensure_ascii=False)}`。'
            f'具体异常类型：`{json.dumps(g["errors"],ensure_ascii=False)}`。'
            f'重复返回的代码/schema字段字节数：{g["repeated_code_schema_bytes"]:,}。']
    lines+=['', '调用分母包含入口参数校验失败；已归档执行次数不含被入口拦截的调用。'
        'E2 R02允许纯print脚本，仅提示缺少结构化结果，因此部分“缺少analyze”的旧错误现在成为正常执行；'
        '这体现协议摩擦减少，不能单独证明数学正确或推理能力提高。其余计算错误、资源超时与科学失败仍保留。', '',
        '返回字节数是单条工具JSON消息大小，不是服务端Token计费；不同批次生成的分析不同，不能把差额全部归因于接口。'
        'E2 R02不再回传代码/schema是直接实现保证，原始调用中的代码仍留在对话历史，所以本次并未消除全部长上下文开销。', '',
        '## 未达高精度的运行', '',
        '| 会话 | 隐藏RMSE | 结束原因 | 剩余能量 | 总Token |', '|---|---:|---|---:|---:|']
    failures=[r for r in s['rows'] if not r['high_precision']]
    for r in failures:
        rmse=f'{r["position_rmse"]:.8e}' if r['position_rmse'] is not None else '—'
        lines.append(f'| {r["run_id"]} | {rmse} | {r["reason"]} | {(r.get("final_budget") or {}).get("energy_remaining","—")} | {r["tokens"]:,} |')
    if not failures:lines+=['| 无 | — | — | — | — |']
    lines+=['', '逐例分析另见[case_notes.md](case_notes.md)，依据公开代码、拟合、验证和提交记录；不读取或发布私有思考。', '',
        '## 复核与限制', '',
        '- [manifest.json](manifest.json)：完整配置、运行顺序、冻结源码/镜像、时间与结束状态。',
        '- [summary.json](summary.json)：15次逐次结果、题目分、最终公式、耗时与服务端请求元数据。',
        '- [diagnostics.json](diagnostics.json)、[code_audit.json](code_audit.json)：实际提示词、输入及产物哈希校验，公开代码和输出预览。',
        '- [interface_metrics.json](interface_metrics.json)：E2 R01/E2 R02代码调用、错误、返回体积及逐次记录。',
        '- [environment.json](environment.json)：环境版本及720项测试通过，含真实Docker与HTTP接口。',
        '- 复核顺序：运行归档目录benchmarks/E3/下的analyze.py、interface_audit.py、report.py；不会调用模型。',
        '- 每世界仅5次，固定布局及同一隐藏集。结果主要反映本次模型随机性，不覆盖跨布局、噪声、其他模型。服务商模型别名并非固定权重。',
        '- 完整本机会话在runs/E3-*；发布目录只含白名单科学数据和请求元数据，不含密钥、私有推理或原始提供商响应。','',
        f'15次代码组累计用量：{sum(r["tokens"] for r in s["rows"]):,} Token；原工具组附加尝试的消耗另存excluded_baseline_summary.json。', '',
        '## 逐次结果', '',
        '| 世界 | 组 | 重复 | 会话 | 高精度 | 隐藏RMSE | 总耗时(s) | 代码调用 |',
        '|---|---|---:|---|---|---:|---:|---:|']
    for r in sorted(s['rows'],key=lambda r:(r['world_id'],r['arm'],r['repeat'])):
        rmse=f'{r["position_rmse"]:.8e}' if r['position_rmse'] is not None else '—'
        lines.append(f'| {r["world_id"]} | {r["arm"]} | {r["repeat"]} | {r["run_id"]} | {"是" if r["high_precision"] else "否"} | '
            f'{rmse} | {r["elapsed_seconds"]:.1f} | {r["tool_counts"].get("run_code",0)} |')
    content='\n'.join(lines)+'\n'
    content=re.sub(r'\]\(([^)]+)\)', lambda m: ']('+('../E3/'+m[1] if '://' not in m[1] else m[1])+')', content)
    content=content.replace('## 改了什么', '原始会话前缀与归档路径保留E3，仅报告编号统一为E2 R02；见[E2轮次索引](README.md)。\n\n## 改了什么', 1)
    (ROOT/'benchmarks/E2/R02.md').write_text(content)
    print('Wrote benchmarks/E2/R02.md')


if __name__=='__main__':main()
