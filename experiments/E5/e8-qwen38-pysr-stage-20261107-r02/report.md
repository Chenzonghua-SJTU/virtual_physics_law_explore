# v15 六世界自主探索 Baseline

实验：`e8-qwen38-pysr-stage-20261107-r02`；归档：E8；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 None，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 15 | 479980 | 5218 | 347.867 | 8 | 53.4151 | 2.08847 | 129.763 | 3.56983 | 1187 | 0 | 135.103 |
| world_2 | submitted / submission_accepted_locally | 7 | 130964 | 3454 | 493.429 | 7 | 96.5 | 4.01538e-08 | 57.4256 | 1.7174 | 1229 | 0 | 61.6051 |
| world_3 | submitted / submission_accepted_locally | 10 | 355951 | 2818 | 281.8 | 8 | 96 | 4.4511e-08 | 92.4356 | 2.4689 | 656 | 0 | 97.0769 |
| world_4 | submitted / deadline_saved_draft | 32 | 1560949 | 13047 | 407.719 | 7 | 15 | — | 274.15 | 4.17101 | 1248 | 0 | 278.979 |
| world_5 | submitted / deadline_saved_draft | 23 | 1452907 | 10328 | 449.043 | 10 | 64.3331 | 0.64393 | 271.109 | 2.76923 | 1412 | 0 | 276.033 |
| world_6 | submitted / submission_accepted_locally | 20 | 1215501 | 9168 | 458.4 | 7 | 96.5 | 3.91581e-08 | 232.145 | 3.5201 | 1732 | 0 | 238.362 |

## 逐世界记录

### world_1

运行：`e8-qwen38-pysr-stage-20261107-r02-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r02-world_1)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "x * sin(c1 / (x * x + y * y))",
      "ay": "sin(y * sin(c2 / (x * x + y * y)))"
    },
    "fitted_parameters": {
      "c1": -0.07955917342635614,
      "c2": -0.07957212056887676
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

运行：`e8-qwen38-pysr-stage-20261107-r02-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r02-world_2)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-k*q('charge')*x/q('mass')",
      "ay": "-k*q('charge')*y/q('mass')"
    },
    "fitted_parameters": {
      "k": 0.05999999997748424
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

运行：`e8-qwen38-pysr-stage-20261107-r02-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r02-world_3)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "(-x + y * c1) * c2",
      "ay": "(x * c3 + y) * c4"
    },
    "fitted_parameters": {
      "c1": 0.5773502653452351,
      "c2": 0.05999999995559325,
      "c3": -0.34641016254956364,
      "c4": -0.09999999952606321
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

运行：`e8-qwen38-pysr-stage-20261107-r02-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r02-world_4)

```json
{
  "law": {
    "law_id": "law_19",
    "law_spec": {
      "ax": "-G * x / (x * x + y * y + C)",
      "ay": "-G * y / (x * x + y * y + C)"
    },
    "fitted_parameters": {
      "G": 0.1458745356108536,
      "C": -0.9832046818514848
    }
  },
  "claims": {
    "dynamics_order": 2,
    "hidden_matter": false,
    "time_dependence": false
  },
  "evaluation_error": null,
  "evaluation_failures": [
    {
      "probe_id": "v15_b0-s0_1",
      "stage": "candidate_rollout",
      "reason": "integration failed: Required step size is less than spacing between numbers."
    },
    {
      "probe_id": "v15_b0-s0_2",
      "stage": "candidate_rollout",
      "reason": "integration failed: Required step size is less than spacing between numbers."
    },
    {
      "probe_id": "v15_b0-s1_1",
      "stage": "candidate_rollout",
      "reason": "integration failed: Required step size is less than spacing between numbers."
    },
    {
      "probe_id": "v15_b0-s1_2",
      "stage": "candidate_rollout",
      "reason": "integration failed: Required step size is less than spacing between numbers."
    }
  ]
}
```

### world_5

运行：`e8-qwen38-pysr-stage-20261107-r02-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r02-world_5)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "-(c1*x + c2*x*x*x + c3*x*y*y)",
      "ay": "-(c4*y + c5*x*x*y)"
    },
    "fitted_parameters": {
      "c1": 0.060012007743098714,
      "c2": 0.0019979970617409705,
      "c3": 0.011986644689854093,
      "c4": 0.10027367945184561,
      "c5": 0.012526951007539623
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

运行：`e8-qwen38-pysr-stage-20261107-r02-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e8-qwen38-pysr-stage-20261107-r02-world_6)

```json
{
  "law": {
    "law_id": "law_7",
    "law_spec": {
      "ax": "-c1*x+c2*x*sin(c3*t+c4)-c5*y*cos(c3*t+c4)",
      "ay": "-c1*y-c2*y*sin(c3*t+c4)-c5*x*cos(c3*t+c4)"
    },
    "fitted_parameters": {
      "c1": 0.1200000000869056,
      "c2": 0.059999999541967386,
      "c3": 0.3926990817884029,
      "c4": 2.170796321159652,
      "c5": 0.060000000275557755
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

## 世界 4、5 失败复核

科学实现冻结于 `174dff5`。以下是对既有记录的分析，不是追加的自主探索，不修改上述原始成绩。

- [世界 4 详细证据](failure-world4.md)：指数算子从首阶段已启用；穿心粗采样的速度差分局部不稳定，搜索没有交付正确指数衰减式。Agent 未拟合三个完整 SR 候选，后续缩小训练集，最终公式在半径约 0.992 处存在极点；已有观测足以反证。独立测评 24 条轨迹中 4 条预测积分失败，15 分不能解释为预测成功。
- [世界 5 详细证据](failure-world5.md)：完整三次结构已经出现在通用回归分支及 PySR 的等价单轴表达式中。单轴 Pareto 筛选早于联合共享参数，丢失了可压缩为五参数的展开写法；Agent 手工补项时又使用六参数而被拒绝。仅在已有观测上重放共享及拟合，完整五参数式的训练/原验证位置 RMSE 分别为 7.97e-9/6.56e-9。这是定位候选交付缺陷的诊断，不是新的自主 baseline 或重新计算的比赛分数。

下一步优先修复联合参数共享之前的候选保留、局部差分质量及全部已获观测一致性反馈；不增加世界专用公式，不降低指数或三角算子优先级。本次分析提交尚未实施这些生产修复。
