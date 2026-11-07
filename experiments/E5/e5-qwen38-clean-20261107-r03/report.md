# v15 六世界自主探索 Baseline

实验：`e5-qwen38-clean-20261107-r03`；归档：E5；规则：`e5`；编排状态：`completed`。

模型 `qwen3.8-27b`；thinking=false；噪声=关闭；seed=42；每世界 10 能量、300 秒；每世界仅一次真实模型探索，不自动重跑。

继承配置：总 token 预算 5000000，单次输出上限 4096，原模型请求重试上限 1。Agent、提示词、工具沿用当前版本。

评测仅在真实 accepted 提交后执行，使用全部 v15 固定案例；采用本地 10 能量口径。这是本地规则适配实验，不表示兼容正式 SDK，也不是比赛成绩。未完成、错误与评测失败均保留。

Tokens 仅统计 API 已返回的 usage；超时或失败请求可能没有返回用量，未统计不代表未消耗。保守预留额度单独记录在 summary.json 中，不作为实际 token 用量。

每轮输出 token = 累计 completion_tokens / 模型请求次数（含重试，不含输入 token）；运行中或缺失 usage 时不报告平均值。探索耗时从 mission 开始，交卷后评测单独计时；总耗时从 worker 启动至评测结束，不含排队。逐次输出最大值不能用平均值替代。

| 世界 | 状态 / 原因 | 模型调用 | 输入+输出 Tokens | 输出 Tokens | 平均每轮输出 Tokens | 能量消耗 | 总分 | 位置 RMSE | 探索秒数 | 评测秒数 | 单次最大输出 | 超输出上限次数 | 含评测秒数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| world_1 | submitted / submission_accepted_locally | 25 | 1180868 | 7782 | 311.28 | 8 | 42.4366 | 2.77835 | 142.53 | 3.46995 | 1407 | 0 | 147.601 |
| world_2 | submitted / submission_accepted_locally | 7 | 110660 | 3037 | 433.857 | 4 | 16.4166 | 7.27602 | 49.9627 | 1.96817 | 966 | 0 | 55.6287 |
| world_3 | submitted / submission_accepted_locally | 5 | 111990 | 1745 | 349 | 4 | 98 | 2.63172e-08 | 31.3511 | 2.56851 | 817 | 0 | 35.3487 |
| world_4 | submitted / submission_accepted_locally | 12 | 383342 | 4524 | 377 | 6 | 65.2059 | 1.24244 | 80.3385 | 4.4207 | 1578 | 0 | 86.1776 |
| world_5 | submitted / submission_accepted_locally | 18 | 817777 | 8504 | 472.444 | 6 | 24.1466 | 2.27313 | 152.007 | 2.61867 | 1191 | 0 | 158.472 |
| world_6 | submitted / submission_accepted_locally | 15 | 646092 | 5661 | 377.4 | 8 | 17.0969 | 4.26139 | 136.516 | 3.31943 | 1706 | 0 | 143.36 |

## 逐世界记录

### world_1

运行：`e5-qwen38-clean-20261107-r03-world_1`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-clean-20261107-r03-world_1)

```json
{
  "law": {
    "law_id": "law_9",
    "law_spec": {
      "ax": "-k*x/sqrt(x*x+y*y)",
      "ay": "-k*y/sqrt(x*x+y*y)"
    },
    "fitted_parameters": {
      "k": 0.025573545491623537
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

运行：`e5-qwen38-clean-20261107-r03-world_2`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-clean-20261107-r03-world_2)

```json
{
  "law": {
    "law_id": "law_2",
    "law_spec": {
      "ax": "-C*q('charge')/q('mass')*x/(x*x+y*y)",
      "ay": "-C*q('charge')/q('mass')*y/(x*x+y*y)"
    },
    "fitted_parameters": {
      "C": 0.1662449548465408
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

运行：`e5-qwen38-clean-20261107-r03-world_3`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-clean-20261107-r03-world_3)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "A*x+B*y",
      "ay": "C*x+D*y"
    },
    "fitted_parameters": {
      "A": -0.0600000000005903,
      "B": 0.034641016155680236,
      "C": 0.03464101615251846,
      "D": -0.10000000000759224
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

运行：`e5-qwen38-clean-20261107-r03-world_4`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-clean-20261107-r03-world_4)

```json
{
  "law": {
    "law_id": "law_5",
    "law_spec": {
      "ax": "k*q('charge')/q('mass')*(-x)/sqrt(x**2+y**2)**3",
      "ay": "k*q('charge')/q('mass')*(-y)/sqrt(x**2+y**2)**3"
    },
    "fitted_parameters": {
      "k": 0.38470895560121054
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

运行：`e5-qwen38-clean-20261107-r03-world_5`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-clean-20261107-r03-world_5)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "a11*x + a12*y",
      "ay": "a21*x + a22*y"
    },
    "fitted_parameters": {
      "a11": -0.0628793059919083,
      "a12": 0.006348576410430432,
      "a21": -0.0020510568022520707,
      "a22": -0.11010267297776802
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

运行：`e5-qwen38-clean-20261107-r03-world_6`。

[本地研究台](http://127.0.0.1:8765/?run=e5-qwen38-clean-20261107-r03-world_6)

```json
{
  "law": {
    "law_id": "law_1",
    "law_spec": {
      "ax": "A*x+B*y",
      "ay": "C*x+D*y"
    },
    "fitted_parameters": {
      "A": -0.07987024339068152,
      "B": 0.04260919077457505,
      "C": 0.04395859285372755,
      "D": -0.16083546474860694
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
