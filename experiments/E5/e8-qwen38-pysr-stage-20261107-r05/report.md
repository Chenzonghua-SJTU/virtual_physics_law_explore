# v15 六世界自主探索 Baseline

实验：`e8-qwen38-pysr-stage-20261107-r05`；归档：E8；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 None，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 8 | 164335 | 3561 | 445.125 | 8 | 95.9999 | 0.0017799 | 103.954 | 3.52001 | 988 | 0 | 109.11 |
| world_2 | submitted / submission_accepted_locally | 11 | 229815 | 7047 | 640.636 | 7 | 96.5 | 7.27448e-08 | 112.826 | 1.71735 | 1699 | 0 | 115.388 |
| world_3 | submitted / submission_accepted_locally | 8 | 232162 | 5415 | 676.875 | 7 | 91.5 | 3.30068e-08 | 132.006 | 2.46849 | 1482 | 0 | 136.343 |
| world_4 | submitted / submission_accepted_locally | 8 | 177359 | 2971 | 371.375 | 6 | 91.51 | 0.475239 | 98.0847 | 4.12011 | 994 | 0 | 102.842 |
| world_5 | submitted / submission_accepted_locally | 7 | 193556 | 4574 | 653.429 | 6 | 97 | 1.55999e-08 | 119.962 | 2.81875 | 1784 | 0 | 124.074 |
| world_6 | submitted / submission_accepted_locally | 67 | 7888165 | 10213 | 152.433 | 9 | 10 | 21512.2 | 282.27 | 3.32007 | 1501 | 0 | 287.788 |

## 逐世界记录

### world_1

运行：`e8-qwen38-pysr-stage-20261107-r05-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r05-world_1)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-c1 * q('charge') / q('mass') * x / (x * x + y * y)",
      "ay": "-c1 * q('charge') / q('mass') * y / (x * x + y * y)"
    },
    "fitted_parameters": {
      "c1": 0.07956851540751546
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

运行：`e8-qwen38-pysr-stage-20261107-r05-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r05-world_2)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-k*q('charge')/q('mass')*x",
      "ay": "-k*q('charge')/q('mass')*y"
    },
    "fitted_parameters": {
      "k": 0.05999999943061308
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

运行：`e8-qwen38-pysr-stage-20261107-r05-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r05-world_3)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "c1 * x + c2 * y",
      "ay": "c3 * x + c4 * y"
    },
    "fitted_parameters": {
      "c1": -0.05999999993623082,
      "c2": 0.03464101602717061,
      "c3": 0.03464101604646358,
      "c4": -0.09999999978068388
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

运行：`e8-qwen38-pysr-stage-20261107-r05-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r05-world_4)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "q('charge') / q('mass') * (c1 - c2 / (x * x + y * y) + c3 / sqrt(x * x + y * y)) * x",
      "ay": "q('charge') / q('mass') * (c1 - c4 / (x * x + y * y) + c5 / sqrt(x * x + y * y)) * y"
    },
    "fitted_parameters": {
      "c1": -0.0051437701208009,
      "c2": 0.310047296886404,
      "c3": 0.0688212682375928,
      "c4": 0.3100932177253906,
      "c5": 0.06883158208615718
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

运行：`e8-qwen38-pysr-stage-20261107-r05-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r05-world_5)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "c1 * x + c2 * x ** 3 + c3 * (x * y ** 2)",
      "ay": "c4 * y + c3 * (x ** 2 * y) + c5 * y ** 3"
    },
    "fitted_parameters": {
      "c1": -0.059999999785441,
      "c2": -0.002000000022342662,
      "c3": -0.012000000098248378,
      "c4": -0.09999999972117023,
      "c5": -0.0020000000593617217
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

运行：`e8-qwen38-pysr-stage-20261107-r05-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r05-world_6)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "c1 * x + c2 * y",
      "ay": "c3 * x + c4 * y + c5 * t * y"
    },
    "fitted_parameters": {
      "c1": -0.12375398953854819,
      "c2": 0.04757875222956939,
      "c3": 0.05627277630813739,
      "c4": -0.1627912737994013,
      "c5": 0.017472906465893917
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
