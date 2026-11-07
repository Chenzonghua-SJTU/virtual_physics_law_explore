# v15 六世界自主探索 Baseline

实验：`e5-qwen38-candidates-20261107-r10`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 13 | 356826 | 3523 | 271 | 10 | 26.0114 | 5.02434 | 74.0399 | 3.52042 | 935 | 0 | 81.2822 |
| world_2 | incomplete / model_token_budget_exhausted | 50 | 4628812 | 4201 | 84.02 | 10 | — | — | 156.899 | — | 212 | 0 | 158.54 |
| world_3 | submitted / submission_accepted_locally | 7 | 204520 | 6362 | 908.857 | 6 | 92 | 2.54791e-08 | 113.913 | 2.51842 | 2914 | 0 | 117.203 |
| world_4 | incomplete / model_token_budget_exhausted | 62 | 4966263 | 7650 | 123.387 | 10 | — | — | 179.252 | — | 226 | 0 | 184.496 |
| world_5 | incomplete / model_token_budget_exhausted | 62 | 4943119 | 9219 | 148.694 | 10 | — | — | 257.993 | — | 571 | 0 | 259 |
| world_6 | submitted / submission_accepted_locally | 16 | 693671 | 9968 | 623 | 7 | 14.9757 | 5.16283 | 273.465 | 9.92728 | 1970 | 0 | 285.469 |

## 逐世界记录

### world_1

运行：`e5-qwen38-candidates-20261107-r10-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-candidates-20261107-r10-world_1)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-G*q('charge')*x/sqrt(x**2+y**2)*(x**2+y**2)",
      "ay": "-G*q('charge')*y/sqrt(x**2+y**2)*(x**2+y**2)"
    },
    "fitted_parameters": {
      "G": 0.0017731368105114536
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

运行：`e5-qwen38-candidates-20261107-r10-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-candidates-20261107-r10-world_2)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_3

运行：`e5-qwen38-candidates-20261107-r10-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-candidates-20261107-r10-world_3)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "a11*x+a12*y",
      "ay": "a21*x+a22*y"
    },
    "fitted_parameters": {
      "a11": -0.06000000005006103,
      "a12": 0.034641016189627095,
      "a21": 0.03464101624290725,
      "a22": -0.10000000006106145
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

运行：`e5-qwen38-candidates-20261107-r10-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-candidates-20261107-r10-world_4)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_5

运行：`e5-qwen38-candidates-20261107-r10-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-candidates-20261107-r10-world_5)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_6

运行：`e5-qwen38-candidates-20261107-r10-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-candidates-20261107-r10-world_6)

```json
{
  "law": {
    "law_id": "law_4",
    "law_spec": {
      "ax": "-sum_b(G*(x-bx)/((x-bx)**2+(y-by)**2+L2))",
      "ay": "-sum_b(G*(y-by)/((x-bx)**2+(y-by)**2+L2))"
    },
    "fitted_parameters": {
      "G": 0.10285499986459916,
      "L2": 0.5344077512887857
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
