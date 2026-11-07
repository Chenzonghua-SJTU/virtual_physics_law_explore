# v15 六世界自主探索 Baseline

实验：`e5-qwen38-tools-on-20261107-r06`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 12 | 319046 | 8620 | 718.333 | 6 | 96.9999 | 0.00257273 | 149.117 | 3.66957 | 2104 | 0 | 156.701 |
| world_2 | submitted / submission_accepted_locally | 9 | 237809 | 3912 | 434.667 | 7 | 96.5 | 3.95711e-08 | 69.7797 | 1.92501 | 1354 | 0 | 75.5751 |
| world_3 | submitted / submission_accepted_locally | 8 | 236516 | 2835 | 354.375 | 8 | 91 | 2.62649e-08 | 52.2614 | 2.51889 | 1000 | 0 | 55.7194 |
| world_4 | submitted / submission_accepted_locally | 10 | 374891 | 3840 | 384 | 10 | 42.5009 | 2.41901 | 72.0026 | 4.37085 | 647 | 0 | 81.5024 |
| world_5 | submitted / submission_accepted_locally | 7 | 238909 | 2750 | 392.857 | 9 | 29.6129 | 1.72763 | 53.0433 | 2.61859 | 989 | 0 | 61.1964 |
| world_6 | submitted / submission_accepted_locally | 10 | 404437 | 5260 | 526 | 10 | 16.9359 | 4.31533 | 119.91 | 18.5375 | 1737 | 0 | 143.35 |

## 逐世界记录

### world_1

运行：`e5-qwen38-tools-on-20261107-r06-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-tools-on-20261107-r06-world_1)

```json
{
  "law": {
    "law_id": "law_4",
    "law_spec": {
      "ax": "-sum_b(K*q('charge')*(x-bx)/(q('mass')*((x-bx)**2+(y-by)**2)))",
      "ay": "-sum_b(K*q('charge')*(y-by)/(q('mass')*((x-bx)**2+(y-by)**2)))"
    },
    "fitted_parameters": {
      "K": 0.07952081975411414
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

运行：`e5-qwen38-tools-on-20261107-r06-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-tools-on-20261107-r06-world_2)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "sum_b(-k * q('charge') / q('mass') * (x - bx))",
      "ay": "sum_b(-k * q('charge') / q('mass') * (y - by))"
    },
    "fitted_parameters": {
      "k": 0.06
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

运行：`e5-qwen38-tools-on-20261107-r06-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-tools-on-20261107-r06-world_3)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "a*x + b*y",
      "ay": "c*x + d*y"
    },
    "fitted_parameters": {
      "a": -0.06000000000236577,
      "b": 0.03464101615726213,
      "c": 0.03464101615527206,
      "d": -0.10000000001034882
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

运行：`e5-qwen38-tools-on-20261107-r06-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-tools-on-20261107-r06-world_4)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "sum_b(q('charge')/q('mass')*c*(bx-x)*((x-bx)**2+(y-by)**2+eps)**(-1)*((x-bx)**2+(y-by)**2+eps)**(-1))",
      "ay": "sum_b(q('charge')/q('mass')*c*(by-y)*((x-bx)**2+(y-by)**2+eps)**(-1)*((x-bx)**2+(y-by)**2+eps)**(-1))"
    },
    "fitted_parameters": {
      "c": 1.0158095886834326,
      "eps": 0.9427256654777252
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

运行：`e5-qwen38-tools-on-20261107-r06-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-tools-on-20261107-r06-world_5)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-kx*x + cvx*vx - cvy*vy",
      "ay": "-ky*y - cvy*vx + cvx*vy"
    },
    "fitted_parameters": {
      "kx": 0.07613103692479954,
      "ky": 0.11687483229439008,
      "cvx": -0.009151569922609626,
      "cvy": 0.0066495606102709584
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

运行：`e5-qwen38-tools-on-20261107-r06-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-tools-on-20261107-r06-world_6)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "sum_b(G*q('mass')*(bx-x)/((x-bx)**2+(y-by)**2+eps)*sqrt((x-bx)**2+(y-by)**2+eps))",
      "ay": "sum_b(G*q('mass')*(by-y)/((x-bx)**2+(y-by)**2+eps)*sqrt((x-bx)**2+(y-by)**2+eps))"
    },
    "fitted_parameters": {
      "G": 0.05229265243975258,
      "eps": 0.06881342664890552
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
