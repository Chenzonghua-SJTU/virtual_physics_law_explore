# v15 六世界自主探索 Baseline

实验：`e5-qwen38-clean-20261107-r01`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 7 | 110506 | 4820 | 688.571 | 6 | 97 | 0.00149947 | 78.9363 | 3.71992 | 1398 | 0 | 85.9188 |
| world_2 | submitted / submission_accepted_locally | 9 | 177361 | 5794 | 643.778 | 10 | 95 | 3.84729e-08 | 99.0246 | 1.7729 | 2500 | 0 | 106.21 |
| world_3 | submitted / submission_accepted_locally | 11 | 351954 | 7594 | 690.364 | 6 | 92 | 2.63195e-08 | 153.883 | 2.51856 | 1863 | 0 | 162.14 |
| world_4 | incomplete / model_finish_length | 8 | 128359 | 6090 | 761.25 | 2 | — | — | 100.762 | — | 4096 | 0 | 106.208 |
| world_5 | submitted / submission_accepted_locally | 26 | 1475034 | 6761 | 260.038 | 3 | 15.5926 | 9.45444 | 265.76 | 4.27073 | 890 | 0 | 270.799 |
| world_6 | submitted / submission_accepted_locally | 16 | 644609 | 7963 | 497.688 | 6 | 26.6027 | 2.59812 | 192.53 | 5.02464 | 1712 | 0 | 199.167 |

## 逐世界记录

### world_1

运行：`e5-qwen38-clean-20261107-r01-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-clean-20261107-r01-world_1)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "sum_b(-k*q('charge')/q('mass')*(x-bx)/((x-bx)**2+(y-by)**2))",
      "ay": "sum_b(-k*q('charge')/q('mass')*(y-by)/((x-bx)**2+(y-by)**2))"
    },
    "fitted_parameters": {
      "k": 0.07955562471166246
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

运行：`e5-qwen38-clean-20261107-r01-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-clean-20261107-r01-world_2)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "-K*x*q('charge')/q('mass')",
      "ay": "-K*y*q('charge')/q('mass')"
    },
    "fitted_parameters": {
      "K": 0.060000000062828567
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

运行：`e5-qwen38-clean-20261107-r01-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-clean-20261107-r01-world_3)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "k1*x + k2*y",
      "ay": "k2*x + k3*y"
    },
    "fitted_parameters": {
      "k1": -0.05999999999817431,
      "k2": 0.03464101615054743,
      "k3": -0.10000000001039734
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

运行：`e5-qwen38-clean-20261107-r01-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-clean-20261107-r01-world_4)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_5

运行：`e5-qwen38-clean-20261107-r01-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-clean-20261107-r01-world_5)

```json
{
  "law": {
    "law_id": "law_5",
    "law_spec": {
      "ax": "a1*sum_b((bx-x)*(bx-x)-(by-y)*(by-y))/(x*x+y*y)**2 + a2*sum_b((bx-x)*(by-y))/(x*x+y*y)**2",
      "ay": "-a2*sum_b((bx-x)*(by-y))/(x*x+y*y)**2 + a1*sum_b((bx-x)*(bx-x)-(by-y)*(by-y))/(x*x+y*y)**2"
    },
    "fitted_parameters": {
      "a1": -0.001467395853787113,
      "a2": 0.0034409499963853657
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

运行：`e5-qwen38-clean-20261107-r01-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-clean-20261107-r01-world_6)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "sum_b(-K*(x-bx))",
      "ay": "sum_b(-K*(y-by))"
    },
    "fitted_parameters": {
      "K": 0.010272127319395296
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
