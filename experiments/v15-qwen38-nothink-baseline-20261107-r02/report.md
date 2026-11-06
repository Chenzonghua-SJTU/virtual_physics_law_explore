# v15 六世界自主探索 Baseline

实验：`v15-qwen38-nothink-baseline-20261107-r02`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；无噪声；seed=42；每世界 100 能量、60 分钟；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 65536，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；分数保留本地 100 能量口径，不是比赛成绩。未完成、错误与评测失败均保留，不按零误差处理。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

| 世界 | 状态 / 原因 | 模型调用 | Tokens | 能量消耗 | 总分 | 位置 RMSE | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 12 | 241994 | 12 | 99.3998 | 0.00345018 | 156.04 |
| world_2 | submitted / submission_accepted_locally | 11 | 307843 | 15 | 99.25 | 3.96833e-08 | 196.367 |
| world_3 | incomplete / model_token_budget_exhausted | 43 | 4850752 | 22 | — | — | 522.856 |
| world_4 | submitted / submission_accepted_locally | 26 | 1285230 | 23 | 91.3312 | 0.563891 | 588.234 |
| world_5 | submitted / submission_accepted_locally | 38 | 3652265 | 6 | 31.8625 | 1.58036 | 162.553 |
| world_6 | incomplete / http_status_400 | 40 | 1693406 | 5 | — | — | 102.536 |

## 逐世界记录

### world_1

运行：`v15-qwen38-nothink-baseline-20261107-r02-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=v15-qwen38-nothink-baseline-20261107-r02-world_1)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "-k*q('charge')/q('mass')*sum_b((x-bx)/((x-bx)**2+(y-by)**2))",
      "ay": "-k*q('charge')/q('mass')*sum_b((y-by)/((x-bx)**2+(y-by)**2))"
    },
    "fitted_parameters": {
      "k": 0.07950502332802203
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

### world_2

运行：`v15-qwen38-nothink-baseline-20261107-r02-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=v15-qwen38-nothink-baseline-20261107-r02-world_2)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-A*x*q('charge')/q('mass')",
      "ay": "-A*y*q('charge')/q('mass')"
    },
    "fitted_parameters": {
      "A": 0.05999999999536216
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

运行：`v15-qwen38-nothink-baseline-20261107-r02-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=v15-qwen38-nothink-baseline-20261107-r02-world_3)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_4

运行：`v15-qwen38-nothink-baseline-20261107-r02-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=v15-qwen38-nothink-baseline-20261107-r02-world_4)

```json
{
  "law": {
    "law_id": "law_5",
    "law_spec": {
      "ax": "-q('charge')/q('mass')*C*x/(sqrt(x**2+y**2)*(sqrt(x**2+y**2)+d)**2)",
      "ay": "-q('charge')/q('mass')*C*y/(sqrt(x**2+y**2)*(sqrt(x**2+y**2)+d)**2)"
    },
    "fitted_parameters": {
      "C": 0.6725381292781443,
      "d": 0.6450282679702947
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

### world_5

运行：`v15-qwen38-nothink-baseline-20261107-r02-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=v15-qwen38-nothink-baseline-20261107-r02-world_5)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-k*x",
      "ay": "-k*y"
    },
    "fitted_parameters": {
      "k": 0.1072311097797815
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

### world_6

运行：`v15-qwen38-nothink-baseline-20261107-r02-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=v15-qwen38-nothink-baseline-20261107-r02-world_6)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

时间戳为 UTC；完整预算、真实模型回复、实验与候选版本保存在各运行目录。
