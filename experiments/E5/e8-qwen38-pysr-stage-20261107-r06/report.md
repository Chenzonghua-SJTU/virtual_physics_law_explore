# v15 六世界自主探索 Baseline

实验：`e8-qwen38-pysr-stage-20261107-r06`；归档：E8；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 None，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 15 | 466560 | 4867 | 324.467 | 6 | 97 | 0.00149371 | 126.446 | 3.52028 | 1384 | 0 | 131.782 |
| world_2 | submitted / submission_accepted_locally | 14 | 403944 | 4910 | 350.714 | 8 | 96 | 9.50979e-08 | 125.345 | 1.71739 | 1144 | 0 | 129.694 |
| world_3 | submitted / submission_accepted_locally | 8 | 232400 | 2389 | 298.625 | 10 | 90 | 2.98893e-08 | 86.0919 | 2.51864 | 1107 | 0 | 90.0752 |
| world_4 | submitted / submission_accepted_locally | 12 | 343597 | 7764 | 647 | 8 | 87.5693 | 0.6009 | 170.351 | 4.12046 | 3098 | 0 | 176.548 |
| world_5 | submitted / submission_accepted_locally | 32 | 2523691 | 10823 | 338.219 | 10 | 37.9686 | 1.28695 | 261.903 | 2.86901 | 1081 | 0 | 266.888 |
| world_6 | submitted / submission_accepted_locally | 18 | 815678 | 6051 | 336.167 | 10 | 95 | 3.18453e-08 | 229.651 | 3.51998 | 1537 | 0 | 234.214 |

## 逐世界记录

### world_1

运行：`e8-qwen38-pysr-stage-20261107-r06-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r06-world_1)

```json
{
  "law": {
    "law_id": "law_4",
    "law_spec": {
      "ax": "-c1 * q('charge') / q('mass') * x / (x * x + y * y)",
      "ay": "-c1 * q('charge') / q('mass') * y / (x * x + y * y)"
    },
    "fitted_parameters": {
      "c1": 0.07955262769073175
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

运行：`e8-qwen38-pysr-stage-20261107-r06-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r06-world_2)

```json
{
  "law": {
    "law_id": "law_5",
    "law_spec": {
      "ax": "q('charge')/q('mass')*c1*x",
      "ay": "q('charge')/q('mass')*c2*y"
    },
    "fitted_parameters": {
      "c1": -0.059999998879852245,
      "c2": -0.059999999590853094
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

运行：`e8-qwen38-pysr-stage-20261107-r06-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r06-world_3)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "c1 * x + c2 * y",
      "ay": "c3 * x + c4 * y"
    },
    "fitted_parameters": {
      "c1": -0.06000000004176067,
      "c2": 0.03464101608223756,
      "c3": 0.03464101622667955,
      "c4": -0.09999999988692432
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

运行：`e8-qwen38-pysr-stage-20261107-r06-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r06-world_4)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-1 * exp(c1 + c2 * sqrt(x * x + y * y) + c3 * log(sqrt(x * x + y * y)) + c4 * q('mass') + c5 * log(q('charge'))) * x",
      "ay": "-1 * exp(c1 + c2 * sqrt(x * x + y * y) + c3 * log(sqrt(x * x + y * y)) + c4 * q('mass') + c5 * log(q('charge'))) * y"
    },
    "fitted_parameters": {
      "c1": -0.45235408403441707,
      "c2": -0.2503055000421901,
      "c3": -1.9986852716207855,
      "c4": -0.6931459704431334,
      "c5": 0.9999989432853983
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

运行：`e8-qwen38-pysr-stage-20261107-r06-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r06-world_5)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "(x + sin(sin(x) * c1)) * (exp(sqrt(x * x + y * y)) * c2 - c3)",
      "ay": "c4 * vy + c5 * y"
    },
    "fitted_parameters": {
      "c1": 1.8049417136146648,
      "c2": -0.0020644238888219086,
      "c3": 0.030054240740276086,
      "c4": -0.004833673130320203,
      "c5": -0.1174400862901977
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

运行：`e8-qwen38-pysr-stage-20261107-r06-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r06-world_6)

```json
{
  "law": {
    "law_id": "law_6",
    "law_spec": {
      "ax": "-(c1 * x) + c2 * (y * sin(c3 * t + c4)) + c2 * (x * cos(c3 * t + c4))",
      "ay": "-(c5 * x) + -(c1 * y) + c2 * (x * sin(c3 * t + c4)) + -(c2 * (y * cos(c3 * t + c4)))"
    },
    "fitted_parameters": {
      "c1": 0.12000000010050967,
      "c2": 0.06000000014947808,
      "c3": 0.39269908163929973,
      "c4": 0.5999999990502488,
      "c5": 8.242753180648067e-11
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
