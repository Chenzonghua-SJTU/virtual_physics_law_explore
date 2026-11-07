# v15 六世界自主探索 Baseline

实验：`e6-qwen38-baseline-s42-20261107`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 22 | 571437 | 7472 | 339.636 | 9 | 50.8835 | 1.98814 | 126.563 | 3.67067 | 2191 | 0 | 132.613 |
| world_2 | submitted / submission_accepted_locally | 9 | 143394 | 3144 | 349.333 | 4 | 27.2447 | 2.29803 | 52.9395 | 1.71805 | 1321 | 0 | 55.6295 |
| world_3 | incomplete / wall_time_exhausted | 49 | 2180348 | 17242 | — | 4 | — | — | 295.919 | — | 557 | 0 | 298.354 |
| world_4 | incomplete / model_token_budget_exhausted | 69 | 4955262 | 5327 | 77.2029 | 10 | — | — | 121.764 | — | 467 | 0 | 127.452 |
| world_5 | incomplete / wall_time_exhausted | 126 | 4786530 | 17075 | — | 10 | — | — | 295.8 | — | 216 | 0 | 300.18 |
| world_6 | incomplete / model_token_budget_exhausted | 39 | 4762865 | 10392 | 266.462 | 4 | — | — | 264.553 | — | 272 | 0 | 270.051 |

## 逐世界记录

### world_1

运行：`e6-qwen38-baseline-s42-20261107-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-baseline-s42-20261107-world_1)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-k*x*sum_b((x-bx)**2+(y-by)**2)**(-1)/q('mass')",
      "ay": "-k*y*sum_b((x-bx)**2+(y-by)**2)**(-1)/q('mass')"
    },
    "fitted_parameters": {
      "k": 0.08062167870788788
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

### world_2

运行：`e6-qwen38-baseline-s42-20261107-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-baseline-s42-20261107-world_2)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-A*x/q('mass')",
      "ay": "-A*y/q('mass')"
    },
    "fitted_parameters": {
      "A": 0.05999999977401865
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

运行：`e6-qwen38-baseline-s42-20261107-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-baseline-s42-20261107-world_3)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_4

运行：`e6-qwen38-baseline-s42-20261107-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-baseline-s42-20261107-world_4)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_5

运行：`e6-qwen38-baseline-s42-20261107-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-baseline-s42-20261107-world_5)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_6

运行：`e6-qwen38-baseline-s42-20261107-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-baseline-s42-20261107-world_6)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

时间戳为 UTC；完整预算、真实模型回复、实验与候选版本保存在各运行目录。
