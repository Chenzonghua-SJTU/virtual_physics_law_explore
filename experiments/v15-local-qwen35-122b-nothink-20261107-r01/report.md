# v15 六世界自主探索 Baseline

实验：`v15-local-qwen35-122b-nothink-20261107-r01`；编排状态：`completed`。

模型 `qwen3.5-122b-a10b`；thinking=false；无噪声；seed=42；每世界 100 能量、60 分钟；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 65536，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；分数保留本地 100 能量口径，不是比赛成绩。未完成、错误与评测失败均保留，不按零误差处理。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。总耗时从 worker 启动至评测结束，不含排队。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 7 | 133701 | 8362 | 1194.57 | 1 | 53.4151 | 2.08847 | 996.018 |
| world_2 | submitted / submission_accepted_locally | 5 | 80447 | 5849 | 1169.8 | 4 | 25.6511 | 2.49277 | 701.483 |
| world_3 | submitted / submission_accepted_locally | 11 | 446578 | 5655 | 514.091 | 7 | 22.9658 | 2.82412 | 716.684 |
| world_4 | submitted / submission_accepted_locally | 9 | 188289 | 7434 | 826 | 7 | 66.2703 | 1.48146 | 891.735 |
| world_5 | submitted / submission_accepted_locally | 11 | 362907 | 5032 | 457.455 | 4 | 31.8625 | 1.58036 | 636.189 |
| world_6 | submitted / submission_accepted_locally | 17 | 817831 | 12886 | 758 | 5 | 12.0872 | 8.12339 | 1565.1 |

## 逐世界记录

### world_1

运行：`v15-local-qwen35-122b-nothink-20261107-r01-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=v15-local-qwen35-122b-nothink-20261107-r01-world_1)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-k * x / (x*x + y*y)",
      "ay": "-k * y / (x*x + y*y)"
    },
    "fitted_parameters": {
      "k": 0.07955634776536571
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

运行：`v15-local-qwen35-122b-nothink-20261107-r01-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=v15-local-qwen35-122b-nothink-20261107-r01-world_2)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-k*x",
      "ay": "-k*y"
    },
    "fitted_parameters": {
      "k": 0.05999999970181658
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

运行：`v15-local-qwen35-122b-nothink-20261107-r01-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=v15-local-qwen35-122b-nothink-20261107-r01-world_3)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "-k * x",
      "ay": "-k * y"
    },
    "fitted_parameters": {
      "k": 0.056056478050259775
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

运行：`v15-local-qwen35-122b-nothink-20261107-r01-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=v15-local-qwen35-122b-nothink-20261107-r01-world_4)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-k * q('charge') / q('mass') * x / ((x*x + y*y) * sqrt(x*x + y*y))",
      "ay": "-k * q('charge') / q('mass') * y / ((x*x + y*y) * sqrt(x*x + y*y))"
    },
    "fitted_parameters": {
      "k": 0.3372398265783139
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

运行：`v15-local-qwen35-122b-nothink-20261107-r01-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=v15-local-qwen35-122b-nothink-20261107-r01-world_5)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-k * x",
      "ay": "-k * y"
    },
    "fitted_parameters": {
      "k": 0.10723111030852309
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

运行：`v15-local-qwen35-122b-nothink-20261107-r01-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=v15-local-qwen35-122b-nothink-20261107-r01-world_6)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-G * x / sqrt(x**2 + y**2)**3",
      "ay": "-G * y / sqrt(x**2 + y**2)**3"
    },
    "fitted_parameters": {
      "G": 1.3657177396834372
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
