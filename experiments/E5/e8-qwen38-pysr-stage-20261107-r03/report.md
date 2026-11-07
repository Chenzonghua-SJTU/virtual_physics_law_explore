# v15 六世界自主探索 Baseline

实验：`e8-qwen38-pysr-stage-20261107-r03`；归档：E8；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 None，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 7 | 168785 | 2933 | 419 | 8 | 96 | 0.00149577 | 95.6411 | 3.52028 | 1087 | 0 | 101.631 |
| world_2 | submitted / submission_accepted_locally | 18 | 795538 | 6538 | 363.222 | 7 | 96.5 | 1.06291e-07 | 161.085 | 1.71793 | 1330 | 0 | 163.4 |
| world_3 | submitted / submission_accepted_locally | 20 | 836185 | 4986 | 249.3 | 7 | 15 | — | 264.853 | 20.3394 | 352 | 0 | 286.759 |
| world_4 | submitted / submission_accepted_locally | 10 | 312777 | 7269 | 726.9 | 9 | 52.2446 | 1.87585 | 170.782 | 4.07025 | 1384 | 0 | 175.438 |
| world_5 | submitted / submission_accepted_locally | 25 | 1867433 | 9311 | 372.44 | 10 | 16.5012 | 5.90593 | 269.254 | 2.61822 | 1452 | 0 | 274.598 |
| world_6 | submitted / submission_accepted_locally | 8 | 270904 | 2895 | 361.875 | 8 | 96 | 4.78061e-08 | 95.0853 | 3.51987 | 888 | 0 | 99.2074 |

## 逐世界记录

### world_1

运行：`e8-qwen38-pysr-stage-20261107-r03-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r03-world_1)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "q('charge') / q('mass') * c1 * x / (x * x + y * y)",
      "ay": "q('charge') / q('mass') * c1 * y / (x * x + y * y)"
    },
    "fitted_parameters": {
      "c1": -0.07955196857308067
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

运行：`e8-qwen38-pysr-stage-20261107-r03-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r03-world_2)

```json
{
  "law": {
    "law_id": "law_5",
    "law_spec": {
      "ax": "q('charge')/q('mass')*c1*x",
      "ay": "q('charge')/q('mass')*c1*y"
    },
    "fitted_parameters": {
      "c1": -0.0599999990187626
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

运行：`e8-qwen38-pysr-stage-20261107-r03-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r03-world_3)

```json
{
  "law": {
    "law_id": "law_7",
    "law_spec": {
      "ax": "sum_b(k1*(bx-x)*(bx-x)/sqrt((bx-x)**2+(by-y)**2)*(sqrt((bx-x)**2+(by-y)**2)**2+k2*(sqrt((bx-x)**2+(by-y)**2)**2+q('mass'))))",
      "ay": "sum_b(k1*(by-y)*(by-y)/sqrt((bx-x)**2+(by-y)**2)*(sqrt((bx-x)**2+(by-y)**2)**2+k2*(sqrt((bx-x)**2+(by-y)**2)**2+q('mass'))))"
    },
    "fitted_parameters": {
      "k1": -0.0003572514756794113,
      "k2": -0.0035084300417678495
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
      "reason": "candidate trajectory diverged"
    },
    {
      "probe_id": "v15_b0-s0_2",
      "stage": "candidate_rollout",
      "reason": "candidate trajectory diverged"
    },
    {
      "probe_id": "v15_b0-s0_3",
      "stage": "candidate_rollout",
      "reason": "candidate trajectory diverged"
    },
    {
      "probe_id": "v15_b0-s0_4",
      "stage": "candidate_rollout",
      "reason": "candidate trajectory diverged"
    },
    {
      "probe_id": "v15_b0-s1_1",
      "stage": "candidate_rollout",
      "reason": "candidate trajectory diverged"
    },
    {
      "probe_id": "v15_b0-s1_2",
      "stage": "candidate_rollout",
      "reason": "candidate trajectory diverged"
    },
    {
      "probe_id": "v15_b0-s1_3",
      "stage": "candidate_rollout",
      "reason": "candidate trajectory diverged"
    },
    {
      "probe_id": "v15_b1-s0_1",
      "stage": "candidate_rollout",
      "reason": "candidate trajectory diverged"
    },
    {
      "probe_id": "v15_b1-s0_2",
      "stage": "candidate_rollout",
      "reason": "candidate trajectory diverged"
    },
    {
      "probe_id": "v15_b1-s0_3",
      "stage": "candidate_rollout",
      "reason": "candidate trajectory diverged"
    },
    {
      "probe_id": "v15_b1-s0_4",
      "stage": "candidate_rollout",
      "reason": "candidate trajectory diverged"
    },
    {
      "probe_id": "v15_b1-s1_1",
      "stage": "candidate_rollout",
      "reason": "candidate trajectory diverged"
    },
    {
      "probe_id": "v15_b1-s1_2",
      "stage": "candidate_rollout",
      "reason": "candidate trajectory diverged"
    },
    {
      "probe_id": "v15_b1-s1_3",
      "stage": "candidate_rollout",
      "reason": "candidate trajectory diverged"
    },
    {
      "probe_id": "v15_b1-s1_4",
      "stage": "candidate_rollout",
      "reason": "candidate trajectory diverged"
    },
    {
      "probe_id": "v15_b2-s0_1",
      "stage": "candidate_rollout",
      "reason": "candidate trajectory diverged"
    },
    {
      "probe_id": "v15_b2-s0_2",
      "stage": "candidate_rollout",
      "reason": "candidate trajectory diverged"
    },
    {
      "probe_id": "v15_b2-s0_3",
      "stage": "candidate_rollout",
      "reason": "candidate trajectory diverged"
    },
    {
      "probe_id": "v15_b2-s0_4",
      "stage": "candidate_rollout",
      "reason": "candidate trajectory diverged"
    },
    {
      "probe_id": "v15_b2-s1_1",
      "stage": "candidate_rollout",
      "reason": "candidate trajectory diverged"
    },
    {
      "probe_id": "v15_b2-s1_2",
      "stage": "candidate_rollout",
      "reason": "candidate trajectory diverged"
    },
    {
      "probe_id": "v15_b2-s1_3",
      "stage": "candidate_rollout",
      "reason": "candidate trajectory diverged"
    },
    {
      "probe_id": "v15_b2-s1_4",
      "stage": "candidate_rollout",
      "reason": "candidate trajectory diverged"
    }
  ]
}
```

### world_4

运行：`e8-qwen38-pysr-stage-20261107-r03-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r03-world_4)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "q('charge') * (c1 + c2 / ((x * x + y * y + c3) / c4)) * (c5 ** sqrt(x * x + y * y) + c1) * x",
      "ay": "q('charge') * (c1 + c2 / ((x * x + y * y + c3) / c4)) * (c5 ** sqrt(x * x + y * y) + c1) * y"
    },
    "fitted_parameters": {
      "c1": 2.045073450862262e-05,
      "c2": 0.42324402303753905,
      "c3": 0.001225968120570276,
      "c4": -0.7515284324615982,
      "c5": 0.7791070579149195
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

运行：`e8-qwen38-pysr-stage-20261107-r03-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r03-world_5)

```json
{
  "law": {
    "law_id": "law_6",
    "law_spec": {
      "ax": "-c1 * x * (x * x + y * y) ** -1",
      "ay": "-c1 * y * (x * x + y * y) ** -1"
    },
    "fitted_parameters": {
      "c1": 0.2810751221658569
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

运行：`e8-qwen38-pysr-stage-20261107-r03-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r03-world_6)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-(c1 * x) + c2 * (x * sin(c3 * t + c4)) + -(c5 * (y * cos(c3 * t + c4)))",
      "ay": "-(c1 * y) + -(c5 * (y * sin(c3 * t + c4))) + -(c2 * (x * cos(c3 * t + c4)))"
    },
    "fitted_parameters": {
      "c1": 0.11999999960487365,
      "c2": 0.059999999670801156,
      "c3": 0.39269908158150163,
      "c4": 2.1707963264957395,
      "c5": 0.05999999977374322
    }
  },
  "claims": {
    "dynamics_order": 2,
    "hidden_matter": false,
    "time_dependence": true
  },
  "evaluation_error": null,
  "evaluation_failures": []
}
```

时间戳为 UTC；完整预算、真实模型回复、实验与候选版本保存在各运行目录。
