# v15 六世界自主探索 Baseline

实验：`e5-qwen38-compact-20261107-r07`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 5 | 79342 | 3323 | 664.6 | 6 | 96.9999 | 0.00169932 | 56.0564 | 3.52175 | 1336 | 0 | 60.6888 |
| world_2 | submitted / submission_accepted_locally | 6 | 94140 | 2933 | 488.833 | 7 | 96.5 | 3.95711e-08 | 48.7537 | 1.71727 | 1340 | 0 | 55.6204 |
| world_3 | incomplete / model_token_budget_exhausted | 108 | 4993836 | 11742 | 108.722 | 10 | — | — | 216.874 | — | 302 | 0 | 219.215 |
| world_4 | submitted / submission_accepted_locally | 18 | 504553 | 10437 | 579.833 | 4 | 39.5549 | 2.63086 | 177.333 | 3.97068 | 2345 | 0 | 183.338 |
| world_5 | incomplete / wall_time_exhausted | 60 | 2314588 | 17420 | — | 6 | — | — | 295.804 | — | 302 | 0 | 296.917 |
| world_6 | submitted / submission_accepted_locally | 12 | 374417 | 2739 | 228.25 | 10 | 16.2173 | 4.58026 | 70.3308 | 9.6787 | 1017 | 0 | 81.7094 |

## 逐世界记录

### world_1

运行：`e5-qwen38-compact-20261107-r07-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-compact-20261107-r07-world_1)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-k*(q('charge')/q('mass'))*x/(x*x+y*y)",
      "ay": "-k*(q('charge')/q('mass'))*y/(x*x+y*y)"
    },
    "fitted_parameters": {
      "k": 0.07956606558660789
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

运行：`e5-qwen38-compact-20261107-r07-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-compact-20261107-r07-world_2)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-k*q('charge')/q('mass')*x",
      "ay": "-k*q('charge')/q('mass')*y"
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

运行：`e5-qwen38-compact-20261107-r07-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-compact-20261107-r07-world_3)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_4

运行：`e5-qwen38-compact-20261107-r07-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-compact-20261107-r07-world_4)

```json
{
  "law": {
    "law_id": "law_5",
    "law_spec": {
      "ax": "-A*x/(q('mass')*sqrt((x*x)+(y*y))*((x*x)+(y*y)+C))",
      "ay": "-A*y/(q('mass')*sqrt((x*x)+(y*y))*((x*x)+(y*y)+C))"
    },
    "fitted_parameters": {
      "A": 0.47606636907091404,
      "C": 0.9584220716338735
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

运行：`e5-qwen38-compact-20261107-r07-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-compact-20261107-r07-world_5)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_6

运行：`e5-qwen38-compact-20261107-r07-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-compact-20261107-r07-world_6)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-d*(x*sqrt(x*x+y*y)) + sum_b(-d*(x-bx)*sqrt((x-bx)*(x-bx)+(y-by)*(y-by)))",
      "ay": "-d*(y*sqrt(x*x+y*y)) + sum_b(-d*(y-by)*sqrt((x-bx)*(x-bx)+(y-by)*(y-by)))"
    },
    "fitted_parameters": {
      "d": 0.0030029213593892722
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
