# v15 六世界自主探索 Baseline

实验：`e5-qwen38-hs-t1-20261107-r11`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 13 | 440563 | 2925 | 225 | 10 | 51.1107 | 2.21295 | 75.9682 | 3.5197 | 920 | 0 | 80.6332 |
| world_2 | submitted / submission_accepted_locally | 7 | 134288 | 3437 | 491 | 3 | 98.5 | 3.95557e-08 | 58.935 | 1.76799 | 1916 | 0 | 65.4794 |
| world_3 | submitted / submission_accepted_locally | 6 | 151429 | 2338 | 389.667 | 4 | 98 | 2.6265e-08 | 45.9515 | 2.46827 | 1456 | 0 | 50.6179 |
| world_4 | submitted / submission_accepted_locally | 20 | 885554 | 12664 | 633.2 | 8 | 31.5433 | 2.88401 | 232.281 | 3.92045 | 2574 | 0 | 239.931 |
| world_5 | submitted / submission_accepted_locally | 11 | 440044 | 4724 | 429.455 | 10 | 95 | 1.7239e-08 | 96.4835 | 2.94286 | 1489 | 0 | 101.871 |
| world_6 | incomplete / model_token_budget_exhausted | 79 | 4921374 | 10017 | 126.797 | 10 | — | — | 198.001 | — | 487 | 0 | 200.655 |

## 逐世界记录

### world_1

运行：`e5-qwen38-hs-t1-20261107-r11-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-hs-t1-20261107-r11-world_1)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-k*x/(x**2+y**2)",
      "ay": "-k*y/(x**2+y**2)"
    },
    "fitted_parameters": {
      "k": 0.07048079414921399
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

运行：`e5-qwen38-hs-t1-20261107-r11-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-hs-t1-20261107-r11-world_2)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-k*q('charge')/q('mass')*x",
      "ay": "-k*q('charge')/q('mass')*y"
    },
    "fitted_parameters": {
      "k": 0.060000000000650915
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

运行：`e5-qwen38-hs-t1-20261107-r11-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-hs-t1-20261107-r11-world_3)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "c0*x+c1*y",
      "ay": "c2*x+c3*y"
    },
    "fitted_parameters": {
      "c0": -0.06000000000236457,
      "c1": 0.034641016157262026,
      "c2": 0.03464101615527238,
      "c3": -0.1000000000103485
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

运行：`e5-qwen38-hs-t1-20261107-r11-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-hs-t1-20261107-r11-world_4)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "c0*x*(x**2+y**2)**c1",
      "ay": "c0*y*(x**2+y**2)**c1"
    },
    "fitted_parameters": {
      "c0": -0.2688715710568118,
      "c1": -1.256912114404669
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

运行：`e5-qwen38-hs-t1-20261107-r11-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-hs-t1-20261107-r11-world_5)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "A1*x + B*x**3 + C*x*y**2",
      "ay": "A2*y + B*y**3 + C*x**2*y"
    },
    "fitted_parameters": {
      "A1": -0.06000000007178582,
      "A2": -0.1000000001057942,
      "B": -0.00199999999633203,
      "C": -0.011999999995041939
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

运行：`e5-qwen38-hs-t1-20261107-r11-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-hs-t1-20261107-r11-world_6)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

时间戳为 UTC；完整预算、真实模型回复、实验与候选版本保存在各运行目录。
