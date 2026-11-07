# v15 六世界自主探索 Baseline

实验：`e5-qwen38-hs-seed43-20261107-r13`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 9 | 185775 | 3556 | 395.111 | 9 | 95.5 | 0.00152575 | 69.7735 | 3.61985 | 1620 | 0 | 75.5764 |
| world_2 | submitted / submission_accepted_locally | 11 | 275414 | 3635 | 330.455 | 9 | 95.5 | 7.42807e-08 | 66.3097 | 1.71785 | 1210 | 0 | 70.5182 |
| world_3 | submitted / submission_accepted_locally | 5 | 116017 | 2023 | 404.6 | 2 | 99 | 2.62649e-08 | 34.1857 | 2.51935 | 1349 | 0 | 40.5026 |
| world_4 | submitted / submission_accepted_locally | 11 | 328345 | 8415 | 765 | 10 | 94.9992 | 0.00559395 | 148.681 | 4.1206 | 2541 | 0 | 157.558 |
| world_5 | submitted / submission_accepted_locally | 14 | 834076 | 16673 | 1190.93 | 6 | 30.4375 | 1.67022 | 294.739 | 2.56883 | 2661 | 0 | 302.329 |
| world_6 | submitted / submission_accepted_locally | 17 | 1071467 | 9168 | 539.294 | 8 | 17.1386 | 4.24773 | 191.321 | 3.26969 | 2588 | 0 | 195.659 |

## 逐世界记录

### world_1

运行：`e5-qwen38-hs-seed43-20261107-r13-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-hs-seed43-20261107-r13-world_1)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "sum_b(kx*(bx-x)/((bx-x)**2+(by-y)**2)*q('charge')/q('mass'))",
      "ay": "sum_b(ky*(by-y)/((bx-x)**2+(by-y)**2)*q('charge')/q('mass'))"
    },
    "fitted_parameters": {
      "kx": 0.07956063577134961,
      "ky": 0.07954424465258361
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

运行：`e5-qwen38-hs-seed43-20261107-r13-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-hs-seed43-20261107-r13-world_2)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-k*q('charge')*x/q('mass')",
      "ay": "-k*q('charge')*y/q('mass')"
    },
    "fitted_parameters": {
      "k": 0.05999999941075496
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

运行：`e5-qwen38-hs-seed43-20261107-r13-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-hs-seed43-20261107-r13-world_3)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "c0*x + c1*y",
      "ay": "c2*x + c3*y"
    },
    "fitted_parameters": {
      "c0": -0.06000000000236578,
      "c1": 0.034641016157261804,
      "c2": 0.03464101615527154,
      "c3": -0.1000000000103492
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

运行：`e5-qwen38-hs-seed43-20261107-r13-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-hs-seed43-20261107-r13-world_4)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "c0*q('charge')/q('mass')*x*(x**2+y**2)**c1*exp(-c2*sqrt(x**2+y**2))",
      "ay": "c0*q('charge')/q('mass')*y*(x**2+y**2)**c1*exp(-c2*sqrt(x**2+y**2))"
    },
    "fitted_parameters": {
      "c0": -0.31808844676783465,
      "c1": -0.9986044976410052,
      "c2": 0.25085443982293554
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

运行：`e5-qwen38-hs-seed43-20261107-r13-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-hs-seed43-20261107-r13-world_5)

```json
{
  "law": {
    "law_id": "law_4",
    "law_spec": {
      "ax": "-c1*x - c3*vx",
      "ay": "-c2*y - c3*vy"
    },
    "fitted_parameters": {
      "c1": 0.07869668614850595,
      "c2": 0.1151539981594583,
      "c3": 0.04566181340722665
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

运行：`e5-qwen38-hs-seed43-20261107-r13-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-hs-seed43-20261107-r13-world_6)

```json
{
  "law": {
    "law_id": "law_5",
    "law_spec": {
      "ax": "p11*x + p12*y",
      "ay": "p21*x + p22*y"
    },
    "fitted_parameters": {
      "p11": -0.07882720482323338,
      "p12": 0.04118012124833241,
      "p21": 0.04313202520133922,
      "p22": -0.16051090598104223
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
