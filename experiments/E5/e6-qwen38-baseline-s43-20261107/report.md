# v15 六世界自主探索 Baseline

实验：`e6-qwen38-baseline-s43-20261107`；归档：E5；规则：`e5`；编排状态：`interrupted`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 4 | 55052 | 2609 | 652.25 | 4 | 53.4164 | 2.0884 | 42.4902 | 3.53844 | 1197 | 0 | 50.5123 |
| world_2 | submitted / submission_accepted_locally | 8 | 179979 | 6516 | 814.5 | 6 | 97 | 1.0073e-07 | 106.469 | 1.82967 | 2496 | 0 | 111.606 |
| world_3 | submitted / submission_accepted_locally | 13 | 541194 | 6814 | 524.154 | 3 | 21.0111 | 3.29485 | 169.822 | 2.66855 | 1208 | 0 | 178.163 |
| world_4 | incomplete / model_finish_length | 9 | 234018 | 9803 | 1089.22 | 3 | — | — | 162.97 | — | 4096 | 0 | 167.911 |
| world_5 | submitted / submission_accepted_locally | 14 | 575721 | 7685 | 548.929 | 6 | 17.2815 | 2.58098 | 158.402 | 2.58896 | 1521 | 0 | 163.38 |
| world_6 | stopped / baseline_driver_interrupted | 11 | 322633 | 3668 | — | 4 | — | — | 64.3647 | — | 772 | 0 | 102.257 |

## 逐世界记录

### world_1

运行：`e6-qwen38-baseline-s43-20261107-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-baseline-s43-20261107-world_1)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-k*x/(x*x+y*y)",
      "ay": "-k*y/(x*x+y*y)"
    },
    "fitted_parameters": {
      "k": 0.07956586845898247
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

运行：`e6-qwen38-baseline-s43-20261107-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-baseline-s43-20261107-world_2)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "-q('charge')/q('mass')*k0*x",
      "ay": "-q('charge')/q('mass')*k0*y"
    },
    "fitted_parameters": {
      "k0": 0.05999999908486024
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

运行：`e6-qwen38-baseline-s43-20261107-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-baseline-s43-20261107-world_3)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "-A*x/sqrt(x**2+y**2)",
      "ay": "-A*y/sqrt(x**2+y**2)"
    },
    "fitted_parameters": {
      "A": 0.14885312823550312
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

运行：`e6-qwen38-baseline-s43-20261107-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-baseline-s43-20261107-world_4)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

### world_5

运行：`e6-qwen38-baseline-s43-20261107-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-baseline-s43-20261107-world_5)

```json
{
  "law": {
    "law_id": "law_3",
    "law_spec": {
      "ax": "-c*x",
      "ay": "-c*y"
    },
    "fitted_parameters": {
      "c": 0.07092974190395666
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

运行：`e6-qwen38-baseline-s43-20261107-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e6-qwen38-baseline-s43-20261107-world_6)

```json
{
  "law": null,
  "claims": null,
  "evaluation_error": null,
  "evaluation_failures": null
}
```

时间戳为 UTC；完整预算、真实模型回复、实验与候选版本保存在各运行目录。
