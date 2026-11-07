# v15 六世界自主探索 Baseline

实验：`e5-qwen38-tools-off-20261107-r05`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 13 | 280172 | 3722 | 286.308 | 10 | 23.922 | 5.6656 | 70.289 | 3.62918 | 1539 | 0 | 75.6202 |
| world_2 | incomplete / wall_time_exhausted | 84 | 2209828 | 17914 | — | 9 | — | — | 295.992 | — | 448 | 0 | 298.624 |
| world_3 | incomplete / wall_time_exhausted | 58 | 2904545 | 16860 | — | 8 | — | — | 295.939 | — | 391 | 0 | 299.279 |
| world_4 | incomplete / wall_time_exhausted | 89 | 2433100 | 17743 | — | 10 | — | — | 295.588 | — | 456 | 0 | 296.201 |
| world_5 | submitted / submission_accepted_locally | 20 | 1052803 | 11510 | 575.5 | 10 | 25.277 | 1.68106 | 292.97 | 2.56828 | 1672 | 0 | 297.199 |
| world_6 | incomplete / wall_time_exhausted | 59 | 2990035 | 17182 | — | 8 | — | — | 295.926 | — | 391 | 0 | 298.971 |

## 逐世界记录

### world_1

运行：`e5-qwen38-tools-off-20261107-r05-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-tools-off-20261107-r05-world_1)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-d*(x + t*(vy-vx))/((x*x+y*y)*(sqrt(x*x+y*y))) - c*(vx - (x + t*(vy-vx))/((x*x+y*y)*(sqrt(x*x+y*y))))*0",
      "ay": "-d*(y + t*(vx-vy))/((x*x+y*y)*(sqrt(x*x+y*y))) - c*(vy - (y + t*(vx-vy))/((x*x+y*y)*(sqrt(x*x+y*y))))*0"
    },
    "fitted_parameters": {
      "d": 0.06485839843749965,
      "c": 0.0
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

运行：`e5-qwen38-tools-off-20261107-r05-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-tools-off-20261107-r05-world_2)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_3

运行：`e5-qwen38-tools-off-20261107-r05-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-tools-off-20261107-r05-world_3)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_4

运行：`e5-qwen38-tools-off-20261107-r05-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-tools-off-20261107-r05-world_4)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_5

运行：`e5-qwen38-tools-off-20261107-r05-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-tools-off-20261107-r05-world_5)

```json
{
  "law": {
    "law_id": "law_5",
    "law_spec": {
      "ax": "-k * x",
      "ay": "-k * y"
    },
    "fitted_parameters": {
      "k": 0.10077477043806293
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

运行：`e5-qwen38-tools-off-20261107-r05-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-tools-off-20261107-r05-world_6)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

时间戳为 UTC；完整预算、真实模型回复、实验与候选版本保存在各运行目录。
