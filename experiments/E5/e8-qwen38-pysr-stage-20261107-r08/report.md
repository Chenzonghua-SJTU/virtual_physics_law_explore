# v15 六世界自主探索 Baseline

实验：`e8-qwen38-pysr-stage-20261107-r08`；归档：E8；规则：`e4`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=开启；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 None，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 55 | 3761749 | 10918 | 198.509 | 10 | 26.9697 | 4.78541 | 249.928 | 3.36969 | 710 | 0 | 254.195 |
| world_2 | submitted / submission_accepted_locally | 11 | 237537 | 3837 | 348.818 | 10 | 94.96 | 0.0218563 | 110.028 | 1.71746 | 1107 | 0 | 112.966 |
| world_3 | submitted / submission_accepted_locally | 15 | 668038 | 7977 | 531.8 | 10 | 89.9807 | 0.0145939 | 202.554 | 2.46826 | 1769 | 0 | 207.374 |
| world_4 | submitted / submission_accepted_locally | 25 | 1360151 | 8229 | 329.16 | 10 | 27.3301 | 3.32939 | 262.667 | 3.92007 | 1161 | 0 | 267.283 |
| world_5 | submitted / submission_accepted_locally | 21 | 1062363 | 6869 | 327.095 | 8 | 25.7955 | 2.06785 | 272.673 | 2.86944 | 922 | 0 | 276.508 |
| world_6 | submitted / submission_accepted_locally | 19 | 979353 | 6142 | 323.263 | 9 | 24.6742 | 2.8053 | 243.183 | 13.2825 | 735 | 0 | 258.452 |

## 逐世界记录

### world_1

运行：`e8-qwen38-pysr-stage-20261107-r08-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r08-world_1)

```json
{
  "law": {
    "law_id": "law_5",
    "law_spec": {
      "ax": "-1 * exp(c1 + c2 * log(sqrt(x * x + y * y)) + c4 * q('mass') + c5 * q('charge')) * x",
      "ay": "-1 * exp(c1 + c2 * log(sqrt(x * x + y * y)) + c4 * q('mass') + c5 * q('charge')) * y"
    },
    "fitted_parameters": {
      "c1": -7.881489834819075,
      "c2": -9.008870257704167,
      "c4": -4.8767065630484545,
      "c5": -4.013169390395141
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

运行：`e8-qwen38-pysr-stage-20261107-r08-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r08-world_2)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "q('charge') / q('mass') * x * c1",
      "ay": "q('charge') / q('mass') * y * c1"
    },
    "fitted_parameters": {
      "c1": -0.0602418668660885
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

运行：`e8-qwen38-pysr-stage-20261107-r08-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r08-world_3)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "c1*x + c2*y",
      "ay": "c3*x + c4*y"
    },
    "fitted_parameters": {
      "c1": -0.059786525174163836,
      "c2": 0.0343164219082388,
      "c3": 0.0346856411918028,
      "c4": -0.09993151502980077
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

运行：`e8-qwen38-pysr-stage-20261107-r08-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r08-world_4)

```json
{
  "law": {
    "law_id": "law_5",
    "law_spec": {
      "ax": "-k * q('charge') * x / (x * x + y * y)",
      "ay": "-k * q('charge') * y / (x * x + y * y)"
    },
    "fitted_parameters": {
      "k": 0.1572649872303073
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

运行：`e8-qwen38-pysr-stage-20261107-r08-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r08-world_5)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "x * (-c1 * cos(y) - c2) + exp(y) * c3",
      "ay": "y * c4 / exp(vy * (x * vx + y * vy) * c5)"
    },
    "fitted_parameters": {
      "c1": 0.008993215378518155,
      "c2": 0.07092737536044802,
      "c3": -0.003988149706389451,
      "c4": -0.1152901123908342,
      "c5": -0.15699426383245596
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

运行：`e8-qwen38-pysr-stage-20261107-r08-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r08-world_6)

```json
{
  "law": {
    "law_id": "law_5",
    "law_spec": {
      "ax": "sum_b(-(x-bx)*c1/sqrt((x-bx)*(x-bx)+(y-by)*(y-by)))",
      "ay": "sum_b(-(y-by)*c1/sqrt((x-bx)*(x-bx)+(y-by)*(y-by)))"
    },
    "fitted_parameters": {
      "c1": 0.055267039733366975
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
