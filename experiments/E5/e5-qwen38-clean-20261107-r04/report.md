# v15 六世界自主探索 Baseline

实验：`e5-qwen38-clean-20261107-r04`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 12 | 316896 | 4885 | 407.083 | 8 | 53.406 | 2.08894 | 84.4278 | 3.47009 | 1693 | 0 | 91.2269 |
| world_2 | submitted / submission_accepted_locally | 4 | 61625 | 2784 | 696 | 6 | 92 | 5.26082e-08 | 45.5984 | 1.76804 | 1487 | 0 | 50.5541 |
| world_3 | incomplete / wall_time_exhausted | 14 | 657890 | 13902 | — | 8 | — | — | 295.541 | — | 4096 | 0 | 301.219 |
| world_4 | submitted / submission_accepted_locally | 8 | 164632 | 3450 | 431.25 | 6 | 44.0204 | 2.3205 | 61.1533 | 4.22027 | 997 | 0 | 70.8645 |
| world_5 | incomplete / wall_time_exhausted | 15 | 662160 | 11784 | — | 8 | — | — | 295.391 | — | 4096 | 0 | 297.075 |
| world_6 | submitted / submission_accepted_locally | 19 | 1098139 | 11617 | 611.421 | 10 | 17.5143 | 4.12949 | 211.757 | 3.32458 | 1984 | 0 | 220.131 |

## 逐世界记录

### world_1

运行：`e5-qwen38-clean-20261107-r04-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-clean-20261107-r04-world_1)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-c*x/(x*x+y*y)",
      "ay": "-c*y/(x*x+y*y)"
    },
    "fitted_parameters": {
      "c": 0.07948761825913807
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

运行：`e5-qwen38-clean-20261107-r04-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-clean-20261107-r04-world_2)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-k*q('charge')/q('mass')*x",
      "ay": "-k*q('charge')/q('mass')*y"
    },
    "fitted_parameters": {
      "k": 0.059999999714878065
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

运行：`e5-qwen38-clean-20261107-r04-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-clean-20261107-r04-world_3)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_4

运行：`e5-qwen38-clean-20261107-r04-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-clean-20261107-r04-world_4)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "sum_b(G*q('charge')*(bx-x)/sqrt((bx-x)**2+(by-y)**2)**3)",
      "ay": "sum_b(G*q('charge')*(by-y)/sqrt((bx-x)**2+(by-y)**2)**3)"
    },
    "fitted_parameters": {
      "G": 0.27591518265075504
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

运行：`e5-qwen38-clean-20261107-r04-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-clean-20261107-r04-world_5)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_6

运行：`e5-qwen38-clean-20261107-r04-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-clean-20261107-r04-world_6)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "-K1*x + K12*y - Om*vy",
      "ay": "K12*x - K3*y + Om*vx"
    },
    "fitted_parameters": {
      "K1": 0.08944644639609704,
      "K12": 0.046532153636482984,
      "K3": 0.1135374160264418,
      "Om": -0.014455395217539612
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
