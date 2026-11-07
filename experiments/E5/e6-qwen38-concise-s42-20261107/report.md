# v15 六世界自主探索 Baseline

实验：`e6-qwen38-concise-s42-20261107`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | incomplete / wall_time_exhausted | 43 | 937288 | 18457 | — | 5 | — | — | 295.986 | — | 442 | 0 | 299.202 |
| world_2 | submitted / submission_accepted_locally | 6 | 97364 | 3029 | 504.833 | 6 | 20.6511 | 2.49277 | 49.8828 | 1.74248 | 838 | 0 | 55.6898 |
| world_3 | submitted / submission_accepted_locally | 8 | 274651 | 3736 | 467 | 8 | 96 | 2.63129e-08 | 66.1391 | 2.51876 | 1163 | 0 | 70.9614 |
| world_4 | incomplete / model_token_budget_exhausted | 59 | 4880347 | 6870 | 116.441 | 10 | — | — | 150.309 | — | 273 | 0 | 153.577 |
| world_5 | submitted / submission_accepted_locally | 15 | 565697 | 4919 | 327.933 | 10 | 25.2694 | 2.12819 | 89.7939 | 2.62332 | 1128 | 0 | 98.01 |
| world_6 | submitted / submission_accepted_locally | 13 | 364268 | 4654 | 358 | 10 | 26.0692 | 2.65199 | 106.307 | 6.22285 | 951 | 0 | 113.918 |

## 逐世界记录

### world_1

运行：`e6-qwen38-concise-s42-20261107-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-concise-s42-20261107-world_1)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_2

运行：`e6-qwen38-concise-s42-20261107-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-concise-s42-20261107-world_2)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-k*x",
      "ay": "-k*y"
    },
    "fitted_parameters": {
      "k": 0.05999999999928331
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

运行：`e6-qwen38-concise-s42-20261107-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-concise-s42-20261107-world_3)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "a*x + b*y",
      "ay": "c*x + d*y"
    },
    "fitted_parameters": {
      "a": -0.06000000000033992,
      "b": 0.03464101615579679,
      "c": 0.03464101615209863,
      "d": -0.1000000000077994
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

运行：`e6-qwen38-concise-s42-20261107-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-concise-s42-20261107-world_4)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_5

运行：`e6-qwen38-concise-s42-20261107-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-concise-s42-20261107-world_5)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "a11*x+a12*y",
      "ay": "a21*x+a22*y"
    },
    "fitted_parameters": {
      "a11": -0.06736773470831028,
      "a12": -0.0023959033297864434,
      "a21": -0.0013231345865636647,
      "a22": -0.10807720313927201
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

运行：`e6-qwen38-concise-s42-20261107-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-concise-s42-20261107-world_6)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-d1*x + d2*sum_b(sqrt((x-bx)*(x-bx)+(y-by)*(y-by)))",
      "ay": "-d3*y + d2*sum_b(sqrt((x-bx)*(x-bx)+(y-by)*(y-by)))"
    },
    "fitted_parameters": {
      "d1": 0.07842722205197827,
      "d2": 0.0006281465226676552,
      "d3": 0.0914402053728069
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
