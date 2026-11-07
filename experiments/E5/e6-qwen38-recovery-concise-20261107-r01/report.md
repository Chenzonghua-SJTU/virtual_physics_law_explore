# v15 六世界自主探索 Baseline

实验：`e6-qwen38-recovery-concise-20261107-r01`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 None，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 8 | 170096 | 4071 | 508.875 | 5 | 53.4082 | 2.08882 | 68.7186 | 3.56999 | 1146 | 0 | 75.3547 |
| world_2 | submitted / submission_accepted_locally | 7 | 119243 | 4047 | 578.143 | 10 | 95 | 4.20693e-08 | 64.9896 | 1.76769 | 945 | 0 | 70.4252 |
| world_3 | submitted / submission_accepted_locally | 9 | 264835 | 5542 | 615.778 | 10 | 95 | 2.69457e-08 | 91.8757 | 2.51826 | 1298 | 0 | 95.8021 |
| world_4 | submitted / submission_accepted_locally | 13 | 487031 | 11038 | 849.077 | 9 | 91.4564 | 0.403957 | 184.539 | 4.37452 | 2398 | 0 | 192.173 |
| world_5 | submitted / submission_accepted_locally | 20 | 1116494 | 5869 | 293.45 | 5 | 27.1281 | 1.93206 | 134.211 | 2.61809 | 1398 | 0 | 142.335 |
| world_6 | submitted / submission_accepted_locally | 14 | 583874 | 4166 | 297.571 | 10 | 11.2292 | 10.6437 | 82.8741 | 3.26921 | 1088 | 0 | 86.9217 |

## 逐世界记录

### world_1

运行：`e6-qwen38-recovery-concise-20261107-r01-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-recovery-concise-20261107-r01-world_1)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-k*x/(x**2+y**2)",
      "ay": "-k*y/(x**2+y**2)"
    },
    "fitted_parameters": {
      "k": 0.0795045545075704
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

运行：`e6-qwen38-recovery-concise-20261107-r01-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-recovery-concise-20261107-r01-world_2)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-(k*q('charge')/q('mass'))*x",
      "ay": "-(k*q('charge')/q('mass'))*y"
    },
    "fitted_parameters": {
      "k": 0.0599999999196218
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

运行：`e6-qwen38-recovery-concise-20261107-r01-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-recovery-concise-20261107-r01-world_3)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "a11*x + a12*y",
      "ay": "a21*x + a22*y"
    },
    "fitted_parameters": {
      "a11": -0.05999999999987509,
      "a12": 0.034641016138994604,
      "a21": 0.03464101615117742,
      "a22": -0.09999999997818951
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

运行：`e6-qwen38-recovery-concise-20261107-r01-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-recovery-concise-20261107-r01-world_4)

```json
{
  "law": {
    "law_id": "law_4",
    "law_spec": {
      "ax": "sum_b(-A*q('charge')/q('mass')*(x-bx)/(( (x-bx)**2+(y-by)**2+B)*sqrt((x-bx)**2+(y-by)**2)))",
      "ay": "sum_b(-A*q('charge')/q('mass')*(y-by)/(( (x-bx)**2+(y-by)**2+B)*sqrt((x-bx)**2+(y-by)**2)))"
    },
    "fitted_parameters": {
      "A": 0.4910584142836662,
      "B": 0.9803538505208212
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

运行：`e6-qwen38-recovery-concise-20261107-r01-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-recovery-concise-20261107-r01-world_5)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "-p1*x",
      "ay": "-p2*y"
    },
    "fitted_parameters": {
      "p1": 0.07220671373091184,
      "p2": 0.11512565052238033
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

运行：`e6-qwen38-recovery-concise-20261107-r01-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-recovery-concise-20261107-r01-world_6)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "-G*x/sqrt((x*x+y*y+e)*(x*x+y*y+e)*(x*x+y*y+e))",
      "ay": "-G*y/sqrt((x*x+y*y+e)*(x*x+y*y+e)*(x*x+y*y+e))"
    },
    "fitted_parameters": {
      "G": 0.24578378512562887,
      "e": 0.9999999999995961
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
