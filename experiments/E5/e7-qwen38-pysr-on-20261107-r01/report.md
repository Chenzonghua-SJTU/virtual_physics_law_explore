# v15 六世界自主探索 Baseline

实验：`e7-qwen38-pysr-on-20261107-r01`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 None，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 7 | 126388 | 3461 | 494.429 | 6 | 96.9999 | 0.00268042 | 57.5644 | 3.5703 | 1259 | 0 | 62.4236 |
| world_2 | submitted / submission_accepted_locally | 32 | 2006122 | 6907 | 215.844 | 8 | 21.6285 | 2.36883 | 214.535 | 2.26811 | 795 | 0 | 219.029 |
| world_3 | submitted / submission_accepted_locally | 13 | 584572 | 3604 | 277.231 | 10 | 15.9366 | 8.62838 | 175.251 | 19.0391 | 598 | 0 | 196.327 |
| world_4 | incomplete / model_finish_length_recovery_exhausted | 12 | 346586 | 14268 | 1189 | 6 | — | — | 264.62 | — | 4096 | 0 | 266.972 |
| world_5 | submitted / submission_accepted_locally | 12 | 640934 | 4000 | 333.333 | 8 | 33.7744 | 1.47488 | 76.9549 | 2.58211 | 1161 | 0 | 80.7141 |
| world_6 | submitted / submission_accepted_locally | 13 | 494369 | 3043 | 234.077 | 3 | 15.7606 | 4.77304 | 136.241 | 31.0755 | 696 | 0 | 169.422 |

## 逐世界记录

### world_1

运行：`e7-qwen38-pysr-on-20261107-r01-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e7-qwen38-pysr-on-20261107-r01-world_1)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-G*q('charge')/q('mass')*x/(x**2+y**2)",
      "ay": "-G*q('charge')/q('mass')*y/(x**2+y**2)"
    },
    "fitted_parameters": {
      "G": 0.07951878277752715
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

运行：`e7-qwen38-pysr-on-20261107-r01-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e7-qwen38-pysr-on-20261107-r01-world_2)

```json
{
  "law": {
    "law_id": "law_15",
    "law_spec": {
      "ax": "-p1*sum_b(x/(x*x+y*y)*sqrt(x*x+y*y))*q('charge')/q('mass')",
      "ay": "-p1*sum_b(y/(x*x+y*y)*sqrt(x*x+y*y))*q('charge')/q('mass')"
    },
    "fitted_parameters": {
      "p1": 0.17716423123648542
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

运行：`e7-qwen38-pysr-on-20261107-r01-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e7-qwen38-pysr-on-20261107-r01-world_3)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "-G*sum_b( (x-bx)/( (x-bx)**2 + (y-by)**2 + s )*( (x-bx)**2 + (y-by)**2 + s )**-1)",
      "ay": "-G*sum_b( (y-by)/( (x-bx)**2 + (y-by)**2 + s )*( (x-bx)**2 + (y-by)**2 + s )**-1)"
    },
    "fitted_parameters": {
      "G": 0.27934899196806473,
      "s": 0.3057404786288644
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

运行：`e7-qwen38-pysr-on-20261107-r01-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e7-qwen38-pysr-on-20261107-r01-world_4)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_5

运行：`e7-qwen38-pysr-on-20261107-r01-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e7-qwen38-pysr-on-20261107-r01-world_5)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "k1*x",
      "ay": "k2*y"
    },
    "fitted_parameters": {
      "k1": -0.08761306843608621,
      "k2": -0.12380047565473282
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

运行：`e7-qwen38-pysr-on-20261107-r01-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e7-qwen38-pysr-on-20261107-r01-world_6)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "sum_b(G*(bx-x)/(sqrt((bx-x)**2+(by-y)**2+eps)**3))",
      "ay": "sum_b(G*(by-y)/(sqrt((bx-x)**2+(by-y)**2+eps)**3))"
    },
    "fitted_parameters": {
      "G": 1.9206066429891593,
      "eps": 1.0439539736098726
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
