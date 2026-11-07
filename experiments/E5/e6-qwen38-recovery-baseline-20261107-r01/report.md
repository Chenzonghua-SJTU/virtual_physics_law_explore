# v15 六世界自主探索 Baseline

实验：`e6-qwen38-recovery-baseline-20261107-r01`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 None，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 32 | 1294859 | 12032 | 376 | 7 | 96.4999 | 0.00167298 | 212.178 | 3.57022 | 1593 | 0 | 221.207 |
| world_2 | submitted / submission_accepted_locally | 6 | 80344 | 4000 | 666.667 | 4 | 98 | 3.95274e-08 | 64.1194 | 1.7673 | 1605 | 0 | 70.6193 |
| world_3 | submitted / submission_accepted_locally | 13 | 483787 | 3805 | 292.692 | 5 | 17.5082 | 5.2201 | 113.753 | 2.44192 | 1060 | 0 | 121.613 |
| world_4 | submitted / submission_accepted_locally | 16 | 453038 | 10313 | 644.562 | 8 | 88.8349 | 0.549133 | 167.738 | 4.12026 | 1972 | 0 | 172.899 |
| world_5 | submitted / submission_accepted_locally | 8 | 205808 | 3917 | 489.625 | 4 | 32.3709 | 1.55078 | 66.0027 | 2.61869 | 1592 | 0 | 71.4389 |
| world_6 | submitted / submission_accepted_locally | 8 | 267938 | 7370 | 921.25 | 4 | 17.0025 | 4.2928 | 145.577 | 3.3199 | 2495 | 0 | 153.456 |

## 逐世界记录

### world_1

运行：`e6-qwen38-recovery-baseline-20261107-r01-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-recovery-baseline-20261107-r01-world_1)

```json
{
  "law": {
    "law_id": "law_6",
    "law_spec": {
      "ax": "-k*q('charge')/q('mass')*x/(x**2+y**2)",
      "ay": "-k*q('charge')/q('mass')*y/(x**2+y**2)"
    },
    "fitted_parameters": {
      "k": 0.07956518350101306
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

运行：`e6-qwen38-recovery-baseline-20261107-r01-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-recovery-baseline-20261107-r01-world_2)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "(-k*q('charge')/q('mass'))*x",
      "ay": "(-k*q('charge')/q('mass'))*y"
    },
    "fitted_parameters": {
      "k": 0.060000000001855805
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

运行：`e6-qwen38-recovery-baseline-20261107-r01-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-recovery-baseline-20261107-r01-world_3)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-a1*vx/a0 - a2*vy/a0",
      "ay": "-a1*vy/a0 + a2*vx/a0"
    },
    "fitted_parameters": {
      "a0": 2.886136799415813,
      "a1": 0.3908014849373322,
      "a2": 0.13159297439258968
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

运行：`e6-qwen38-recovery-baseline-20261107-r01-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-recovery-baseline-20261107-r01-world_4)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "(q('charge')/q('mass'))*(-G*x/((x*x+y*y+s)*sqrt(x*x+y*y+s)))",
      "ay": "(q('charge')/q('mass'))*(-G*y/((x*x+y*y+s)*sqrt(x*x+y*y+s)))"
    },
    "fitted_parameters": {
      "G": 0.5055376763179171,
      "s": 0.7818796333748834
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

运行：`e6-qwen38-recovery-baseline-20261107-r01-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-recovery-baseline-20261107-r01-world_5)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-w2*x",
      "ay": "-w2*y"
    },
    "fitted_parameters": {
      "w2": 0.10975394390349136
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

运行：`e6-qwen38-recovery-baseline-20261107-r01-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-recovery-baseline-20261107-r01-world_6)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "a11*x + a12*y",
      "ay": "a21*x + a22*y"
    },
    "fitted_parameters": {
      "a11": -0.07469558838826654,
      "a12": 0.03899783628067424,
      "a21": 0.03906091392477181,
      "a22": -0.16530720188868425
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
