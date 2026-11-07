# v15 六世界自主探索 Baseline

实验：`e6-qwen38-recovery-concise-20261107-r02`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 None，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 16 | 363403 | 5788 | 361.75 | 5 | 63.4775 | 1.72672 | 97.4193 | 4.02038 | 1154 | 0 | 105.523 |
| world_2 | submitted / submission_accepted_locally | 26 | 1026195 | 12362 | 475.462 | 6 | 15 | — | 209.912 | 10.0298 | 1766 | 0 | 222.006 |
| world_3 | submitted / submission_accepted_locally | 10 | 359720 | 5587 | 558.7 | 10 | 90 | 2.64959e-08 | 119.821 | 2.51958 | 1188 | 0 | 126.73 |
| world_4 | submitted / submission_accepted_locally | 16 | 536100 | 10503 | 656.438 | 10 | 15 | — | 173.647 | 4.19268 | 2329 | 0 | 183.103 |
| world_5 | submitted / submission_accepted_locally | 17 | 787397 | 11011 | 647.706 | 8 | 27.034 | 1.94094 | 242.681 | 2.66859 | 1500 | 0 | 250.33 |
| world_6 | submitted / submission_accepted_locally | 18 | 1094385 | 8921 | 495.611 | 6 | 26.4909 | 2.60921 | 239.145 | 11.1294 | 3132 | 0 | 252.102 |

## 逐世界记录

### world_1

运行：`e6-qwen38-recovery-concise-20261107-r02-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-recovery-concise-20261107-r02-world_1)

```json
{
  "law": {
    "law_id": "law_6",
    "law_spec": {
      "ax": "sum_b(-G*(q('charge')/q('mass'))*(x-bx)/sqrt((x-bx)**2+(y-by)**2)/((x-bx)**2+(y-by)**2))",
      "ay": "sum_b(-G*(q('charge')/q('mass'))*(y-by)/sqrt((x-bx)**2+(y-by)**2)/((x-bx)**2+(y-by)**2))"
    },
    "fitted_parameters": {
      "G": 0.22348874268836502
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

运行：`e6-qwen38-recovery-concise-20261107-r02-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-recovery-concise-20261107-r02-world_2)

```json
{
  "law": {
    "law_id": "law_6",
    "law_spec": {
      "ax": "-p1*x/((x*x+y*y)*sqrt(x*x+y*y))+a*vx+b*vy",
      "ay": "-p1*y/((x*x+y*y)*sqrt(x*x+y*y))+c*vx+d*vy"
    },
    "fitted_parameters": {
      "p1": 0.4183701845439802,
      "a": -0.1578842577926926,
      "b": -0.2874348785427238,
      "c": 0.07439893933784769,
      "d": -0.013835954637938762
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
      "reason": "integration exceeded derivative-evaluation limit"
    },
    {
      "probe_id": "v15_b0-s0_2",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    },
    {
      "probe_id": "v15_b0-s0_3",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    },
    {
      "probe_id": "v15_b0-s0_4",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    },
    {
      "probe_id": "v15_b0-s1_1",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    },
    {
      "probe_id": "v15_b0-s1_2",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    },
    {
      "probe_id": "v15_b0-s1_3",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    },
    {
      "probe_id": "v15_b0-s1_4",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    },
    {
      "probe_id": "v15_b1-s0_2",
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
    }
  ]
}
```

### world_3

运行：`e6-qwen38-recovery-concise-20261107-r02-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-recovery-concise-20261107-r02-world_3)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "a11*x+a12*y",
      "ay": "a21*x+a22*y"
    },
    "fitted_parameters": {
      "a11": -0.05999999998955766,
      "a12": 0.03464101615040686,
      "a21": 0.034641016134225544,
      "a22": -0.09999999999822845
    }
  },
  "claims": {
    "dynamics_order": 2,
    "hidden_matter": true,
    "time_dependence": false
  },
  "evaluation_error": null,
  "evaluation_failures": []
}
```

### world_4

运行：`e6-qwen38-recovery-concise-20261107-r02-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-recovery-concise-20261107-r02-world_4)

```json
{
  "law": {
    "law_id": "law_4",
    "law_spec": {
      "ax": "-k*x/(x**2+y**2+c)",
      "ay": "-k*y/(x**2+y**2+c)"
    },
    "fitted_parameters": {
      "k": 0.13989424921706278,
      "c": -0.9101117225374225
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
      "reason": "integration failed: Required step size is less than spacing between numbers."
    },
    {
      "probe_id": "v15_b0-s0_2",
      "stage": "candidate_rollout",
      "reason": "integration failed: Required step size is less than spacing between numbers."
    },
    {
      "probe_id": "v15_b0-s1_1",
      "stage": "candidate_rollout",
      "reason": "integration failed: Required step size is less than spacing between numbers."
    },
    {
      "probe_id": "v15_b0-s1_2",
      "stage": "candidate_rollout",
      "reason": "non-finite or excessive intermediate expression value"
    }
  ]
}
```

### world_5

运行：`e6-qwen38-recovery-concise-20261107-r02-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-recovery-concise-20261107-r02-world_5)

```json
{
  "law": {
    "law_id": "law_7",
    "law_spec": {
      "ax": "-k*x*exp(g*log(x*x+y*y))",
      "ay": "-k*y*exp(g*log(x*x+y*y))"
    },
    "fitted_parameters": {
      "k": 0.07227360964518784,
      "g": 0.09046483382039275
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

运行：`e6-qwen38-recovery-concise-20261107-r02-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-recovery-concise-20261107-r02-world_6)

```json
{
  "law": {
    "law_id": "law_8",
    "law_spec": {
      "ax": "sum_b(G*(bx-x)/sqrt((x-bx)**2+(y-by)**2))",
      "ay": "sum_b(G*(by-y)/sqrt((x-bx)**2+(y-by)**2))"
    },
    "fitted_parameters": {
      "G": 0.04131017739133858
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

时间戳为 UTC；完整预算、真实模型回复、实验与候选版本保存在各运行目录。
