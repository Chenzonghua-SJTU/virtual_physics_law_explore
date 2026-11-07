# v15 六世界自主探索 Baseline

实验：`e8-qwen38-pysr-stage-20261107-r09`；归档：E8；规则：`e4`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=开启；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 None，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 11 | 280616 | 3618 | 328.909 | 7 | 28.8977 | 4.37772 | 110.446 | 3.52073 | 642 | 0 | 115.133 |
| world_2 | submitted / submission_accepted_locally | 11 | 309900 | 3480 | 316.364 | 7 | 95.6678 | 0.100161 | 106.529 | 1.71805 | 923 | 0 | 108.871 |
| world_3 | submitted / submission_accepted_locally | 8 | 241764 | 2643 | 330.375 | 6 | 91.9896 | 0.010698 | 91.138 | 2.46852 | 746 | 0 | 94.305 |
| world_4 | submitted / submission_accepted_locally | 14 | 481478 | 4323 | 308.786 | 8 | 87.5282 | 0.372908 | 153.933 | 4.32052 | 916 | 0 | 159.422 |
| world_5 | submitted / submission_accepted_locally | 10 | 425394 | 5501 | 550.1 | 9 | 24.8199 | 2.18336 | 141.687 | 2.51829 | 1352 | 0 | 144.857 |
| world_6 | submitted / submission_accepted_locally | 18 | 974428 | 7920 | 440 | 8 | 10 | 57324.6 | 256.518 | 3.36983 | 1040 | 0 | 262.084 |

## 逐世界记录

### world_1

运行：`e8-qwen38-pysr-stage-20261107-r09-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r09-world_1)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "x * (q('charge') / q('mass')) * c1 / (x * x + y * y)",
      "ay": "(vx * (vy * c2 - 1 * c3) - (-c4 * vy - c5)) / sqrt(x * x + y * y)"
    },
    "fitted_parameters": {
      "c1": -0.07988110781243467,
      "c2": -0.2366397280456173,
      "c3": -0.39122652262118346,
      "c4": -0.0931350046811353,
      "c5": 0.02839983037715537
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

运行：`e8-qwen38-pysr-stage-20261107-r09-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r09-world_2)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "q('charge') / q('mass') * c1 * x",
      "ay": "q('charge') / q('mass') * c1 * y"
    },
    "fitted_parameters": {
      "c1": -0.05890162278913443
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

运行：`e8-qwen38-pysr-stage-20261107-r09-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r09-world_3)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "c1 * vy + c2 * x + c3 * y",
      "ay": "c4 * x + c5 * y"
    },
    "fitted_parameters": {
      "c1": -0.00015352192155056657,
      "c2": -0.060101724607300254,
      "c3": 0.034826884084866325,
      "c4": 0.03471632125233326,
      "c5": -0.10006599173595658
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

### world_4

运行：`e8-qwen38-pysr-stage-20261107-r09-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r09-world_4)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "q('charge') / q('mass') * c1 * exp(c2 * sqrt(sqrt(x * x + y * y))) * x / (c3 + x * x + y * y)",
      "ay": "q('charge') / q('mass') * c1 * exp(c2 * sqrt(sqrt(x * x + y * y))) * y / (c3 + x * x + y * y)"
    },
    "fitted_parameters": {
      "c1": -0.6115018961479286,
      "c2": -0.8085189284409465,
      "c3": 0.07262275427505756
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

运行：`e8-qwen38-pysr-stage-20261107-r09-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r09-world_5)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "c1 * x",
      "ay": "c2 * y"
    },
    "fitted_parameters": {
      "c1": -0.0664491293536566,
      "c2": -0.10789739359623116
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

运行：`e8-qwen38-pysr-stage-20261107-r09-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r09-world_6)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "c1 * x + c2 * y",
      "ay": "c3 * x + c4 * y + c5 * (t * y)"
    },
    "fitted_parameters": {
      "c1": -0.09520742691124132,
      "c2": 0.0496080349838047,
      "c3": 0.04980656051306675,
      "c4": -0.17296972151318174,
      "c5": 0.019843421224253498
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

时间戳为 UTC；完整预算、真实模型回复、实验与候选版本保存在各运行目录。
