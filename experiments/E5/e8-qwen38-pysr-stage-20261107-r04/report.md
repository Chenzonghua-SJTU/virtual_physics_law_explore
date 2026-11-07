# v15 六世界自主探索 Baseline

实验：`e8-qwen38-pysr-stage-20261107-r04`；归档：E8；规则：`e4`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=开启；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 None，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 9 | 278971 | 2656 | 295.111 | 8 | 15 | — | 96.6303 | 8.07553 | 982 | 0 | 105.846 |
| world_2 | submitted / submission_accepted_locally | 13 | 311747 | 3352 | 257.846 | 10 | 91.0957 | 0.221285 | 57.7598 | 1.71733 | 1354 | 0 | 61.7565 |
| world_3 | submitted / submission_accepted_locally | 12 | 550683 | 4635 | 386.25 | 9 | 95.4687 | 0.0185725 | 136.36 | 2.46829 | 1127 | 0 | 139.892 |
| world_4 | submitted / submission_accepted_locally | 23 | 1247019 | 11914 | 518 | 10 | 15 | — | 270.149 | 5.12174 | 1513 | 0 | 277.195 |
| world_5 | submitted / submission_accepted_locally | 38 | 3200694 | 8877 | 233.605 | 10 | 15 | — | 261.848 | 13.6819 | 1166 | 0 | 277.278 |
| world_6 | submitted / submission_accepted_locally | 25 | 1737969 | 8663 | 346.52 | 10 | 17.9325 | 4.00754 | 257.945 | 3.26947 | 827 | 0 | 263.622 |

## 逐世界记录

### world_1

运行：`e8-qwen38-pysr-stage-20261107-r04-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r04-world_1)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "q('charge') / q('mass') * x * c1 / (x * x + y * y)",
      "ay": "(vx * vx + vy * vy) * c2 * (q('charge') / q('mass') * y * c3 + vx * sqrt(x * x + y * y) * sin(sqrt(x * x + y * y) * cos(y * cos(cos(q('mass') + x * y))) * cos(y + c4)) * c5)"
    },
    "fitted_parameters": {
      "c1": -0.08400997088109673,
      "c2": -0.5751936110483903,
      "c3": 0.30083457777006556,
      "c4": 2.084164385242326,
      "c5": 0.8821500834381755
    }
  },
  "claims": {
    "dynamics_order": 2,
    "hidden_matter": false,
    "time_dependence": false
  },
  "evaluation_error": null,
  "evaluation_failures": [
    {
      "probe_id": "v15_b2-s1_3",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    }
  ]
}
```

### world_2

运行：`e8-qwen38-pysr-stage-20261107-r04-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r04-world_2)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-k*q('charge')*x/q('mass')",
      "ay": "-k*q('charge')*y/q('mass')"
    },
    "fitted_parameters": {
      "k": 0.05759457794888201
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

运行：`e8-qwen38-pysr-stage-20261107-r04-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r04-world_3)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "c1 * x + c2 * y",
      "ay": "c3 * x + c4 * y"
    },
    "fitted_parameters": {
      "c1": -0.06027577992186965,
      "c2": 0.03492095623167358,
      "c3": 0.03474602962794406,
      "c4": -0.1002563942869169
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

### world_4

运行：`e8-qwen38-pysr-stage-20261107-r04-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r04-world_4)

```json
{
  "law": {
    "law_id": "law_6",
    "law_spec": {
      "ax": "sin(sin(sin(sqrt(x * x + y * y) * c1 / (x * x + y * y))) / (x * x + y * y)) * (q('charge') / q('mass')) * c2 * (c3 * t * (t - y) + x)",
      "ay": "c4 * (q('charge') / q('mass')) * y * sin(sqrt(sqrt(q('charge') / q('mass') * cos(t) + t + c5) / (q('mass') + (x * x + y * y))) / (x * x + y * y))"
    },
    "fitted_parameters": {
      "c1": 1.4696851573849188,
      "c2": -0.3202113399854931,
      "c3": -5.208355853467595e-05,
      "c4": -0.24714967923053294,
      "c5": 6.812155341276314
    }
  },
  "claims": {
    "dynamics_order": 2,
    "hidden_matter": false,
    "time_dependence": false
  },
  "evaluation_error": null,
  "evaluation_failures": [
    {
      "probe_id": "v15_b0-s1_1",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    }
  ]
}
```

### world_5

运行：`e8-qwen38-pysr-stage-20261107-r04-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r04-world_5)

```json
{
  "law": {
    "law_id": "law_4",
    "law_spec": {
      "ax": "c1 * sqrt(sqrt(x * x + y * y)) * sin(x)",
      "ay": "y * c2 + sin(cos(cos(x * x + y * y) * c3) * cos(x * sin((x * x + y * y) * cos((x * x + y * y) * y))) * c4 * y) * cos(x) * c5"
    },
    "fitted_parameters": {
      "c1": -0.07820403240914998,
      "c2": -0.12670099031844045,
      "c3": 0.1855804061269353,
      "c4": 0.8215354278458468,
      "c5": 0.03332449441790957
    }
  },
  "claims": {
    "dynamics_order": 2,
    "hidden_matter": false,
    "time_dependence": false
  },
  "evaluation_error": null,
  "evaluation_failures": [
    {
      "probe_id": "v15_b0-s0_4",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    },
    {
      "probe_id": "v15_b1-s0_2",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    },
    {
      "probe_id": "v15_b1-s0_3",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    },
    {
      "probe_id": "v15_b1-s0_4",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    },
    {
      "probe_id": "v15_b1-s1_2",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    },
    {
      "probe_id": "v15_b1-s1_3",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    },
    {
      "probe_id": "v15_b1-s1_4",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    },
    {
      "probe_id": "v15_b2-s0_1",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    },
    {
      "probe_id": "v15_b2-s0_2",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    },
    {
      "probe_id": "v15_b2-s0_3",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    },
    {
      "probe_id": "v15_b2-s0_4",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    },
    {
      "probe_id": "v15_b2-s1_1",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    },
    {
      "probe_id": "v15_b2-s1_2",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    },
    {
      "probe_id": "v15_b2-s1_3",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    },
    {
      "probe_id": "v15_b2-s1_4",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    }
  ]
}
```

### world_6

运行：`e8-qwen38-pysr-stage-20261107-r04-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r04-world_6)

```json
{
  "law": {
    "law_id": "law_7",
    "law_spec": {
      "ax": "-k * x + B * vy + a2 * sin(w * t)",
      "ay": "-k * y - B * vx + a1 * cos(w * t)"
    },
    "fitted_parameters": {
      "k": 0.10346069248598275,
      "B": 0.21813741953024418,
      "a1": 0.04964267980163514,
      "a2": -0.06319222634388832,
      "w": 0.28424739250907954
    }
  },
  "claims": {
    "dynamics_order": 2,
    "hidden_matter": true,
    "time_dependence": true
  },
  "evaluation_error": null,
  "evaluation_failures": []
}
```

时间戳为 UTC；完整预算、真实模型回复、实验与候选版本保存在各运行目录。
