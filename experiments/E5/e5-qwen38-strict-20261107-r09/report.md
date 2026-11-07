# v15 六世界自主探索 Baseline

实验：`e5-qwen38-strict-20261107-r09`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | incomplete / model_token_budget_exhausted | 66 | 4829530 | 6042 | 91.5455 | 10 | — | — | 161.57 | — | 289 | 0 | 164.646 |
| world_2 | submitted / submission_accepted_locally | 7 | 127195 | 1564 | 223.429 | 7 | 96.5 | 4.41242e-08 | 36.7065 | 1.71746 | 325 | 0 | 40.4516 |
| world_3 | submitted / submission_accepted_locally | 9 | 256803 | 1357 | 150.778 | 10 | 95 | 2.68072e-08 | 40.7418 | 2.46819 | 366 | 0 | 45.5492 |
| world_4 | submitted / submission_accepted_locally | 12 | 455222 | 2798 | 233.167 | 10 | 30.4394 | 3.58017 | 89.3661 | 3.9204 | 388 | 0 | 96.898 |
| world_5 | incomplete / model_token_budget_exhausted | 37 | 4814718 | 9416 | 254.486 | 4 | — | — | 226.162 | — | 351 | 0 | 229.187 |
| world_6 | submitted / submission_accepted_locally | 11 | 411936 | 1313 | 119.364 | 10 | 15.6782 | 4.81022 | 37.6336 | 3.52152 | 366 | 0 | 46.2587 |

## 逐世界记录

### world_1

运行：`e5-qwen38-strict-20261107-r09-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-strict-20261107-r09-world_1)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_2

运行：`e5-qwen38-strict-20261107-r09-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-strict-20261107-r09-world_2)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-c*q('charge')/q('mass')*x",
      "ay": "-c*q('charge')/q('mass')*y"
    },
    "fitted_parameters": {
      "c": 0.05999999987041086
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

运行：`e5-qwen38-strict-20261107-r09-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-strict-20261107-r09-world_3)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-a*x - b*y",
      "ay": "c*x + d*y"
    },
    "fitted_parameters": {
      "a": 0.0599999999916008,
      "b": -0.03464101614242489,
      "c": 0.034641016139090826,
      "d": -0.09999999998358576
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

运行：`e5-qwen38-strict-20261107-r09-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-strict-20261107-r09-world_4)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-G*q('charge')*x/(x*x+y*y)",
      "ay": "-G*q('charge')*y/(x*x+y*y)"
    },
    "fitted_parameters": {
      "G": 0.16862614753412716
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

运行：`e5-qwen38-strict-20261107-r09-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-strict-20261107-r09-world_5)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_6

运行：`e5-qwen38-strict-20261107-r09-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-strict-20261107-r09-world_6)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-d*x*sqrt(x*x+y*y)",
      "ay": "-d*y*sqrt(x*x+y*y)"
    },
    "fitted_parameters": {
      "d": 0.05381206484004941
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
