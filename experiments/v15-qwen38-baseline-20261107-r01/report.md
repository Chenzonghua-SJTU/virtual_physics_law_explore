# v15 六世界自主探索 Baseline

实验：`v15-qwen38-baseline-20261107-r01`；编排状态：`interrupted`。

模型 `qwen3.8-27b`；thinking=true；无噪声；seed=42；每世界 100 能量、60 分钟；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 65536，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；分数保留本地 100 能量口径，不是比赛成绩。未完成、错误与评测失败均保留，不按零误差处理。

| 世界 | 状态 / 原因 | 模型调用 | Tokens | 能量消耗 | 总分 | 位置 RMSE | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|
| world_1 | stopped / baseline_driver_interrupted | 6 | 199403 | 9 | — | — | 811.112 |
| world_2 | submitted / submission_accepted_locally | 5 | 174178 | 14 | 99.3 | 3.85729e-08 | 392.783 |
| world_3 | stopped / baseline_driver_interrupted | 2 | 0 | 0 | — | — | 811.117 |
| world_4 | stopped / baseline_driver_interrupted | 1 | 0 | 0 | — | — | 413.316 |
| world_5 | stopped / not_started_driver_interrupted | — | — | — | — | — | 0 |
| world_6 | stopped / not_started_driver_interrupted | — | — | — | — | — | 0 |

## 逐世界记录

### world_1

运行：`v15-qwen38-baseline-20261107-r01-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=v15-qwen38-baseline-20261107-r01-world_1)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_2

运行：`v15-qwen38-baseline-20261107-r01-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=v15-qwen38-baseline-20261107-r01-world_2)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-k*q('charge')/q('mass')*x",
      "ay": "-k*q('charge')/q('mass')*y"
    },
    "fitted_parameters": {
      "k": 0.06000000005443938
    }
  },
  "claims": {
    "dynamics_order": 2,
    "hidden_matter": false,
    "time_dependence": false
  },
  "evaluation_error": null,
  "evaluation_failures": []
}
```

### world_3

运行：`v15-qwen38-baseline-20261107-r01-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=v15-qwen38-baseline-20261107-r01-world_3)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_4

运行：`v15-qwen38-baseline-20261107-r01-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=v15-qwen38-baseline-20261107-r01-world_4)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_5

运行：`v15-qwen38-baseline-20261107-r01-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=v15-qwen38-baseline-20261107-r01-world_5)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_6

运行：`v15-qwen38-baseline-20261107-r01-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=v15-qwen38-baseline-20261107-r01-world_6)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

时间戳为 UTC；完整预算、真实模型回复、实验与候选版本保存在各运行目录。
