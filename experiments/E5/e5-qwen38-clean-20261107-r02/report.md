# v15 六世界自主探索 Baseline

实验：`e5-qwen38-clean-20261107-r02`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 12 | 228173 | 4338 | 361.5 | 4 | 98 | 0.00149798 | 73.8434 | 3.67038 | 2118 | 0 | 80.9616 |
| world_2 | submitted / submission_accepted_locally | 5 | 72534 | 1469 | 293.8 | 6 | 25.6511 | 2.49277 | 25.3884 | 1.76786 | 741 | 0 | 30.2684 |
| world_3 | submitted / submission_accepted_locally | 19 | 722333 | 8547 | 449.842 | 5 | 10.3488 | 14.1909 | 180.64 | 2.5194 | 4096 | 0 | 188.367 |
| world_4 | submitted / submission_accepted_locally | 10 | 203683 | 8859 | 885.9 | 7 | 96.4979 | 0.00900077 | 147.193 | 4.22077 | 1925 | 0 | 152.42 |
| world_5 | submitted / submission_accepted_locally | 19 | 849178 | 9206 | 484.526 | 7 | 27.0425 | 1.94014 | 228.341 | 2.59492 | 2959 | 0 | 235.529 |
| world_6 | submitted / submission_accepted_locally | 24 | 1807233 | 7430 | 309.583 | 7 | 21.6386 | 3.22231 | 197.126 | 3.2697 | 995 | 0 | 205.484 |

## 逐世界记录

### world_1

运行：`e5-qwen38-clean-20261107-r02-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-clean-20261107-r02-world_1)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "sum_b(-k*q('charge')/q('mass')*(x-bx)/((x-bx)*(x-bx)+(y-by)*(y-by)))",
      "ay": "sum_b(-k*q('charge')/q('mass')*(y-by)/((x-bx)*(x-bx)+(y-by)*(y-by)))"
    },
    "fitted_parameters": {
      "k": 0.07955536306169467
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

运行：`e5-qwen38-clean-20261107-r02-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-clean-20261107-r02-world_2)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-a1*x + a2*vx",
      "ay": "-a1*y + a2*vy"
    },
    "fitted_parameters": {
      "a1": 0.05999999999659403,
      "a2": -3.2211275632621765e-13
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

运行：`e5-qwen38-clean-20261107-r02-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-clean-20261107-r02-world_3)

```json
{
  "law": {
    "law_id": "law_5",
    "law_spec": {
      "ax": "a1*t+a2*x+a3*y+a4*vx",
      "ay": "a1*t+a2*x+a3*y+a4*vy"
    },
    "fitted_parameters": {
      "a1": -0.002110583481627881,
      "a2": -0.020621389621661483,
      "a3": -0.04563312868126065,
      "a4": 0.07855571213989404
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

### world_4

运行：`e5-qwen38-clean-20261107-r02-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-clean-20261107-r02-world_4)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-kx*q('charge')/q('mass')*x/(x**2+y**2)*exp(-s*sqrt(x**2+y**2))",
      "ay": "-ky*q('charge')/q('mass')*y/(x**2+y**2)*exp(-s*sqrt(x**2+y**2))"
    },
    "fitted_parameters": {
      "kx": 0.31805453604098477,
      "ky": 0.31804870061280166,
      "s": 0.24983891225624344
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

运行：`e5-qwen38-clean-20261107-r02-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-clean-20261107-r02-world_5)

```json
{
  "law": {
    "law_id": "law_7",
    "law_spec": {
      "ax": "-cx*x",
      "ay": "-cy*y"
    },
    "fitted_parameters": {
      "cx": 0.07226313368800964,
      "cy": 0.11423095350395944
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

运行：`e5-qwen38-clean-20261107-r02-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-clean-20261107-r02-world_6)

```json
{
  "law": {
    "law_id": "law_6",
    "law_spec": {
      "ax": "a1*x + a2*y - a5*vx",
      "ay": "a3*x + a4*y - a5*vy"
    },
    "fitted_parameters": {
      "a1": -0.10645430681855256,
      "a2": 0.012486521638686623,
      "a3": 0.050264074766866264,
      "a4": -0.11015662919326916,
      "a5": 0.02651941220717336
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
