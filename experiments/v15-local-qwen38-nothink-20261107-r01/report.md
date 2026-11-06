# v15 六世界自主探索 Baseline

实验：`v15-local-qwen38-nothink-20261107-r01`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；无噪声；seed=42；每世界 100 能量、60 分钟；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 65536，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；分数保留本地 100 能量口径，不是比赛成绩。未完成、错误与评测失败均保留，不按零误差处理。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。总耗时从 worker 启动至评测结束，不含排队。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 17 | 843534 | 7125 | 419.118 | 22 | 87.801 | 0.805638 | 648.876 |
| world_2 | submitted / submission_accepted_locally | 12 | 218782 | 5368 | 447.333 | 7 | 94.65 | 6.68152e-08 | 470.524 |
| world_3 | submitted / submission_accepted_locally | 18 | 976455 | 7826 | 434.778 | 13 | 99.35 | 3.25063e-08 | 771.667 |
| world_4 | submitted / submission_accepted_locally | 12 | 340481 | 7288 | 607.333 | 9 | 94.7954 | 0.440099 | 637.021 |
| world_5 | submitted / submission_accepted_locally | 29 | 2213689 | 9042 | 311.793 | 48 | 17.3993 | 2.55827 | 1150.92 |
| world_6 | submitted / submission_accepted_locally | 20 | 1042617 | 23550 | 1177.5 | 14 | 99.3 | 3.52378e-08 | 1799.45 |

## 逐世界记录

### world_1

运行：`v15-local-qwen38-nothink-20261107-r01-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=v15-local-qwen38-nothink-20261107-r01-world_1)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "-q('charge')/q('mass')*sum_b(G*exp(-B*sqrt((x-bx)**2+(y-by)**2))*(x-bx) / sqrt((x-bx)**2+(y-by)**2))",
      "ay": "-q('charge')/q('mass')*sum_b(G*exp(-B*sqrt((x-bx)**2+(y-by)**2))*(y-by) / sqrt((x-bx)**2+(y-by)**2))"
    },
    "fitted_parameters": {
      "G": 0.09855850794426509,
      "B": 0.40917551520044043
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

运行：`v15-local-qwen38-nothink-20261107-r01-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=v15-local-qwen38-nothink-20261107-r01-world_2)

```json
{
  "law": {
    "law_id": "law_4",
    "law_spec": {
      "ax": "sum_b(-q('charge')/q('mass')*k*(x-bx))",
      "ay": "sum_b(-q('charge')/q('mass')*k*(y-by))"
    },
    "fitted_parameters": {
      "k": 0.059999999508925636
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

运行：`v15-local-qwen38-nothink-20261107-r01-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=v15-local-qwen38-nothink-20261107-r01-world_3)

```json
{
  "law": {
    "law_id": "law_7",
    "law_spec": {
      "ax": "a11*x+a12*y",
      "ay": "a21*x+a22*y"
    },
    "fitted_parameters": {
      "a11": -0.06000000012361108,
      "a12": 0.034641016458164246,
      "a21": 0.034641016363715894,
      "a22": -0.10000000052942717
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

运行：`v15-local-qwen38-nothink-20261107-r01-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=v15-local-qwen38-nothink-20261107-r01-world_4)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-G*q('charge')/q('mass')*x/sqrt((x*x+y*y+eps2)*(x*x+y*y+eps2)*(x*x+y*y+eps2))",
      "ay": "-G*q('charge')/q('mass')*y/sqrt((x*x+y*y+eps2)*(x*x+y*y+eps2)*(x*x+y*y+eps2))"
    },
    "fitted_parameters": {
      "G": 0.46287573767388734,
      "eps2": 0.5416699255382006
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

运行：`v15-local-qwen38-nothink-20261107-r01-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=v15-local-qwen38-nothink-20261107-r01-world_5)

```json
{
  "law": {
    "law_id": "law_10",
    "law_spec": {
      "ax": "sum_b(g*(bx-x)/((x-bx)**2+(y-by)**2)*sqrt((x-bx)**2+(y-by)**2))",
      "ay": "sum_b(g*(by-y)/((x-bx)**2+(y-by)**2)*sqrt((x-bx)**2+(y-by)**2))"
    },
    "fitted_parameters": {
      "g": 0.033
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

### world_6

运行：`v15-local-qwen38-nothink-20261107-r01-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=v15-local-qwen38-nothink-20261107-r01-world_6)

```json
{
  "law": {
    "law_id": "law_5",
    "law_spec": {
      "ax": "(-(m0 - m1*cos(om*t+ph0)))*x + m1*sin(om*t+ph0)*y",
      "ay": "m1*sin(om*t+ph0)*x - (m0 + m1*cos(om*t+ph0))*y"
    },
    "fitted_parameters": {
      "m0": 0.12000000001250755,
      "m1": 0.06000000005331924,
      "om": 0.39269908178426566,
      "ph0": 0.5999999988619208
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
