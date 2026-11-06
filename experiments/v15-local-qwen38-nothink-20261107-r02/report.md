# v15 六世界自主探索 Baseline

实验：`v15-local-qwen38-nothink-20261107-r02`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；无噪声；seed=42；每世界 100 能量、60 分钟；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 65536，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；分数保留本地 100 能量口径，不是比赛成绩。未完成、错误与评测失败均保留，不按零误差处理。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。总耗时从 worker 启动至评测结束，不含排队。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 8 | 141547 | 4186 | 523.25 | 7 | 99.6499 | 0.00187757 | 302.955 |
| world_2 | submitted / submission_accepted_locally | 17 | 488604 | 8496 | 499.765 | 22 | 93.9 | 9.62854e-08 | 628.726 |
| world_3 | submitted / submission_accepted_locally | 16 | 712104 | 11129 | 695.562 | 16 | 99.2 | 2.63902e-08 | 874.855 |
| world_4 | submitted / submission_accepted_locally | 8 | 106955 | 2740 | 342.5 | 5 | 32.2685 | 3.33696 | 198.235 |
| world_5 | submitted / submission_accepted_locally | 28 | 2264766 | 19206 | 685.929 | 14 | 99.3 | 1.25944e-07 | 2084.88 |
| world_6 | incomplete / model_token_budget_exhausted | 46 | 4844656 | 9019 | 196.065 | 14 | — | — | 1871.22 |

## 逐世界记录

### world_1

运行：`v15-local-qwen38-nothink-20261107-r02-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=v15-local-qwen38-nothink-20261107-r02-world_1)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-C*q('charge')/q('mass')*x/(x**2+y**2)",
      "ay": "-C*q('charge')/q('mass')*y/(x**2+y**2)"
    },
    "fitted_parameters": {
      "C": 0.0795711532561722
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

运行：`v15-local-qwen38-nothink-20261107-r02-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=v15-local-qwen38-nothink-20261107-r02-world_2)

```json
{
  "law": {
    "law_id": "law_4",
    "law_spec": {
      "ax": "-c*x*q('charge')/q('mass')",
      "ay": "-c*y*q('charge')/q('mass')"
    },
    "fitted_parameters": {
      "c": 0.059999999138137604
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

### world_3

运行：`v15-local-qwen38-nothink-20261107-r02-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=v15-local-qwen38-nothink-20261107-r02-world_3)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "a11*x + a12*y",
      "ay": "a21*x + a22*y"
    },
    "fitted_parameters": {
      "a11": -0.059999999997706686,
      "a12": 0.034641016153514156,
      "a21": 0.03464101614761546,
      "a22": -0.10000000000376405
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

运行：`v15-local-qwen38-nothink-20261107-r02-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=v15-local-qwen38-nothink-20261107-r02-world_4)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "sum_b(G*(bx-x)/((x-bx)**2+(y-by)**2)/sqrt((x-bx)**2+(y-by)**2))",
      "ay": "sum_b(G*(by-y)/((x-bx)**2+(y-by)**2)/sqrt((x-bx)**2+(y-by)**2))"
    },
    "fitted_parameters": {
      "G": 0.22709800025902613
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

运行：`v15-local-qwen38-nothink-20261107-r02-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=v15-local-qwen38-nothink-20261107-r02-world_5)

```json
{
  "law": {
    "law_id": "law_8",
    "law_spec": {
      "ax": "-kx*x-nx*x**3-m*x*y**2",
      "ay": "-ky*y-ny*y**3-m*y*x**2"
    },
    "fitted_parameters": {
      "kx": 0.06000000061673337,
      "nx": 0.0019999998234199036,
      "ky": 0.10000000050805792,
      "ny": 0.001999999984271102,
      "m": 0.011999999314925805
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

运行：`v15-local-qwen38-nothink-20261107-r02-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=v15-local-qwen38-nothink-20261107-r02-world_6)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

时间戳为 UTC；完整预算、真实模型回复、实验与候选版本保存在各运行目录。
