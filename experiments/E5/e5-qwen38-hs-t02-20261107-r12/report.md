# v15 六世界自主探索 Baseline

实验：`e5-qwen38-hs-t02-20261107-r12`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 17 | 623967 | 4686 | 275.647 | 10 | 26.8966 | 4.80268 | 101.717 | 3.4194 | 1067 | 0 | 106.106 |
| world_2 | submitted / submission_accepted_locally | 6 | 101174 | 1707 | 284.5 | 6 | 97 | 1.15652e-07 | 32.7408 | 1.71792 | 1014 | 0 | 35.2241 |
| world_3 | submitted / submission_accepted_locally | 6 | 180135 | 2381 | 396.833 | 5 | 97.5 | 2.62649e-08 | 47.4808 | 2.46901 | 1244 | 0 | 50.6315 |
| world_4 | submitted / submission_accepted_locally | 19 | 783568 | 5816 | 306.105 | 8 | 32.7946 | 2.77356 | 113.871 | 3.97063 | 2102 | 0 | 122.381 |
| world_5 | submitted / submission_accepted_locally | 11 | 407393 | 3034 | 275.818 | 6 | 25.5387 | 2.09677 | 91.0384 | 11.7794 | 1252 | 0 | 107.168 |
| world_6 | submitted / submission_accepted_locally | 13 | 593291 | 7068 | 543.692 | 8 | 22.2386 | 3.12852 | 251.97 | 3.17508 | 2089 | 0 | 257.21 |

## 逐世界记录

### world_1

运行：`e5-qwen38-hs-t02-20261107-r12-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-hs-t02-20261107-r12-world_1)

```json
{
  "law": {
    "law_id": "law_5",
    "law_spec": {
      "ax": "G*q('charge')*x*sqrt(1/(x**2+y**2))**3",
      "ay": "G*q('charge')*y*sqrt(1/(x**2+y**2))**3"
    },
    "fitted_parameters": {
      "G": 0.001000025519575391
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

运行：`e5-qwen38-hs-t02-20261107-r12-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-hs-t02-20261107-r12-world_2)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-k*q('charge')/q('mass')*x",
      "ay": "-k*q('charge')/q('mass')*y"
    },
    "fitted_parameters": {
      "k": 0.05999999890860252
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

运行：`e5-qwen38-hs-t02-20261107-r12-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-hs-t02-20261107-r12-world_3)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "c0*x+c1*y",
      "ay": "c2*x+c3*y"
    },
    "fitted_parameters": {
      "c0": -0.06000000000236546,
      "c1": 0.0346410161572622,
      "c2": 0.03464101615527216,
      "c3": -0.10000000001034892
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

运行：`e5-qwen38-hs-t02-20261107-r12-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-hs-t02-20261107-r12-world_4)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "c0*x/((x**2+y**2+c1)*sqrt(x**2+y**2+c1))",
      "ay": "c0*y/((x**2+y**2+c1)*sqrt(x**2+y**2+c1))"
    },
    "fitted_parameters": {
      "c0": -0.4075912244928753,
      "c1": 0.38453579831761703
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

运行：`e5-qwen38-hs-t02-20261107-r12-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-hs-t02-20261107-r12-world_5)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "sum_b(-G*(x-bx)/((x-bx)**2+(y-by)**2)*sqrt((x-bx)**2+(y-by)**2))",
      "ay": "sum_b(-G*(y-by)/((x-bx)**2+(y-by)**2)*sqrt((x-bx)**2+(y-by)**2))"
    },
    "fitted_parameters": {
      "G": 0.04248326752781389
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

运行：`e5-qwen38-hs-t02-20261107-r12-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-hs-t02-20261107-r12-world_6)

```json
{
  "law": {
    "law_id": "law_4",
    "law_spec": {
      "ax": "-k*x+c*vy",
      "ay": "-k*y-c*vx"
    },
    "fitted_parameters": {
      "k": 0.09233647810030192,
      "c": 0.1106169552508679
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
