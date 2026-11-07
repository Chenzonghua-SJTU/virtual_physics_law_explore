# v15 六世界自主探索 Baseline

实验：`e6-qwen38-recovery-baseline-20261107-r02`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 None，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 5 | 74276 | 3125 | 625 | 5 | 97.5 | 0.00150168 | 51.0241 | 3.62076 | 1136 | 0 | 60.2305 |
| world_2 | submitted / submission_accepted_locally | 5 | 65966 | 2705 | 541 | 4 | 20.6511 | 2.49277 | 43.6932 | 1.76842 | 1007 | 0 | 50.2682 |
| world_3 | submitted / submission_accepted_locally | 21 | 1249029 | 7971 | 379.571 | 7 | 96.5 | 4.22115e-08 | 223.787 | 2.55038 | 1550 | 0 | 227.34 |
| world_4 | submitted / submission_accepted_locally | 18 | 471174 | 6017 | 334.278 | 8 | 43.9143 | 2.04092 | 106.716 | 4.5213 | 1875 | 0 | 111.875 |
| world_5 | submitted / submission_accepted_locally | 23 | 1062733 | 9260 | 402.609 | 8 | 5.75038 | 8.39325 | 192.645 | 2.71918 | 2007 | 0 | 199.511 |
| world_6 | submitted / submission_accepted_locally | 13 | 486144 | 10829 | 833 | 4 | 21.1005 | 3.31247 | 254.056 | 13.6326 | 2440 | 0 | 272.616 |

## 逐世界记录

### world_1

运行：`e6-qwen38-recovery-baseline-20261107-r02-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-recovery-baseline-20261107-r02-world_1)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-p*(q('charge')/q('mass'))*x/(x*x+y*y)",
      "ay": "-p*(q('charge')/q('mass'))*y/(x*x+y*y)"
    },
    "fitted_parameters": {
      "p": 0.07955596439936335
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

运行：`e6-qwen38-recovery-baseline-20261107-r02-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-recovery-baseline-20261107-r02-world_2)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-k*x",
      "ay": "-k*y"
    },
    "fitted_parameters": {
      "k": 0.0599999994550875
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

运行：`e6-qwen38-recovery-baseline-20261107-r02-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-recovery-baseline-20261107-r02-world_3)

```json
{
  "law": {
    "law_id": "law_7",
    "law_spec": {
      "ax": "-k11*x-k12*y-d*vx",
      "ay": "-k21*x-k22*y-d*vy"
    },
    "fitted_parameters": {
      "k11": 0.05999999937317549,
      "k12": -0.03464101590644177,
      "k21": -0.03464101528480235,
      "k22": 0.09999999961545973,
      "d": -2.4106061261429613e-10
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

运行：`e6-qwen38-recovery-baseline-20261107-r02-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-recovery-baseline-20261107-r02-world_4)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "sum_b(-k*q('charge')/q('mass')*(x-bx)/sqrt((x-bx)**2+(y-by)**2)**3)",
      "ay": "sum_b(-k*q('charge')/q('mass')*(y-by)/sqrt((x-bx)**2+(y-by)**2)**3)"
    },
    "fitted_parameters": {
      "k": 0.29703958703967914
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

### world_5

运行：`e6-qwen38-recovery-baseline-20261107-r02-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-recovery-baseline-20261107-r02-world_5)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-p1*x/sqrt(x**2+y**2)/((x**2+y**2))",
      "ay": "-p1*y/sqrt(x**2+y**2)/((x**2+y**2))"
    },
    "fitted_parameters": {
      "p1": 0.23880004683142456
    }
  },
  "claims": {
    "dynamics_order": 2,
    "hidden_matter": true,
    "time_dependence": true
  },
  "evaluation_error": null,
  "evaluation_failures": []
}
```

### world_6

运行：`e6-qwen38-recovery-baseline-20261107-r02-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-recovery-baseline-20261107-r02-world_6)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "sum_b(k*(bx-x)/((x-bx)*(x-bx)+(y-by)*(y-by))*sqrt((x-bx)*(x-bx)+(y-by)*(y-by)))",
      "ay": "sum_b(k*(by-y)/((x-bx)*(x-bx)+(y-by)*(y-by))*sqrt((x-bx)*(x-bx)+(y-by)*(y-by)))"
    },
    "fitted_parameters": {
      "k": 0.0323064634073905
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
