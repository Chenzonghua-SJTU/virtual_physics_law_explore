# E3：简化代码接口与结果返回

本轮按用户调整完成15次简化代码组复测，高精度 **15/15**。高精度是完整隐藏位置RMSE<1e-6；执行成功、局部验证和独立隐藏测评分别统计。

## 改了什么

普通脚本可直接使用inputs，将输出赋给result；不再要求analyze函数或输出schema。NumPy数组/标量及元组自动转JSON；非有限值明确报错。旧analyze函数可兼容，仅print的脚本不因缺少结构化输出而报错，但会返回明确提示。

完整代码、输入来源哈希、结果与有界日志仍留档；模型默认只收到精简结果、日志、错误位置及输入形状。取消重复回传代码/schema，小型比较表不再按6行阈值截断，大结果标记truncated，可用call_back按字段/范围读取。日志每路完整记录上限仍为16000字符，默认预览1500字符；结果预览约8000字符。没有新增子Agent、强制研究状态、科学候选模板、自动改代码重试或对话历史压缩。最终仍用原fit/validate/submit提交受限表达式。

## 实验协议

世界3/4/5 × 简化code × 每世界5次，共15次。DeepSeek Flash、thinking=true、high，5M总Token、393216单次输出上限、无模型调用次数限制、每会话3600秒。3并发、数值库单线程；环境v4、seed=42、无噪声、固定布局。提交后20条隐藏轨迹，seed=1871。调度seed=2026110403。科学失败不补跑；账户401/402会停止后续排队。

实现冻结提交`7fc4e94`，镜像`sha256:2a50e2592133c23969506e674151b83a9886da3254139a618c1cf65702b81988`。原工具组main.txt和7个工具定义与E2逐项核对相同；运行中不修改代码。E2用于跨批次描述性比较，不能当作同一批随机对照或合并到本轮分母。

最初误按完整对照安排了30次，用户明确缩减为15次代码组后立即停止原调度器，取消1次在途原工具组，剩余8次原工具组不再启动。此前完成的6次原工具组仅作为附加记录保留，不计入主结果。原始调度保存在original_schedule/，取消和范围调整见scope_change.json、excluded_baseline_summary.json；代码组未中断、未替换、未重跑。调整后仍最多3并发，但并发任务构成变化，因此耗时的跨批次比较仅供描述。

## 科学结果

| 世界 | E2旧code | E3简化code |
|---|---:|---:|
| world_3 | 5/5 | 5/5 |
| world_4 | 5/5 | 5/5 |
| world_5 | 3/5 | 5/5 |
| all | 13/15 | 15/15 |

| 世界 | E3组 | 已提交/计划 | 已完整评测/计划 | 已评分均分(n) | 总耗时中位数(s) | API时间中位数(s) | 工具时间中位数(s) | Token中位数(M) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| world_3 | code | 5/5 | 5/5 | 98.51（5） | 321.1 | 294.8 | 8.4 | 0.846 |
| world_4 | code | 5/5 | 5/5 | 98.12（5） | 256.5 | 208.9 | 28.3 | 0.705 |
| world_5 | code | 5/5 | 5/5 | 97.45（5） | 419.8 | 386.3 | 10.1 | 2.131 |
| all | code | 15/15 | 15/15 | 98.03（15） | 321.1 | 294.8 | 12.4 | 1.038 |

分数沿用题目显示公式的本地实现，不代表官方成绩，也不能代替高精度门槛。缺失分数不计0且不进入均分分母。时间包含正常失败；API时间含网络和服务等待。各列独立取中位数，不应相加。

## 代码错误与返回体积

| 批次/世界 | 工具调用 | 执行成功 | 未成功调用 | 未成功比例 | 返回中位数(bytes) | 纯print提示次数 | 按字段读取次数 |
|---|---:|---:|---:|---:|---:|---:|---:|
| E2/world_3 | 43 | 35 | 8 | 18.6% | 5172 | 0 | 0 |
| E2/world_4 | 35 | 26 | 9 | 25.7% | 5335 | 0 | 0 |
| E2/world_5 | 92 | 74 | 18 | 19.6% | 5173 | 0 | 0 |
| E2/all | 170 | 135 | 35 | 20.6% | 5240 | 0 | 0 |
| E3/world_3 | 46 | 43 | 3 | 6.5% | 1312 | 28 | 1 |
| E3/world_4 | 46 | 39 | 7 | 15.2% | 1578 | 24 | 0 |
| E3/world_5 | 84 | 73 | 11 | 13.1% | 1466 | 72 | 1 |
| E3/all | 176 | 155 | 21 | 11.9% | 1446 | 124 | 2 |

E2错误类别：`{"other_code_or_numerical_error": 22, "script_entry_contract": 8, "output_schema": 2, "timeout": 1, "scientific_type_serialization": 1, "tool_argument_or_entry_error": 1}`。具体异常类型：`{"KeyError": 2, "LinAlgError": 2, "TypeError": 3, "NameError": 8, "SyntaxError": 2, "UnboundLocalError": 2, "ValueError": 9, "IndexError": 3, "OutputSchemaError": 2, "timeout": 1, "ValidationError": 1}`。重复返回的代码/schema字段字节数：446,288。

E3错误类别：`{"other_code_or_numerical_error": 16, "tool_argument_or_entry_error": 2, "execution_environment_or_protocol_error": 1, "timeout": 2}`。具体异常类型：`{"LinAlgError": 4, "AttributeError": 2, "ValidationError": 2, "ValueError": 5, "KeyError": 2, "NameError": 1, "TimeoutExpired": 1, "timeout": 2, "TypeError": 1, "IndexError": 1}`。重复返回的代码/schema字段字节数：0。

调用分母包含入口参数校验失败；已归档执行次数不含被入口拦截的调用。E3允许纯print脚本，仅提示缺少结构化结果，因此部分“缺少analyze”的旧错误现在成为正常执行；这体现协议摩擦减少，不能单独证明数学正确或推理能力提高。其余计算错误、资源超时与科学失败仍保留。

返回字节数是单条工具JSON消息大小，不是服务端Token计费；不同批次生成的分析不同，不能把差额全部归因于接口。E3不再回传代码/schema是直接实现保证，原始调用中的代码仍留在对话历史，所以本次并未消除全部长上下文开销。

## 未达高精度的运行

| 会话 | 隐藏RMSE | 结束原因 | 剩余能量 | 总Token |
|---|---:|---|---:|---:|
| 无 | — | — | — | — |

逐例分析另见[case_notes.md](case_notes.md)，依据公开代码、拟合、验证和提交记录；不读取或发布私有思考。

## 复核与限制

- [manifest.json](manifest.json)：完整配置、运行顺序、冻结源码/镜像、时间与结束状态。
- [summary.json](summary.json)：15次逐次结果、题目分、最终公式、耗时与服务端请求元数据。
- [diagnostics.json](diagnostics.json)、[code_audit.json](code_audit.json)：实际提示词、输入及产物哈希校验，公开代码和输出预览。
- [interface_metrics.json](interface_metrics.json)：E2/E3代码调用、错误、返回体积及逐次记录。
- [environment.json](environment.json)：环境版本及720项测试通过，含真实Docker与HTTP接口。
- 复核顺序：运行本目录analyze.py、interface_audit.py、report.py；不会调用模型。
- 每世界仅5次，固定布局及同一隐藏集。结果主要反映本次模型随机性，不覆盖跨布局、噪声、其他模型。服务商模型别名并非固定权重。
- 完整本机会话在runs/E3-*；发布目录只含白名单科学数据和请求元数据，不含密钥、私有推理或原始提供商响应。

15次代码组累计用量：20,212,111 Token；原工具组附加尝试的消耗另存excluded_baseline_summary.json。

## 逐次结果

| 世界 | 组 | 重复 | 会话 | 高精度 | 隐藏RMSE | 总耗时(s) | 代码调用 |
|---|---|---:|---|---|---:|---:|---:|
| world_3 | code | 1 | E3-code-w3-r1 | 是 | 8.31056300e-08 | 284.7 | 7 |
| world_3 | code | 2 | E3-code-w3-r2 | 是 | 6.67463926e-08 | 321.1 | 7 |
| world_3 | code | 3 | E3-code-w3-r3 | 是 | 8.19030363e-08 | 368.9 | 9 |
| world_3 | code | 4 | E3-code-w3-r4 | 是 | 6.16346180e-07 | 497.1 | 10 |
| world_3 | code | 5 | E3-code-w3-r5 | 是 | 4.13840410e-08 | 298.6 | 13 |
| world_4 | code | 1 | E3-code-w4-r1 | 是 | 4.77713085e-07 | 256.5 | 14 |
| world_4 | code | 2 | E3-code-w4-r2 | 是 | 9.69547242e-08 | 218.6 | 3 |
| world_4 | code | 3 | E3-code-w4-r3 | 是 | 9.54992471e-08 | 521.7 | 15 |
| world_4 | code | 4 | E3-code-w4-r4 | 是 | 9.00861591e-08 | 260.6 | 8 |
| world_4 | code | 5 | E3-code-w4-r5 | 是 | 2.80193504e-07 | 256.5 | 6 |
| world_5 | code | 1 | E3-code-w5-r1 | 是 | 7.29790167e-08 | 353.1 | 10 |
| world_5 | code | 2 | E3-code-w5-r2 | 是 | 1.02115072e-07 | 419.8 | 19 |
| world_5 | code | 3 | E3-code-w5-r3 | 是 | 1.04731737e-07 | 302.8 | 8 |
| world_5 | code | 4 | E3-code-w5-r4 | 是 | 2.73461744e-07 | 1096.5 | 30 |
| world_5 | code | 5 | E3-code-w5-r5 | 是 | 7.63350717e-08 | 515.2 | 17 |
