# v15 六世界自主探索 Baseline

实验：`e5-qwen38-budget-tools-20261107-r08`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 9 | 216864 | 4487 | 498.556 | 6 | 96.9995 | 0.00514401 | 79.2336 | 3.57 | 1530 | 0 | 86.0862 |
| world_2 | submitted / submission_accepted_locally | 7 | 128487 | 3465 | 495 | 6 | 97 | 1.04467e-07 | 60.6174 | 1.71726 | 1468 | 0 | 65.7485 |
| world_3 | submitted / submission_accepted_locally | 5 | 113187 | 3050 | 610 | 3 | 98.5 | 2.62649e-08 | 53.5686 | 2.46847 | 1628 | 0 | 60.6799 |
| world_4 | incomplete / wall_time_exhausted | 103 | 4005902 | 16440 | — | 10 | — | — | 295.367 | — | 212 | 0 | 300.544 |
| world_5 | incomplete / wall_time_exhausted | 65 | 2625088 | 16458 | — | 10 | — | — | 295.438 | — | 302 | 0 | 296.126 |
| world_6 | submitted / submission_accepted_locally | 9 | 254973 | 2289 | 254.333 | 9 | 10 | — | 75.849 | 89.0213 | 646 | 0 | 168.408 |

## 逐世界记录

### world_1

运行：`e5-qwen38-budget-tools-20261107-r08-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-budget-tools-20261107-r08-world_1)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "-K * q('charge') / q('mass') * x / (x*x + y*y)",
      "ay": "-K * q('charge') / q('mass') * y / (x*x + y*y)"
    },
    "fitted_parameters": {
      "K": 0.07947682941799486
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

运行：`e5-qwen38-budget-tools-20261107-r08-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-budget-tools-20261107-r08-world_2)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-k*q('charge')/q('mass')*x",
      "ay": "-k*q('charge')/q('mass')*y"
    },
    "fitted_parameters": {
      "k": 0.05999999904038369
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

运行：`e5-qwen38-budget-tools-20261107-r08-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-budget-tools-20261107-r08-world_3)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "a10*x + a11*y",
      "ay": "a20*x + a21*y"
    },
    "fitted_parameters": {
      "a10": -0.06000000000236479,
      "a11": 0.034641016157261506,
      "a20": 0.03464101615527574,
      "a21": -0.1000000000103502
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

运行：`e5-qwen38-budget-tools-20261107-r08-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-budget-tools-20261107-r08-world_4)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_5

运行：`e5-qwen38-budget-tools-20261107-r08-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-budget-tools-20261107-r08-world_5)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_6

运行：`e5-qwen38-budget-tools-20261107-r08-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-budget-tools-20261107-r08-world_6)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "sum_b(GM*((bx-x)/( ( (bx-x)*(bx-x)+(by-y)*(by-y) ) *sqrt( ( (bx-x)*(bx-x)+(by-y)*(by-y) ) ))) )",
      "ay": "sum_b(GM*((by-y)/( ( (bx-x)*(bx-x)+(by-y)*(by-y) ) *sqrt( ( (bx-x)*(bx-x)+(by-y)*(by-y) ) ))) )"
    },
    "fitted_parameters": {
      "GM": 0.9957586198987582
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
      "probe_id": "v15_b0-s0_1",
      "stage": "candidate_rollout",
      "reason": "numerical wall-time budget exhausted"
    },
    {
      "probe_id": "v15_b0-s0_2",
      "stage": "candidate_rollout",
      "reason": "numerical wall-time budget exhausted"
    },
    {
      "probe_id": "v15_b0-s0_3",
      "stage": "candidate_rollout",
      "reason": "numerical wall-time budget exhausted"
    },
    {
      "probe_id": "v15_b0-s0_4",
      "stage": "candidate_rollout",
      "reason": "numerical wall-time budget exhausted"
    },
    {
      "probe_id": "v15_b0-s1_1",
      "stage": "candidate_rollout",
      "reason": "numerical wall-time budget exhausted"
    },
    {
      "probe_id": "v15_b0-s1_3",
      "stage": "candidate_rollout",
      "reason": "numerical wall-time budget exhausted"
    },
    {
      "probe_id": "v15_b0-s2_1",
      "stage": "candidate_rollout",
      "reason": "numerical wall-time budget exhausted"
    },
    {
      "probe_id": "v15_b0-s3_1",
      "stage": "candidate_rollout",
      "reason": "numerical wall-time budget exhausted"
    },
    {
      "probe_id": "v15_b0-s3_3",
      "stage": "candidate_rollout",
      "reason": "numerical wall-time budget exhausted"
    },
    {
      "probe_id": "v15_b1-s0_3",
      "stage": "candidate_rollout",
      "reason": "numerical wall-time budget exhausted"
    },
    {
      "probe_id": "v15_b1-s0_4",
      "stage": "candidate_rollout",
      "reason": "numerical wall-time budget exhausted"
    },
    {
      "probe_id": "v15_b1-s2_1",
      "stage": "candidate_rollout",
      "reason": "numerical wall-time budget exhausted"
    },
    {
      "probe_id": "v15_b1-s2_3",
      "stage": "candidate_rollout",
      "reason": "numerical wall-time budget exhausted"
    },
    {
      "probe_id": "v15_b1-s3_1",
      "stage": "candidate_rollout",
      "reason": "numerical wall-time budget exhausted"
    }
  ]
}
```

时间戳为 UTC；完整预算、真实模型回复、实验与候选版本保存在各运行目录。
