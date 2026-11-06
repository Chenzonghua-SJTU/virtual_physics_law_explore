# E3：服务器本地 Qwen 六世界基线

本轮将既有三组服务器实验归档为 E3，保留原始 experiment_id、run_id、summary 和报告，不移动或重写历史运行。

规则：v15 六个公开开发世界；100 能量、3600 秒；无噪声；关闭思考；每请求最多 65536 输出 token；使用自研候选积分与背景输入协议，非正式评测成绩。

GPU 0/1 分别运行两个 27B BF16 实例；GPU 2/3 共同运行 122B FP8。每批最多三个世界并发。

| 批次 | 模型 | 世界 | 状态 | 本地分数 | 总耗时秒（含评测） | 调用数 | 平均输出 token/请求 |
|---|---|---|---|---:|---:|---:|---:|
| E3 R01 | qwen3.8-27b | world_1 | submitted | 87.80 | 648.876 | 17 | 419.12 |
| E3 R01 | qwen3.8-27b | world_2 | submitted | 94.65 | 470.524 | 12 | 447.33 |
| E3 R01 | qwen3.8-27b | world_3 | submitted | 99.35 | 771.667 | 18 | 434.78 |
| E3 R01 | qwen3.8-27b | world_4 | submitted | 94.80 | 637.021 | 12 | 607.33 |
| E3 R01 | qwen3.8-27b | world_5 | submitted | 17.40 | 1150.915 | 29 | 311.79 |
| E3 R01 | qwen3.8-27b | world_6 | submitted | 99.30 | 1799.453 | 20 | 1177.50 |
| E3 R02 | qwen3.8-27b | world_1 | submitted | 99.65 | 302.955 | 8 | 523.25 |
| E3 R02 | qwen3.8-27b | world_2 | submitted | 93.90 | 628.726 | 17 | 499.76 |
| E3 R02 | qwen3.8-27b | world_3 | submitted | 99.20 | 874.855 | 16 | 695.56 |
| E3 R02 | qwen3.8-27b | world_4 | submitted | 32.27 | 198.235 | 8 | 342.50 |
| E3 R02 | qwen3.8-27b | world_5 | submitted | 99.30 | 2084.880 | 28 | 685.93 |
| E3 R02 | qwen3.8-27b | world_6 | incomplete | — | 1871.216 | 46 | 196.07 |
| E3 R03 | qwen3.5-122b-a10b | world_1 | submitted | 53.42 | 996.018 | 7 | 1194.57 |
| E3 R03 | qwen3.5-122b-a10b | world_2 | submitted | 25.65 | 701.483 | 5 | 1169.80 |
| E3 R03 | qwen3.5-122b-a10b | world_3 | submitted | 22.97 | 716.684 | 11 | 514.09 |
| E3 R03 | qwen3.5-122b-a10b | world_4 | submitted | 66.27 | 891.735 | 9 | 826.00 |
| E3 R03 | qwen3.5-122b-a10b | world_5 | submitted | 31.86 | 636.189 | 11 | 457.45 |
| E3 R03 | qwen3.5-122b-a10b | world_6 | submitted | 12.09 | 1565.103 | 17 | 758.00 |

17/18 次提交并完成评测；27B R02 世界 6 因累计 token 预算不足未提交。两次 27B 重复不可择优拼成一轮。

## 原始报告

- E3 R01：[报告](../v15-local-qwen38-nothink-20261107-r01/report.md) · [汇总](../v15-local-qwen38-nothink-20261107-r01/summary.json)
- E3 R02：[报告](../v15-local-qwen38-nothink-20261107-r02/report.md) · [汇总](../v15-local-qwen38-nothink-20261107-r02/summary.json)
- E3 R03：[报告](../v15-local-qwen35-122b-nothink-20261107-r01/report.md) · [汇总](../v15-local-qwen35-122b-nothink-20261107-r01/summary.json)

`source_snapshot.tar.gz` 保存服务器实际 E3 源码（不包含密钥、运行日志或虚拟环境）；对应各批次 summary 的科学核心 source_sha256 保留。

前置的云端 v15 试跑继续保留在原 experiments/v15-qwen38-* 目录，不混入上述服务器三批统计。
