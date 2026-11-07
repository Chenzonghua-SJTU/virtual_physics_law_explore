# v15 六世界自主探索 Baseline

实验：`e7-qwen38-pysr-off-20261107-r01`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 None，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 18 | 521208 | 6926 | 384.778 | 5 | 97.5 | 0.00149618 | 116.801 | 3.62069 | 1408 | 0 | 121.943 |
| world_2 | submitted / submission_accepted_locally | 7 | 129746 | 4100 | 585.714 | 4 | 98 | 1.16998e-07 | 66.1089 | 1.76956 | 1107 | 0 | 70.2599 |
| world_3 | submitted / submission_accepted_locally | 11 | 420453 | 6346 | 576.909 | 5 | 97.5 | 1.62783e-07 | 108.057 | 2.58824 | 1382 | 0 | 112.437 |
| world_4 | submitted / submission_accepted_locally | 16 | 405610 | 4467 | 279.188 | 7 | 70.0316 | 1.2311 | 77.1454 | 4.42028 | 914 | 0 | 83.4633 |
| world_5 | submitted / submission_accepted_locally | 21 | 1144041 | 11828 | 563.238 | 4 | 20.5007 | 2.10114 | 233.469 | 2.62213 | 1676 | 0 | 237.667 |
| world_6 | submitted / submission_accepted_locally | 17 | 804552 | 10925 | 642.647 | 4 | 19.1269 | 3.70505 | 278.355 | 14.9579 | 4096 | 0 | 294.39 |

## 逐世界记录

### world_1

运行：`e7-qwen38-pysr-off-20261107-r01-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e7-qwen38-pysr-off-20261107-r01-world_1)

```json
{
  "law": {
    "law_id": "law_7",
    "law_spec": {
      "ax": "-G*q('charge')/q('mass')*x/(x**2+y**2)",
      "ay": "-G*q('charge')/q('mass')*y/(x**2+y**2)"
    },
    "fitted_parameters": {
      "G": 0.07955498827057125
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

运行：`e7-qwen38-pysr-off-20261107-r01-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e7-qwen38-pysr-off-20261107-r01-world_2)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-c*q('charge')/q('mass')*x",
      "ay": "-c*q('charge')/q('mass')*y"
    },
    "fitted_parameters": {
      "c": 0.05999999889285631
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

运行：`e7-qwen38-pysr-off-20261107-r01-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e7-qwen38-pysr-off-20261107-r01-world_3)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "c1*x+c2*y",
      "ay": "c3*x+c4*y"
    },
    "fitted_parameters": {
      "c1": -0.06000000009944075,
      "c2": 0.034641017893101464,
      "c3": 0.03464101630951572,
      "c4": -0.10000000274247814
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

运行：`e7-qwen38-pysr-off-20261107-r01-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e7-qwen38-pysr-off-20261107-r01-world_4)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "-k*q('charge')/q('mass')*x/((x*x+y*y)*sqrt(x*x+y*y))",
      "ay": "-k*q('charge')/q('mass')*y/((x*x+y*y)*sqrt(x*x+y*y))"
    },
    "fitted_parameters": {
      "k": 0.3997288525430542
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

运行：`e7-qwen38-pysr-off-20261107-r01-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e7-qwen38-pysr-off-20261107-r01-world_5)

```json
{
  "law": {
    "law_id": "law_6",
    "law_spec": {
      "ax": "-kx*x",
      "ay": "-ky*y"
    },
    "fitted_parameters": {
      "kx": 0.06586038236401728,
      "ky": 0.1178532480949151
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

运行：`e7-qwen38-pysr-off-20261107-r01-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e7-qwen38-pysr-off-20261107-r01-world_6)

```json
{
  "law": {
    "law_id": "law_5",
    "law_spec": {
      "ax": "sum_b(G1*(bx-x)/sqrt((bx-x)**2+(by-y)**2)) + dx*vx",
      "ay": "sum_b(G1*(by-y)/sqrt((bx-x)**2+(by-y)**2)) + dy*vy"
    },
    "fitted_parameters": {
      "G1": 0.06332921166346774,
      "dx": -0.19263232705371885,
      "dy": -0.22728566335611292
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
