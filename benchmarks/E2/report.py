"""Render the completed E2 audit; does not run models or change experiment code."""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]


def read(path):
    return json.loads(path.read_text())


def main():
    summary = read(OUT/'combined_summary.json')
    audit = read(OUT/'diagnostics.json')
    assert summary['status'] == 'completed_all_attempts' and len(summary['rows']) == 30
    rows = summary['rows']
    groups = audit['groups']
    overall = {g['arm']:g for g in groups if g['world_id'] == 'all'}
    base, code = overall['baseline'], overall['code']
    lines = ['# E2：开放 Python 分析能力是否有帮助', '',
        f'30个计划单元完成：原工具组高精度成功 **{base["high_precision"]}/15**，增加 `run_code` 组 **{code["high_precision"]}/15**。'
        '高精度指完整独立评测位置 RMSE < 1e-6；代码执行成功与高精度成功分别统计。', '',
        '## 实验设计与额度中断', '',
        '世界3、4、5，每组各5次。两组均为 DeepSeek Flash、thinking=true、high 推理强度、5M总Token、单次输出上限393216，'
        '无模型调用次数上限。每会话3600秒，固定3并发、数值库单线程。环境v4、seed=42、无噪声、固定天体布局；'
        '每个提交使用20条独立隐藏轨迹、seed=1871评测。E1没有作为控制组复用。', '',
        '原工具组保持原始main.txt和7个工具；代码组只增加可选run_code及必要接口说明，没有新增强制反思、进度或研究状态更新步骤。'
        '代码每次在无网络、无宿主挂载的Docker容器执行，最多1CPU、1GiB、90秒。最终仍通过正式拟合、验证、submit提交受限表达式。', '',
        '首批30次中9次正常完成，21次被账户HTTP402中断（其中18次没有得到模型回复）。用户恢复额度并授权继续后，'
        '只对21个402单元从新会话补跑，配置、提示词、源代码、镜像不变；保留原9次，包括已经完成的科学失败。'
        '因此共留存51次实际尝试，主表是**额度恢复后30个计划单元的结果，不是首批一次运行成功率**。'
        '补跑时恢复完整会话预算，原中断消耗单列。此调整在补跑前写入 recovery-1/manifest.json；不重跑科学失败或预算失败。', '',
        '首批完整结果见[summary.json](summary.json)与[comparison.md](comparison.md)，恢复后的主结果见'
        '[combined_summary.json](combined_summary.json)。后者每行标注原尝试编号和是否补跑。', '',
        '## 成功率与题目公式得分', '',
        '| 世界 | 原工具高精度 | 加代码高精度 | 原工具完整评测 | 加代码完整评测 | 原工具平均分（已评分n） | 加代码平均分（已评分n） |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for world in ['world_3','world_4','world_5','all']:
        pair = {g['arm']:g for g in groups if g['world_id']==world}
        a,b=pair['baseline'],pair['code']
        lines.append(f'| {world} | {a["high_precision"]}/{a["scheduled"]} | {b["high_precision"]}/{b["scheduled"]} | '
            f'{a["evaluated"]}/{a["scheduled"]} | {b["evaluated"]}/{b["scheduled"]} | '
            f'{a["mean_score_scored_only"]:.2f}（{a["score_n"]}） | {b["mean_score_scored_only"]:.2f}（{b["score_n"]}） |')
    lines += ['', '得分沿用项目按题目显示公式实现的本地评分，不能等同官方评测；未提交者没有分数，不计0分也不进入均分分母。'
        'RMSE明显未达高精度的近似模型仍可能取得高题目分，故必须同时看高精度次数与提交率。', '',
        '本次差异集中在世界3（2/5→5/5）和世界5（5/5→3/5），世界4两组均5/5。总体只多成功1次，不能据此认定稳定优势。', '',
        '## 耗时与用量', '',
        '下表均基于恢复后每个计划单元的一次有效尝试；失败也纳入。总耗时为工作进程启动至提交后评测结束；'
        'API时间包含网络及模型服务等待，不能解释为纯GPU计算时间。工具时间含run_code，不能与代码时间相加；各列是分别取中位数，也不能相加重建总耗时。', '',
        '| 世界 | 工具组 | 总耗时中位数(s) | API中位数(s) | 全部工具中位数(s) | 代码中位数(s) | 模型调用中位数 | Token中位数(M) |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for g in groups:
        lines.append(f'| {g["world_id"]} | {g["arm"]} | {g["median_seconds"]:.1f} | {g["median_api_seconds"]:.1f} | '
            f'{g["median_tool_seconds"]:.1f} | {g["median_code_seconds"]:.1f} | {g["median_model_calls"]:g} | {g["median_tokens"]/1e6:.3f} |')
    lines += ['', f'恢复后30个单元共消耗 {audit["retained_cell_tokens"]:,} Token；'
        f'21次额度中断尝试另消耗 {audit["quota_interrupted_attempt_tokens"]:,} Token；'
        f'51次实际尝试合计 {audit["all_attempt_tokens"]:,} Token。这里只统计服务端返回的用量，不推算金额。', '',
        f'代码容器累计耗时 {code["code_seconds"]:.1f} 秒，其中执行器可报告的累计CPU时间为 {code["total_code_cpu_seconds_reported"]:.1f} 秒。'
        'CPU时间不含容器启动，也不能覆盖被强制终止后没有上报的消耗；它是部分可观测的执行开销，不等于全部计算成本。', '',
        f'代码组15次中有 {code["runs_using_code"]} 次实际调用代码，归档执行 {code["code_calls"]} 次，'
        f'其中 {code["code_successes"]} 次运行及输出格式成功。代码调用状态（包含入口校验失败）：`{json.dumps(audit["retained_code_status_counts"], ensure_ascii=False)}`。'
        '接口参数校验失败发生在容器运行之前，单列为argument_or_runtime_error，不计入归档执行次数。', '',
        f'代码相关错误类型（恢复后30个单元）：`{json.dumps(audit["retained_code_error_types"], ensure_ascii=False)}`。'
        '错误会返回主Agent，后续调用可自行纠正；成功状态不保证分析方法或结论正确。', '',
        '## 代码实际新增了什么', '',
        '原fit工具也能拟合Agent给出的具体表达式。run_code新增的是**主Agent自己选择数据处理、候选比较和数值分析算法并实际执行**；'
        '不是证明原工具绝对不能发现相同规律。以下来自公开代码和结果，源码、输入引用与后续调用见[code_audit.json](code_audit.json)。', '',
        '1. **世界3：按源点构造基函数并成批比较。** `E2-code-w3-r1 / code_655439848d03`对齐加速度估计时间与位置，'
        '比较逐源线性项、三次径向项、各天体系数、额外高次项等，估计共享系数约0.059996和0.00399983。'
        '后续正式轨迹拟合、验证及隐藏评测达到1.13e-7。这里的初估来自差分加速度，最后精度来自正式整条轨迹验证。', '',
        '2. **世界4：自写核函数比较与多初值搜索。** `E2R1-code-w4-r2 / code_3cfd69ca9678`比较'
        '`g·d/(|d|²+s²)^(p/2)`、固定p=2/3、无软化及分源系数。差分数据上的自由指数约3.087，'
        '固定p=3误差约0.00592，p=2约0.0529；这提供候选选择证据，不应把初估当最终精确参数。该会话隐藏RMSE为7.96e-8。', '',
        '3. **世界5：提取速度耦合并比较空间核。** `E2-code-w5-r1 / code_2ca2f3297d4a`从空间网格轨迹中扣除位置回复项，'
        '估计随位置变化的旋转系数；`code_ca96415870fd`在444个状态样本上批量比较指数、Gauss、逆一次和逆二次软化核。'
        '逆二次核的系数约0.9999、长度尺度约0.9978；x分量差分加速度RMSE约0.00145，优于该次指数核0.00215。'
        '随后law_1正式拟合得到k≈0.1、c≈1、e≈1，隐藏RMSE为7.37e-8。代码让这些定量比较成为可执行操作。', '',
        '上述先后关系证明工具提供了可用计算结果，并记录了后续候选；不能单独证明某个代码调用造成成功。'
        '组间结果衡量的是“增加代码能力及接口说明”的整体效果。', '',
        '## 失败与改进线索', '',
        '**原工具世界3三次提前接受了近似模型。** `E2-baseline-w3-r1`、`E2R1-baseline-w3-r3`、`E2R1-baseline-w3-r5`采用平移中心的各向异性三次回复近似，'
        '隐藏RMSE分别为0.10418、0.09189、0.05309；训练RMSE已经约0.00136、0.00330、0.00184，验证也非数值精度级。'
        '三次结束时仍剩70/87/64能量、约3040/3241/2888秒，因而不是额度耗尽。真实结构是对各源点的'
        '`Σ_b (0.06+0.004|b−r|²)(b−r)`，上述受约束中心形式没有正确表达全部空间项。', '',
        '**代码组世界5第4次分析过久，最后才找到正确核。** `E2R1-code-w5-r4`用了35次模型调用、4,876,865 Token。'
        '下一次请求估计输入290,620 Token，大于剩余123,135，因此在调用前停止；这不是单次输出截断，也不是API再次402。'
        '该会话先重复线性/多项式、纯逆距离和隐源分析，早期两次忘记把逻辑放入analyze(inputs)，又有一次输入别名数量超限。'
        '末次`code_9115eed1e198`已比较出`Σ1/(d²+a²)`且系数/尺度接近1，但来不及重新正式拟合、验证、提交。'
        '它保留为未完成，不能因末次结果接近真值而算成功。', '',
        '**代码组世界5第5次算了很多，却选中了错误核。** `E2R1-code-w5-r5`进行27次代码执行、38次模型调用，'
        '最终提交指数核`Ω(r)=p4+p2·Σexp(−|b−r|/p3)`。训练位置RMSE为0.01286，最后独立验证为0.01716，'
        '隐藏评测为0.12386。代码比较了纯逆距离、平方根软化和指数核等，但没有完成对正确逆二次软化结构的确认。'
        '当时仍剩77能量和约2621秒；这次是候选选择与停止判断失败，不是容器故障或预算耗尽。'
        '不少代码仅返回`{"ok":1}`，实质数值写在stdout；执行成功本身没有给候选选择增加保证。', '',
        '后续优先改进方向是：让代码默认返回小型比较表与必要诊断，把大数组留为产物或可回调记录；'
        '明确输入别名与analyze(inputs)契约；减少不断增长的会话重复携带已有数值数据。'
        '这些可以减少重复和上下文膨胀，但本次没有边跑边修改，也没有为代码组增加额外预算。'
        '本次不引入子Agent、不强制输出研究状态或进度。', '',
        '## 结论边界', '',
        '保留run_code作为可选能力是合理的：新增的数据变换和批量数值比较确实被使用，世界3出现收益；'
        '但它没有保证成功，也没有证明在每个世界更快。工作台默认仍关闭，由高级设置开启。'
        '不要把本次小样本结果理解为代码组普遍优于原工具组。', '']
    for arm,g in overall.items():
        low,high=g['high_precision_wilson_95']
        lines += [f'- {arm}总体成功率Wilson 95%区间约 {low:.1%}–{high:.1%}。']
    lines += ['', '每世界每组只有5次，固定布局、同一环境种子和隐藏集，重复主要测模型随机性；'
        '不覆盖噪声、跨布局泛化或其他模型。两批跨越额度恢复，提供商管理的模型别名并非固定权重。'
        'HTTP状态、返回model及system_fingerprint均记录在diagnostics.json，不能据此保证提供商内部版本完全不变。', '',
        '## 复核与产物', '',
        '- 运行实现冻结在`44e05bc`；原始配置/提示词/源码SHA256和镜像ID见[manifest.json](manifest.json)。',
        '- 补跑协议与每个原始单元的映射见[recovery-1/manifest.json](recovery-1/manifest.json)。',
        '- 统计、来源审计与逐次拟合/验证记录见[diagnostics.json](diagnostics.json)；所有代码记录见[code_audit.json](code_audit.json)。',
        '- 审计校验两组实际提示词、逐次配置、输入记录哈希、产物哈希及冻结源码一致；有效本机会话保存在runs/E2-*与runs/E2R1-*。21次402原始记录已在runs/.trash/中，审计只读它们，不恢复历史列表。每条实际路径见diagnostics.json。',
        '- [environment.json](environment.json)记录容器/科学库版本及707项测试通过（包含真实容器隔离、超时、内存、科学计算、产物与网页接口）。',
        '- 复核命令：`.venv/bin/python benchmarks/E2/analyze.py`，再运行`.venv/bin/python benchmarks/E2/report.py`。不调用模型。',
        '- 此目录仅保存白名单科学结果、代码和请求元数据；不保存API密钥、原始模型响应或私有思考。', '',
        '## 逐次有效结果', '', '| 世界 | 组 | 重复 | 会话 | 隐藏位置RMSE | 高精度 | 结束原因 | 耗时(s) |',
        '|---|---|---:|---|---:|---|---|---:|']
    for r in sorted(rows,key=lambda r:(r['world_id'],r['arm'],r['repeat'])):
        rmse=f'{r["position_rmse"]:.8e}' if r['position_rmse'] is not None else '—'
        lines.append(f'| {r["world_id"]} | {r["arm"]} | {r["repeat"]} | {r["run_id"]} | {rmse} | '
            f'{"是" if r["high_precision"] else "否"} | {r["reason"]} | {r["elapsed_seconds"]:.1f} |')
    (OUT/'README.md').write_text('\n'.join(lines)+'\n')
    print('Wrote benchmarks/E2/README.md')


if __name__ == '__main__':
    main()
