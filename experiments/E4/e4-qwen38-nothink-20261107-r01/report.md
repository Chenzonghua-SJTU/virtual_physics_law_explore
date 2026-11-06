# v15 六世界自主探索 Baseline

实验：`e4-qwen38-nothink-20261107-r01`；归档：E4；规则：`e4`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=开启；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 9 | 170160 | 5126 | 569.556 | 4 | 53.4442 | 2.08695 | 85.9503 | 3.47096 | 1521 | 0 | 91.064 |
| world_2 | submitted / submission_accepted_locally | 8 | 220684 | 6571 | 821.375 | 7 | 81.4616 | 0.470036 | 108.033 | 1.76792 | 1626 | 0 | 111.431 |
| world_3 | submitted / submission_accepted_locally | 11 | 417769 | 4427 | 402.455 | 8 | 15.4836 | 12.0419 | 153.815 | 7.34118 | 816 | 0 | 162.564 |
| world_4 | submitted / submission_accepted_locally | 18 | 907100 | 9032 | 501.778 | 6 | 35.6469 | 2.96844 | 162.812 | 3.9207 | 1921 | 0 | 167.691 |
| world_5 | submitted / submission_accepted_locally | 10 | 540392 | 4533 | 453.3 | 10 | 23.9101 | 1.78023 | 86.9583 | 2.56904 | 1054 | 0 | 92.0339 |
| world_6 | submitted / submission_accepted_locally | 11 | 427841 | 4509 | 409.909 | 8 | 11.1338 | 11.0888 | 164.132 | 16.9072 | 911 | 0 | 184.341 |

## 逐世界记录

### world_1

运行：`e4-qwen38-nothink-20261107-r01-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e4-qwen38-nothink-20261107-r01-world_1)

```json
{
  "law": {
    "law_id": "law_4",
    "law_spec": {
      "ax": "-k*x/(x*x+y*y)",
      "ay": "-k*y/(x*x+y*y)"
    },
    "fitted_parameters": {
      "k": 0.0797826454192098
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

运行：`e4-qwen38-nothink-20261107-r01-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e4-qwen38-nothink-20261107-r01-world_2)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-C*q('charge')/q('mass')*x",
      "ay": "-C*q('charge')/q('mass')*y"
    },
    "fitted_parameters": {
      "C": 0.06538868056463089
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

运行：`e4-qwen38-nothink-20261107-r01-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e4-qwen38-nothink-20261107-r01-world_3)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "sum_b(a*(x-bx)/sqrt((bx-x)**2+(by-y)**2)/((bx-x)**2+(by-y)**2))",
      "ay": "sum_b(a*(y-by)/sqrt((bx-x)**2+(by-y)**2)/((bx-x)**2+(by-y)**2))"
    },
    "fitted_parameters": {
      "a": 0.03847041339976558
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

运行：`e4-qwen38-nothink-20261107-r01-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e4-qwen38-nothink-20261107-r01-world_4)

```json
{
  "law": {
    "law_id": "law_7",
    "law_spec": {
      "ax": "-G*x/(x*x+y*y)/sqrt(x*x+y*y)",
      "ay": "-G*y/(x*x+y*y)/sqrt(x*x+y*y)"
    },
    "fitted_parameters": {
      "G": 0.30000000352732553
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

运行：`e4-qwen38-nothink-20261107-r01-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e4-qwen38-nothink-20261107-r01-world_5)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "-kx*x",
      "ay": "-kx*y"
    },
    "fitted_parameters": {
      "kx": 0.09593142181381265
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

### world_6

运行：`e4-qwen38-nothink-20261107-r01-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e4-qwen38-nothink-20261107-r01-world_6)

```json
{
  "law": {
    "law_id": "law_4",
    "law_spec": {
      "ax": "sum_b(-G*(x-bx)/((sqrt((x-bx)**2+(y-by)**2)+eps)*(sqrt((x-bx)**2+(y-by)**2)+eps)*(sqrt((x-bx)**2+(y-by)**2)+eps)))",
      "ay": "sum_b(-G*(y-by)/((sqrt((x-bx)**2+(y-by)**2)+eps)*(sqrt((x-bx)**2+(y-by)**2)+eps)*(sqrt((x-bx)**2+(y-by)**2)+eps)))"
    },
    "fitted_parameters": {
      "G": 0.022894070920786665,
      "eps": 0.05599000679550367
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
