# v15 六世界自主探索 Baseline

实验：`e7-qwen38-pysr-power-20261107-r01`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 None，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 14 | 386518 | 10056 | 718.286 | 9 | 90.4999 | 0.00173162 | 188.586 | 3.60867 | 2047 | 0 | 193.31 |
| world_2 | submitted / submission_accepted_locally | 9 | 149288 | 3062 | 340.222 | 10 | 95 | 8.77095e-08 | 74.4646 | 1.76767 | 1142 | 0 | 80.9667 |
| world_3 | submitted / submission_accepted_locally | 13 | 690151 | 4405 | 338.846 | 8 | 19.355 | 3.91402 | 86.0196 | 3.0696 | 1042 | 0 | 91.1254 |
| world_4 | submitted / saved_draft_after_http_status_400 | 12 | 221292 | 11756 | — | 9 | 27.8491 | 4.00243 | 217.342 | 4.47333 | 4096 | 0 | 224.079 |
| world_5 | submitted / submission_accepted_locally | 18 | 881867 | 7600 | 422.222 | 8 | 32.1813 | 1.56167 | 182.954 | 2.86916 | 1835 | 0 | 189.328 |
| world_6 | submitted / submission_accepted_locally | 11 | 314550 | 3686 | 335.091 | 6 | 23.7461 | 2.91897 | 139.598 | 13.1861 | 876 | 0 | 153.527 |

## 逐世界记录

### world_1

运行：`e7-qwen38-pysr-power-20261107-r01-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e7-qwen38-pysr-power-20261107-r01-world_1)

```json
{
  "law": {
    "law_id": "law_6",
    "law_spec": {
      "ax": "-k*q('charge')*x/(q('mass')*(x*x+y*y))",
      "ay": "-k*q('charge')*y/(q('mass')*(x*x+y*y))"
    },
    "fitted_parameters": {
      "k": 0.0795670866689815
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

### world_2

运行：`e7-qwen38-pysr-power-20261107-r01-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e7-qwen38-pysr-power-20261107-r01-world_2)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "x * q('charge') * c1 / q('mass')",
      "ay": "y * q('charge') * c2 / q('mass')"
    },
    "fitted_parameters": {
      "c1": -0.059999999190504145,
      "c2": -0.05999999930243532
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

运行：`e7-qwen38-pysr-power-20261107-r01-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e7-qwen38-pysr-power-20261107-r01-world_3)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "p1*x/((x-b0)**2+(y-b1)**2)",
      "ay": "p2*y/((x-b0)**2+(y-b1)**2)"
    },
    "fitted_parameters": {
      "p1": -0.6000000149011612,
      "p2": -0.6,
      "b0": 0.0,
      "b1": 0.0
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

运行：`e7-qwen38-pysr-power-20261107-r01-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e7-qwen38-pysr-power-20261107-r01-world_4)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-A*sum_b((x - bx)*q('charge')/(q('mass')*((x - bx)**2 + (y - by)**2)))",
      "ay": "-A*sum_b((y - by)*q('charge')/(q('mass')*((x - bx)**2 + (y - by)**2)))"
    },
    "fitted_parameters": {
      "A": 0.24331009651725138
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

运行：`e7-qwen38-pysr-power-20261107-r01-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e7-qwen38-pysr-power-20261107-r01-world_5)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "x*(-a + b*x*x + c*y*y)",
      "ay": "y*(-a + c*x*x + b*y*y)"
    },
    "fitted_parameters": {
      "a": 0.06562672223856238,
      "b": -0.0015422118095634635,
      "c": -0.022364764637697383
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

运行：`e7-qwen38-pysr-power-20261107-r01-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e7-qwen38-pysr-power-20261107-r01-world_6)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "sum_b(-M * (x - bx) / ((x - bx)**2 + (y - by)**2) * sqrt((x - bx)**2 + (y - by)**2))",
      "ay": "sum_b(-M * (y - by) / ((x - bx)**2 + (y - by)**2) * sqrt((x - bx)**2 + (y - by)**2))"
    },
    "fitted_parameters": {
      "M": 0.03629084719104847
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
