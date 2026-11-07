# v15 六世界自主探索 Baseline

实验：`e8-qwen38-pysr-stage-20261107-r01`；归档：E8；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 None，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 7 | 146374 | 2899 | 414.143 | 6 | 92 | 0.00154525 | 73.4594 | 3.51954 | 1156 | 0 | 78.0038 |
| world_2 | submitted / submission_accepted_locally | 10 | 236385 | 3978 | 397.8 | 8 | 91 | 3.95711e-08 | 107.992 | 1.71798 | 1164 | 0 | 111.425 |
| world_3 | submitted / submission_accepted_locally | 6 | 180599 | 3081 | 513.5 | 6 | 97 | 2.64008e-08 | 95.6984 | 2.46818 | 1085 | 0 | 98.8444 |
| world_4 | submitted / submission_accepted_locally | 13 | 524680 | 7099 | 546.077 | 10 | 28.9825 | 3.13895 | 165.927 | 4.02061 | 1418 | 0 | 170.532 |
| world_5 | submitted / submission_accepted_locally | 16 | 929962 | 6539 | 408.688 | 8 | 25.2312 | 1.68418 | 186.377 | 2.66844 | 1382 | 0 | 190.416 |
| world_6 | submitted / submission_accepted_locally | 9 | 286742 | 3123 | 347 | 10 | 15 | 55923 | 98.0154 | 3.3699 | 964 | 0 | 103.552 |

## 逐世界记录

### world_1

运行：`e8-qwen38-pysr-stage-20261107-r01-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r01-world_1)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-c * q('charge') / q('mass') * x / (x * x + y * y)",
      "ay": "-c * q('charge') / q('mass') * y / (x * x + y * y)"
    },
    "fitted_parameters": {
      "c": 0.07955964041046466
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

运行：`e8-qwen38-pysr-stage-20261107-r01-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r01-world_2)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-k*(q('charge')/q('mass'))*x",
      "ay": "-k*(q('charge')/q('mass'))*y"
    },
    "fitted_parameters": {
      "k": 0.06
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

运行：`e8-qwen38-pysr-stage-20261107-r01-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r01-world_3)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "(x - c1 * y) * c2",
      "ay": "(x * c3 + y) * c4"
    },
    "fitted_parameters": {
      "c1": 0.5773502692562412,
      "c2": -0.05999999999617922,
      "c3": -0.3464101614404007,
      "c4": -0.10000000000317354
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

运行：`e8-qwen38-pysr-stage-20261107-r01-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r01-world_4)

```json
{
  "law": {
    "law_id": "law_4",
    "law_spec": {
      "ax": "-C * q('charge') / q('mass') * x / (x * x + y * y)",
      "ay": "-C * q('charge') / q('mass') * y / (x * x + y * y)"
    },
    "fitted_parameters": {
      "C": 0.20326094666132657
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

运行：`e8-qwen38-pysr-stage-20261107-r01-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r01-world_5)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "(-kx0 - c1 * t) * x",
      "ay": "(-ky0 - c2 * t) * y"
    },
    "fitted_parameters": {
      "kx0": 0.06499441009585138,
      "ky0": 0.10544311130269898,
      "c1": 0.007816366385849904,
      "c2": 0.009248767433840756
    }
  },
  "claims": {
    "dynamics_order": 2,
    "hidden_matter": false,
    "time_dependence": true
  },
  "evaluation_error": null,
  "evaluation_failures": []
}
```

### world_6

运行：`e8-qwen38-pysr-stage-20261107-r01-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r01-world_6)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "(x - (vx + y * c1)) * c2",
      "ay": "(y + (x + y) * (t * c3 - c4)) * c5"
    },
    "fitted_parameters": {
      "c1": 0.6311034951804915,
      "c2": -0.07693133588389169,
      "c3": -0.08057770095123429,
      "c4": 0.16740088336972792,
      "c5": -0.2037679727859308
    }
  },
  "claims": {
    "dynamics_order": 2,
    "hidden_matter": false,
    "time_dependence": true
  },
  "evaluation_error": null,
  "evaluation_failures": []
}
```

时间戳为 UTC；完整预算、真实模型回复、实验与候选版本保存在各运行目录。
