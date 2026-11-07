# v15 六世界自主探索 Baseline

实验：`e7-qwen38-pysr-on-20261107-r02`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 None，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 14 | 397017 | 4560 | 325.714 | 7 | 30.3888 | 4.11304 | 96.1723 | 3.67683 | 918 | 0 | 102.663 |
| world_2 | submitted / submission_accepted_locally | 19 | 454460 | 5578 | 293.579 | 7 | 15.9117 | 9.09868 | 131.899 | 2.77037 | 1144 | 0 | 136.151 |
| world_3 | submitted / submission_accepted_locally | 14 | 586073 | 7182 | 513 | 8 | 96 | 2.48966e-08 | 207.111 | 2.56869 | 2051 | 0 | 210.584 |
| world_4 | submitted / submission_accepted_locally | 18 | 700957 | 8086 | 449.222 | 10 | 25.2945 | 4.55581 | 174.852 | 4.72645 | 1396 | 0 | 180.731 |
| world_5 | submitted / submission_accepted_locally | 23 | 1380267 | 5396 | 234.609 | 8 | 10 | — | 262.663 | 29.0507 | 948 | 0 | 293.974 |
| world_6 | submitted / submission_accepted_locally | 16 | 748403 | 6242 | 390.125 | 10 | 21.0926 | 4.63079 | 146.211 | 3.41919 | 1226 | 0 | 152.39 |

## 逐世界记录

### world_1

运行：`e7-qwen38-pysr-on-20261107-r02-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e7-qwen38-pysr-on-20261107-r02-world_1)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "sum_b(-k*x/((x-bx)**2+(y-by)**2)/sqrt((x-bx)**2+(y-by)**2))",
      "ay": "sum_b(-k*y/((x-bx)**2+(y-by)**2)/sqrt((x-bx)**2+(y-by)**2))"
    },
    "fitted_parameters": {
      "k": 0.04934802124529271
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

运行：`e7-qwen38-pysr-on-20261107-r02-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e7-qwen38-pysr-on-20261107-r02-world_2)

```json
{
  "law": {
    "law_id": "law_4",
    "law_spec": {
      "ax": "sum_b(G*(bx-x)/(sqrt((bx-x)**2+(by-y)**2)*((bx-x)**2+(by-y)**2)*q('mass')))",
      "ay": "sum_b(G*(by-y)/(sqrt((bx-x)**2+(by-y)**2)*((bx-x)**2+(by-y)**2)*q('mass')))*q('charge')"
    },
    "fitted_parameters": {
      "G": 0.1762830600796748
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

运行：`e7-qwen38-pysr-on-20261107-r02-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e7-qwen38-pysr-on-20261107-r02-world_3)

```json
{
  "law": {
    "law_id": "law_4",
    "law_spec": {
      "ax": "k1*x + k2*y",
      "ay": "k2*x + k3*y"
    },
    "fitted_parameters": {
      "k1": -0.06000000003823096,
      "k2": 0.03464101621720519,
      "k3": -0.10000000011523473
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

运行：`e7-qwen38-pysr-on-20261107-r02-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e7-qwen38-pysr-on-20261107-r02-world_4)

```json
{
  "law": {
    "law_id": "law_5",
    "law_spec": {
      "ax": "-G*sum_b((x-bx)/((x-bx)**2+(y-by)**2+H**2)*q('charge')**2/q('mass'))",
      "ay": "-G*sum_b((y-by)/((x-bx)**2+(y-by)**2+H**2)*q('charge')**2/q('mass'))"
    },
    "fitted_parameters": {
      "G": 0.23347045377181222,
      "H": 3.252182990315292e-07
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

运行：`e7-qwen38-pysr-on-20261107-r02-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e7-qwen38-pysr-on-20261107-r02-world_5)

```json
{
  "law": {
    "law_id": "law_10",
    "law_spec": {
      "ax": "sum_b(k*(bx-x)/(abs(bx-x)*abs(bx-x)+abs(by-y)*abs(by-y)))",
      "ay": "sum_b(k*(by-y)/(abs(bx-x)*abs(bx-x)+abs(by-y)*abs(by-y)))"
    },
    "fitted_parameters": {
      "k": 0.19992380340513755
    }
  },
  "claims": {
    "dynamics_order": 2,
    "hidden_matter": false,
    "time_dependence": true
  },
  "evaluation_error": null,
  "evaluation_failures": [
    {
      "probe_id": "v15_b0-s1_3",
      "stage": "candidate_rollout",
      "reason": "integration exceeded derivative-evaluation limit"
    }
  ]
}
```

### world_6

运行：`e7-qwen38-pysr-on-20261107-r02-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e7-qwen38-pysr-on-20261107-r02-world_6)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "(p1+p2*t)*x",
      "ay": "(p3+p4*t)*y"
    },
    "fitted_parameters": {
      "p1": -0.07770686618201472,
      "p2": -0.012413095424915643,
      "p3": -0.15924762786750815,
      "p4": -0.012582190448265643
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
