# v15 六世界自主探索 Baseline

实验：`e6-qwen38-e3-s42-20261107`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | incomplete / wall_time_exhausted | 155 | 4799360 | 17058 | — | 10 | — | — | 295.656 | — | 336 | 0 | 297.306 |
| world_2 | incomplete / model_token_budget_exhausted | 51 | 4913377 | 5412 | 106.118 | 10 | — | — | 133.888 | — | 281 | 0 | 137.42 |
| world_3 | incomplete / wall_time_exhausted | 88 | 3100098 | 17139 | — | 10 | — | — | 295.593 | — | 395 | 0 | 297.304 |
| world_4 | incomplete / model_token_budget_exhausted | 109 | 4968654 | 12258 | 112.459 | 10 | — | — | 223.381 | — | 349 | 0 | 224.88 |
| world_5 | incomplete / wall_time_exhausted | 13 | 566574 | 3588 | 276 | 8 | — | — | 295.984 | — | 391 | 0 | 300.543 |
| world_6 | incomplete / model_token_budget_exhausted | 79 | 4985234 | 5970 | 75.5696 | 10 | — | — | 166.787 | — | 402 | 0 | 171.262 |

## 逐世界记录

### world_1

运行：`e6-qwen38-e3-s42-20261107-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-e3-s42-20261107-world_1)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_2

运行：`e6-qwen38-e3-s42-20261107-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-e3-s42-20261107-world_2)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_3

运行：`e6-qwen38-e3-s42-20261107-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-e3-s42-20261107-world_3)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_4

运行：`e6-qwen38-e3-s42-20261107-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-e3-s42-20261107-world_4)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_5

运行：`e6-qwen38-e3-s42-20261107-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-e3-s42-20261107-world_5)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_6

运行：`e6-qwen38-e3-s42-20261107-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-e3-s42-20261107-world_6)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

时间戳为 UTC；完整预算、真实模型回复、实验与候选版本保存在各运行目录。
