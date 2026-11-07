# v15 六世界自主探索 Baseline

实验：`e5-qwen38-hs-seed44-20261107-r15`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 14 | 353954 | 2589 | 184.929 | 5 | 45.4093 | 2.56335 | 49.684 | 3.61937 | 1064 | 0 | 55.4133 |
| world_2 | submitted / submission_accepted_locally | 8 | 168351 | 3446 | 430.75 | 5 | 97.5 | 5.97252e-08 | 60.7841 | 1.71714 | 1472 | 0 | 65.503 |
| world_3 | submitted / submission_accepted_locally | 7 | 167273 | 1702 | 243.143 | 4 | 98 | 2.64629e-08 | 32.2927 | 2.51892 | 868 | 0 | 35.4227 |
| world_4 | submitted / submission_accepted_locally | 26 | 1674359 | 8760 | 336.923 | 8 | 44.1145 | 2.0305 | 196.583 | 4.02063 | 1178 | 0 | 203.922 |
| world_5 | incomplete / wall_time_exhausted | 56 | 2297752 | 17413 | — | 8 | — | — | 295.335 | — | 379 | 0 | 296.614 |
| world_6 | submitted / submission_accepted_locally | 20 | 991515 | 5205 | 260.25 | 6 | 12.1587 | 4.24117 | 105.922 | 3.26965 | 538 | 0 | 112.839 |

## 逐世界记录

### world_1

运行：`e5-qwen38-hs-seed44-20261107-r15-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-hs-seed44-20261107-r15-world_1)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-g/q('mass')/((x**2+y**2)*sqrt(x**2+y**2))*x",
      "ay": "-g/q('mass')/((x**2+y**2)*sqrt(x**2+y**2))*y"
    },
    "fitted_parameters": {
      "g": 0.20887956337597002
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

运行：`e5-qwen38-hs-seed44-20261107-r15-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-hs-seed44-20261107-r15-world_2)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-c0*q('charge')/q('mass')*x",
      "ay": "-c0*q('charge')/q('mass')*y"
    },
    "fitted_parameters": {
      "c0": 0.059999999607306065
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

运行：`e5-qwen38-hs-seed44-20261107-r15-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-hs-seed44-20261107-r15-world_3)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "c0*x+c1*y",
      "ay": "c2*x+c3*y"
    },
    "fitted_parameters": {
      "c0": -0.06000000000206566,
      "c1": 0.034641016151618416,
      "c2": 0.03464101615476328,
      "c3": -0.100000000000421
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

运行：`e5-qwen38-hs-seed44-20261107-r15-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-hs-seed44-20261107-r15-world_4)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-c0*q('charge')*x/(x**2+y**2+c1)*1/sqrt(x**2+y**2+c1)",
      "ay": "-c0*q('charge')*y/(x**2+y**2+c1)*1/sqrt(x**2+y**2+c1)"
    },
    "fitted_parameters": {
      "c0": 0.3245852625877489,
      "c1": 0.1869592188979292
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

运行：`e5-qwen38-hs-seed44-20261107-r15-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-hs-seed44-20261107-r15-world_5)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_6

运行：`e5-qwen38-hs-seed44-20261107-r15-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-hs-seed44-20261107-r15-world_6)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "p0+p1*x+p2*y",
      "ay": "p3*x+p4*y"
    },
    "fitted_parameters": {
      "p0": -0.0011856668004814577,
      "p1": -0.08532771067918153,
      "p2": 0.046458676706011504,
      "p3": 0.04688339969569281,
      "p4": -0.15553474934797276
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

时间戳为 UTC；完整预算、真实模型回复、实验与候选版本保存在各运行目录。
