# v15 六世界自主探索 Baseline

实验：`e5-qwen35-122b-hs-20261107-r14`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.5-122b-a10b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 7 | 149254 | 6130 | 875.714 | 4 | 98 | 0.00149297 | 66.6984 | 3.51935 | 1733 | 0 | 75.3024 |
| world_2 | submitted / submission_accepted_locally | 7 | 140184 | 4711 | 673 | 8 | 96 | 5.37918e-08 | 49.4478 | 1.71724 | 1002 | 0 | 55.3673 |
| world_3 | submitted / submission_accepted_locally | 5 | 123983 | 4314 | 862.8 | 2 | 99 | 2.62649e-08 | 42.0951 | 2.4684 | 1608 | 0 | 45.4346 |
| world_4 | submitted / submission_accepted_locally | 8 | 181529 | 8265 | 1033.12 | 4 | 50.7487 | 1.9479 | 83.0095 | 4.1204 | 2145 | 0 | 91.0762 |
| world_5 | submitted / submission_accepted_locally | 15 | 649078 | 14830 | 988.667 | 2 | 25.1767 | 2.13929 | 179.975 | 2.61927 | 4096 | 0 | 187.844 |
| world_6 | submitted / submission_accepted_locally | 10 | 389034 | 10298 | 1029.8 | 3 | 15.659 | 4.819 | 117.4 | 3.56978 | 1834 | 0 | 122.405 |

## 逐世界记录

### world_1

运行：`e5-qwen35-122b-hs-20261107-r14-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen35-122b-hs-20261107-r14-world_1)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "k * q('charge') / q('mass') * x / (x**2 + y**2)",
      "ay": "k * q('charge') / q('mass') * y / (x**2 + y**2)"
    },
    "fitted_parameters": {
      "k": -0.07955309915173811
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

运行：`e5-qwen35-122b-hs-20261107-r14-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen35-122b-hs-20261107-r14-world_2)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-K * q('charge') / q('mass') * x",
      "ay": "-K * q('charge') / q('mass') * y"
    },
    "fitted_parameters": {
      "K": 0.05999999969609484
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

运行：`e5-qwen35-122b-hs-20261107-r14-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen35-122b-hs-20261107-r14-world_3)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "c1*x + c2*y",
      "ay": "c3*x + c4*y"
    },
    "fitted_parameters": {
      "c1": -0.06000000000236601,
      "c2": 0.03464101615726214,
      "c3": 0.03464101615527179,
      "c4": -0.10000000001034916
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

运行：`e5-qwen35-122b-hs-20261107-r14-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen35-122b-hs-20261107-r14-world_4)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "c0 * q('charge')**cq * x * (x**2 + y**2)**c1",
      "ay": "c0 * q('charge')**cq * y * (x**2 + y**2)**c1"
    },
    "fitted_parameters": {
      "c0": -0.32790089444126547,
      "c1": -1.3823236977295907,
      "cq": 1.0867173981198148
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

运行：`e5-qwen35-122b-hs-20261107-r14-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen35-122b-hs-20261107-r14-world_5)

```json
{
  "law": {
    "law_id": "law_4",
    "law_spec": {
      "ax": "c0 + c1*x + c2*y",
      "ay": "c3 + c4*x + c1*y"
    },
    "fitted_parameters": {
      "c0": 0.11891290675785428,
      "c1": -0.14052687750907403,
      "c2": -0.037858007275122584,
      "c3": 0.06441772592082286,
      "c4": -0.045303845837186524
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

运行：`e5-qwen35-122b-hs-20261107-r14-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen35-122b-hs-20261107-r14-world_6)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "k * x * (x*x + y*y) ** p",
      "ay": "k * y * (x*x + y*y) ** p"
    },
    "fitted_parameters": {
      "k": -0.04233348082329085,
      "p": 0.6317455702770526
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
