# 修复版七世界真实探索复测

代码版本：`3e7264d316172c4dac727f52b461fd5b4c887424`。七次运行期间已跟踪文件哈希保持不变。

每世界一次真实自主探索，DeepSeek Flash、thinking=true、reasoning_effort=low、无噪声、种子42；总预算每世界2,000,000 token、单次输出65,536、模型调用次数不限。每次提交后独立评测20组隐藏初态，评测种子1871。原始会话均保留在工作台历史中，不以手工拟合或补提交替代失败结果。

| 世界 | 旧得分 → 新得分 | 旧位置 RMSE → 新位置 RMSE | 调用数 | Token | 状态 |
|---|---|---|---:|---:|---|
| world_1 | 99.75 → 94.45 | 6.023e-08 → 5.369e-08 | 6 | 163,521 | submitted |
| world_2 | 99.20 → 94.20 | 8.641e-06 → 4.681e-08 | 8 | 381,493 | submitted |
| world_3 | 99.10 → 91.01 | 5.493e-06 → 3.555e-01 | 16 | 1,169,750 | submitted |
| world_4 | 99.00 → 98.40 | 6.244e-07 → 9.546e-08 | 10 | 637,132 | submitted |
| world_5 | — → — | — → — | 21 | 1,899,520 | incomplete |
| world_6 | 99.85 → 99.20 | 5.911e-08 → 5.504e-08 | 7 | 226,445 | submitted |
| world_7 | 99.25 → 97.15 | 2.705e-08 → 2.779e-08 | 14 | 665,913 | submitted |

合计 82 次 API 请求，5,143,774 token；上一轮 62 次、3,810,937 token。实际提交 6/7，完成独立评测 6/7。

同一仿真种子固定环境及评测条件，不固定服务商模型回复；每世界只有一个样本，不能据此估计成功率或将全部差异归因于代码修复。得分采用题目公式；RMSE是额外诊断，不另设通关阈值。物理解释的正确性仍不参与评分。

## 各世界记录

### world_1 · `web-20261103-162820-863cefee`

结束原因：`submission_accepted_locally`；工具错误 0 次。

```text
ax = -k*x
ay = -k*(y-cy)
{"k": 0.30000000073090427, "cy": 0.9999999987088467}
```

### world_2 · `web-20261103-162953-72b81d97`

结束原因：`submission_accepted_locally`；工具错误 1 次。

```text
ax = a0 + a1*x + a2*y
ay = b0 + a2*x + b2*y
{"a0": 0.08000000004258338, "a1": -0.34999999988502845, "a2": -0.08000000001552288, "b0": 0.20000000002000035, "b2": -0.20000000010617675}
```

- 工具步骤 5 / `fit_law_and_rollout`：{"code": "invalid_expression", "message": "use named parameters for constants; only 0, +/-1 and integer exponents -3..3 are structural literals"}

### world_3 · `web-20261103-163310-fe87f266`

结束原因：`submission_accepted_locally`；工具错误 1 次。

```text
ax = p0*sum_b((bx-x)*sqrt((bx-x)**2+(by-y)**2))+p1*sum_b((bx-x)*((bx-x)**2+(by-y)**2))
ay = p0*sum_b((by-y)*sqrt((bx-x)**2+(by-y)**2))+p1*sum_b((by-y)*((bx-x)**2+(by-y)**2))
{"p0": 0.02678701749989038, "p1": 0.001230838275636668}
```

- 工具步骤 24 / `fit_law_and_rollout`：{"code": "invalid_expression", "message": "formula exceeds 256 total AST nodes (276 counted through ay); factor repeated terms or combine body sums. This is a syntax/resource limit, not evidence against the physical hypothesis."}

### world_4 · `web-20261103-163901-54d3f356`

结束原因：`submission_accepted_locally`；工具错误 0 次。

```text
ax = sum_b(G*(bx-x)*(((bx-x)*(bx-x)+(by-y)*(by-y)+c)*sqrt((bx-x)*(bx-x)+(by-y)*(by-y)+c))**(-1))
ay = sum_b(G*(by-y)*(((bx-x)*(bx-x)+(by-y)*(by-y)+c)*sqrt((bx-x)*(bx-x)+(by-y)*(by-y)+c))**(-1))
{"G": 0.7999999920506856, "c": 0.6399999876556897}
```

### world_5 · `web-20261103-164419-999a4b0d`

结束原因：`model_token_budget_exhausted`；工具错误 3 次。

- 工具步骤 7 / `fit_law_and_rollout`：{"code": "invalid_expression", "message": "use named parameters for constants; only 0, +/-1 and integer exponents -3..3 are structural literals"}
- 工具步骤 12 / `fit_law_and_rollout`：{"code": "invalid_expression", "message": "invalid, reserved or duplicate parameter name"}
- 工具步骤 23 / `fit_law_and_rollout`：{"code": "invalid_expression", "message": "numeric offsets must be named parameters"}

### world_6 · `web-20261103-165106-cf601833`

结束原因：`submission_accepted_locally`；工具错误 0 次。

```text
ax = p1*x + p2*sum_b(bx)
ay = p1*y + p2*sum_b(by)
{"p1": -0.3000000002557422, "p2": 0.10000000005022801}
```

### world_7 · `web-20261103-165300-bd3263fa`

结束原因：`submission_accepted_locally`；工具错误 1 次。

```text
ax = -(A+B*cos(w*t+p))*x
ay = -(A+B*cos(w*t+p))*(y-C)
{"A": 0.3000000003262361, "B": 0.14999999986442916, "w": 0.5999999996540034, "p": -1.5707963253178292, "C": 1.0000000001786935}
```

- 工具步骤 30 / `fit_law_and_rollout`：{"code": "invalid_expression", "message": "numeric offsets must be named parameters"}

详细工具错误、参数精修状态、预算预估及实际 API 用量见 [diagnostics.json](diagnostics.json)。
