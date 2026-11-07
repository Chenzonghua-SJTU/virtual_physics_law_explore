# v15 六世界自主探索 Baseline

实验：`e8-qwen38-pysr-stage-20261107-r07`；归档：E8；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 None，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 11 | 244177 | 3641 | 331 | 6 | 53.4147 | 2.08849 | 102.845 | 3.4195 | 1007 | 0 | 107.162 |
| world_2 | submitted / submission_accepted_locally | 25 | 1278081 | 8236 | 329.44 | 10 | 90 | 5.78673e-08 | 187.368 | 1.71706 | 1408 | 0 | 191.391 |
| world_3 | submitted / submission_accepted_locally | 11 | 324641 | 2901 | 263.727 | 9 | 95.5 | 2.7014e-08 | 92.518 | 2.56854 | 620 | 0 | 96.7286 |
| world_4 | submitted / submission_accepted_locally | 12 | 345009 | 7439 | 619.917 | 6 | 34.5084 | 2.63445 | 163.581 | 4.12057 | 2166 | 0 | 169.64 |
| world_5 | submitted / submission_accepted_locally | 16 | 582153 | 4073 | 254.562 | 10 | 95 | 9.64872e-08 | 115.414 | 2.8689 | 1033 | 0 | 120.622 |
| world_6 | submitted / submission_accepted_locally | 16 | 655593 | 7428 | 464.25 | 8 | 91 | 5.72143e-08 | 212.25 | 3.51948 | 1734 | 0 | 217.105 |

## 逐世界记录

### world_1

运行：`e8-qwen38-pysr-stage-20261107-r07-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r07-world_1)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-k / (x * x + y * y) * x",
      "ay": "-k / (x * x + y * y) * y"
    },
    "fitted_parameters": {
      "k": 0.0795533083191998
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

运行：`e8-qwen38-pysr-stage-20261107-r07-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r07-world_2)

```json
{
  "law": {
    "law_id": "law_7",
    "law_spec": {
      "ax": "-k*(q('charge')/q('mass'))*x",
      "ay": "-k*(q('charge')/q('mass'))*y"
    },
    "fitted_parameters": {
      "k": 0.059999999634304496
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

运行：`e8-qwen38-pysr-stage-20261107-r07-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r07-world_3)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "c1 * x + c2 * y",
      "ay": "c3 * x + c4 * y"
    },
    "fitted_parameters": {
      "c1": -0.059999999996288626,
      "c2": 0.034641016137143835,
      "c3": 0.034641016145226626,
      "c4": -0.09999999997494528
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

运行：`e8-qwen38-pysr-stage-20261107-r07-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r07-world_4)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-1 * exp(c1 + c2 * sqrt(x * x + y * y) + c3 * log(sqrt(x * x + y * y)) + c4 * log(q('mass'))) * x",
      "ay": "-1 * exp(c1 + c2 * sqrt(x * x + y * y) + c3 * log(sqrt(x * x + y * y)) + c4 * log(q('mass'))) * y"
    },
    "fitted_parameters": {
      "c1": -1.1455109689354064,
      "c2": -0.2502568397346378,
      "c3": -1.9988082571581351,
      "c4": -0.9999998860863555
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

### world_5

运行：`e8-qwen38-pysr-stage-20261107-r07-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r07-world_5)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "c1 * x + c2 * x ** 3 + c3 * (x * y ** 2)",
      "ay": "c4 * y + c3 * (x ** 2 * y) + c5 * y ** 3"
    },
    "fitted_parameters": {
      "c1": -0.06000000003878042,
      "c2": -0.0019999999468482362,
      "c3": -0.011999999468619467,
      "c4": -0.10000000003546562,
      "c5": -0.0019999999471456294
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

运行：`e8-qwen38-pysr-stage-20261107-r07-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r07-world_6)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-(c1 * x) + c2 * y + c3 * (x * sin(c4 * t + c5)) - (c3 * (y * cos(c4 * t + c5)))",
      "ay": "-(c1 * y) - (c3 * (y * sin(c4 * t + c5))) - (c3 * (x * cos(c4 * t + c5)))"
    },
    "fitted_parameters": {
      "c1": 0.11999999957678528,
      "c2": -4.6151591384337406e-10,
      "c3": 0.059999999716414586,
      "c4": 0.3926990811203055,
      "c5": 2.1707963289969343
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
