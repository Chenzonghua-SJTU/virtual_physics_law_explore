# 七个科研工具与数据约定

本文按当前 [工具 JSON Schema](../shore_agent/schemas.py)、[执行层](../shore_agent/runtime.py)、[记录库](../shore_agent/store.py)、[表达式解释器](../shore_agent/expressions.py)、[数值工具](../shore_agent/numerics.py) 和 [提交生成器](../shore_agent/submission.py) 编写。运行时模型只有下面七个工具，没有 Shell、任意 Python、任意文件读取或隐藏评测接口。本文不包含环境真实动力学。已移除 summarize_data 工具和分析子 Agent；旧会话中的 data_summary 档案与日志只为历史查看保留，不再由新探索生成。

## 统一返回与时间

所有工具返回同一外层结构；以下各节描述的是其中的 `data`：

```json
{
  "ok": true,
  "data": {},
  "error": null,
  "budget": {
    "energy_remaining": 100,
    "observations_remaining": 20,
    "wall_seconds_remaining": 3599.8,
    "session_ended": false
  }
}
```

失败时 `ok=false`、`data=null`，`error` 包含 `code` 和 `message`。未知工具、额外参数、数组形状错误、非有限数值、非法表达式、资源耗尽等都会返回错误。`ok=true` 只代表这次调用完成：仍须查看 `fit_status` 或提交的 `status` 判断具体结果。环境进程失联时，执行层将剩余现实时间视为 0，能量和观察余额可能为 `null`。

`t`、`t0`、`dt` 和 `times` 均使用任务公布的统一物理单位，时刻是绝对时刻。`dt` 是采样间隔，不是积分器步长。某次实验的第 `k` 个样本时刻为 `t0 + k*dt`，`k=0,...,K-1`；`K` 包括投放时刻。实验可以在合法区间内指定较早或较晚的绝对时刻，不维护随思考推进的全局物理时钟。

现实计时从框架第一次成功读取 `mission` 开始。重复读取任务、读取预算均不会重置时钟或资源。模型思考、工具计算和网络等待都消耗现实时间。`mission`、`budget`、`end_session` 是框架与独立环境进程之间的内部方法，不是额外的模型工具；初始化前不接受实验。

## 记录与预览

记录的完整 JSON 保存到运行目录的 `records/<record_type>/<record_id>.json`；写入后不覆盖。模型按编号读取已经取得的记录，编号不是文件路径。

| 含义 | 字段 / 记录类型 | 当前编号形式 |
| --- | --- | --- |
| 可见天体 | `body_id`；嵌于任务和天体观测中 | `b1` 等，不是轨迹编号 |
| 一次天体观察 | `observation_id` / `body_observation` | `body_0001` 等 |
| 一次具体探针投放 | `probe_id` / `probe` | `probe_0001` 等；新投放产生新编号 |
| 固定规律版本 | `law_id` / `law` | `law_1`、`law_2` 等，按会话内的拟合版本顺序递增 |
| 一次冻结参数验证 | `validation_id` / `validation` | `validation_<随机后缀>` |
| 一份残差报告 | `residual_id` / `residual` | `residual_<随机后缀>` |
| 一次提交记录 | `submission_id` / `submission` | `submission_<随机后缀>` |

`law_spec` 是尚未拟合的结构；`law_id` 绑定该结构、该次拟合参数、训练轨迹和天体位置估计版本。再次拟合会生成新版本。编号仅在当前会话内使用，不能把其他运行目录的编号当成本次已取得的数据。

旧会话的随机后缀编号在网页中按生成顺序显示为 `law_1`、`law_2` 等；其原始档案和导出文件仍使用原编号，以保留既有引用关系。

工具通常返回递归预览。任意长度大于 6 的列表会替换成以下对象，保留前 3 项；长度不超过 6 的列表保持列表形式：

```json
{
  "preview": ["第1项", "第2项", "第3项"],
  "total_items": 30,
  "truncated": true,
  "retrieve": "call_back(detail=\"full\", record_ids=[id])"
}
```

这意味着预览里的 `times`、`r_obs`、`rollouts` 等字段可能是对象，不能当作完整数组直接计算。下面注明的数组形状均指完整记录。获取完整轨迹：

```json
{"record_type":"probe","record_ids":["probe_0001"],"detail":"full"}
```

## 1. `observe_body(times)`

输入 `times`：1–50 个严格递增的有限绝对时刻，全部处于任务公开范围并对齐 `0.005` 网格。合法调用消耗一次天体观察机会，不消耗探针能量。

完整 `body_observation` 记录：

| 字段 | 形状 / 含义 |
| --- | --- |
| `observation_id` | 本次记录编号 |
| `times` | `[T]` |
| `body_ids` | `[B]`，与位置第二维顺序一致 |
| `positions_obs` | `[T,B,2]`，最后一维为 x、y |
| `body_position_estimate` | 运行时附加的当前静态天体位置估计，见下文 |

即使天体静止，也保留时间维度。只返回可见天体位置观测，不返回作用强度、隐藏天体或真实力场。结果先完整存档，再返回预览。

Agent 初始任务包仅公开可见天体编号与静态环境约定，不含 `task.visible_bodies`、`first_light.body_observation` 或位置估计。坐标须通过显式 `observe_body` 取得；首次调用也消耗一次观察机会。观察前 `call_back` 没有天体位置记录，使用 `sum_b` 拟合会提示先观察；不依赖天体的候选不受影响。每次成功观察后，运行时按天体编号汇总已取得的独立样本，用逐坐标算术平均得到 `body_position_estimate`：

- `version`：当前会话的 `body_estimate_1`、`body_estimate_2` 等版本。
- `observation_ids`：实际使用的观测编号；`sample_count_per_body`：各天体样本数。
- `bodies`：每项含 `body_id`、估计 `position`、`sample_count`、逐坐标 `position_standard_error`。
- `method` 为 `mean_of_acquired_static_observations`；标准误为公开位置噪声标准差除以样本数的平方根，不是与真值之间的实际误差。未知噪声尺度时标准误为 `null`。

汇总按样本等权，批次样本数不同也不按批次均值等权。缓存读取不会再次计数。仅适用于当前明确静止、独立同尺度噪声的天体；不会据此推断运动天体轨迹。新观察不会修改旧档案，每份观察记录保留当时的估计版本。

## 2. `insert_probe(probes, t0, dt, n_samples)`

输入示例仅展示格式，不规定科研路线：

```json
{
  "probes": [{"r0":[1,0],"v0":[0,0.5],"properties":{}}],
  "t0": 2,
  "dt": 0.1,
  "n_samples": 20
}
```

`probes` 包含 1–8 项，每项必须含 `r0`、`v0`、`properties`。`r0`、`v0` 是有限二维向量，逐坐标遵守任务公布的投放上下界。`properties` 可为空；当前只接受可选的有限标量 `mass`、`charge`，不接受其他键。`t0`、正数 `dt` 和末样本时刻均受本地时间范围及网格约束；`n_samples` 是 1–50 的整数。

返回 `{"probes":[轨迹预览,...]}`。每条轨迹完整记录为：

| 字段 | 形状 / 含义 |
| --- | --- |
| `probe_id` | 此次投放生成的唯一轨迹编号 |
| `initial_conditions` | `{r0:[2], v0:[2], properties:{...}, t0:数值}`；受控初态 |
| `times` | `[K]`，含 `t0` |
| `r_obs` | `[K,2]`，位置观测 |
| `v_obs` | `[K,2]`，接口提供的速度观测 |
| `a_est_times` | `[K-2]`，仅内部采样点；`K<3` 时 `[]` |
| `a_est` | `[K-2,2]`；`K<3` 时 `[]` |
| `a_est_method` | `velocity_centered_difference`，或 `unavailable_fewer_than_3_samples` |

对于内部点 `k=1,...,K-2`：

```text
a_est[k-1] = (v_obs[k+1] - v_obs[k-1]) / (2*dt)
```

估计使用观测速度，不读取真实加速度；不存在端点假零值。每条轨迹消耗 1 点能量。输入校验失败不扣资源。新实验独立生成位置噪声，完整旧记录不重新抽噪声。拟合从受控 `initial_conditions` 启动，不把带噪首个位置观测当成受控初态。

## 3. `fit_law_and_rollout(law_spec, parameter_spec, train_probe_ids)`

`law_spec` 必须恰有字符串字段 `ax`、`ay`，模型工具层每个公式最多 600 字符。`parameter_spec` 是至多 5 项的列表，每项为 `{name, initial, lower?, upper?}`。`train_probe_ids` 必须是不重复的已取得整条轨迹编号；当前数值后端接受 1–102 条训练轨迹，包含最多一百条付费轨迹与两条免费第一束光。

候选两个分量都可使用完整的 `t,x,y,vx,vy`、已知静态天体和合法探针属性，不限制同轴依赖。表达式语法见后文。

目标函数为每条轨迹位置误差平方范数的样本平均，再对轨迹等权平均：

```text
position_mse_j = mean_k(sum_coordinate((r_pred_jk - r_obs_jk)^2))
fit_objective = mean_j(position_mse_j)
```

速度误差独立报告，不混入此目标。当前使用局部 `scipy.least_squares`，不保证全局最优。默认最大函数评估设置 `max_nfev=80`，可配置为 1–300；另有目标调用次数和时间限制。数值异常可能导致 `failed`，也可能返回已找到的最佳有限迭代并标记 `not_converged`。`ok=true` 不等于收敛。

任务明确公开位置噪声为零时，已收敛且位置 RMSE 不超过 `1e-5 × max(1, 训练位置 RMS)` 的候选可以继续精修：优化器的 `ftol/xtol/gtol` 从 `1e-8` 收紧到 `1e-12`。精修使用同一候选、同一训练数据、积分设置及参数边界，与初次拟合共享 25 秒和函数评估预算；不读取验证数据或真值。只有精修收敛且训练目标不变差才采用新参数，超时或失败保留原收敛结果。噪声非零或未知、结构残差明显、无需拟合参数或已达到精细梯度容差时跳过。`refinement` 字段记录是否尝试、跳过/保留原因、误差和追加目标调用次数。

完整 `law` 记录包含：

- `law_id, law_spec, parameter_spec, fitted_parameters, train_probe_ids, known_bodies`；其中 `known_bodies` 仅为本次拟合冻结的观测估计位置。
- `body_position_estimate`：本次冻结的位置估计、来源观测编号、样本数与标准误；追加观察只用于新拟合，不修改该 law 的验证、残差或提交。
- `fit_status`：`converged`、`not_converged`、`no_parameters` 或 `failed`；以及 `converged, message`。
- `errors`：整体及逐轨迹的位置/速度 MSE、RMSE；失败且无可用结果时为 `null`。
- `rollouts`：训练轨迹预测；每项含 `probe_id, times[K], r_pred[K,2], v_pred[K,2], a_pred[K,2]`。
- `objective_calls, invalid_evaluations, objective, optimizer`。

`a_pred` 是候选公式在预测状态上计算的加速度，含端点；它不同于内部采样点的 `a_est`。这里只重演输入训练记录，没有预测任意新实验的独立工具。返回记录预览；失败版本不能用于后续验证、残差或提交。

## 4. `validate_law(law_id, test_probe_ids)`

输入一个已拟合的固定 `law_id` 和不重复的已有测试轨迹编号。任何一条测试轨迹参与过该版本拟合，整个调用都会被拒绝。需要新数据时先调用 `insert_probe`；本工具不投放探针、不重新拟合参数。

返回并存档 `validation_id, law_id, test_probe_ids, errors, rollouts, warnings`，对模型使用预览。预测字段与拟合工具的 `rollouts` 相同。

误差结构为：

```text
errors.overall = {position_mse, position_rmse, velocity_mse, velocity_rmse}
errors.per_probe = [{probe_id, n_samples, position_mse, position_rmse,
                     velocity_mse, velocity_rmse}, ...]
errors.definition = 指标定义文本
```

每条轨迹的 `position_rmse=sqrt(mean_k(||r_pred-r_obs||²))`，速度同理。整体 RMSE 先对各轨迹 MSE 等权平均再开平方，不先把不等长轨迹的所有样本混合。

这些误差相对观测计算，没有预设通过阈值，不是隐藏测试得分。看过这批验证数据后调整候选，该批数据就属于开发数据；最终检查应使用新实验。

## 5. `call_back(record_type="all", record_ids=None, detail="summary")`

`record_type` 可选 `all, body_observation, probe, law, validation, residual, submission`。`record_ids` 可省略、为 `null` 或最多 102 项的数组。`detail` 为 `summary` 或 `full`。

不指定编号时，`summary` 返回该类型已有记录的目录和递归预览；`full` 必须指定非空编号列表。指定未取得编号会失败，不能读取其他会话或路径。返回：

```json
{"records":[{"record_type":"probe","record_id":"probe_0001","content":{}}]}
```

此工具不产生观测、不重新抽噪声、不重新拟合、不重新计算验证。会话结束后，主 Agent 工具统一停止；保存的 JSON 仍可由人离线检查。当前 CLI 不支持将已有记录目录恢复为继续进行的会话。

## 6. `analyze_residual(law_id, probe_ids)`

输入已拟合规律版本和不重复的已有轨迹编号，可含训练轨迹和验证轨迹。确定性程序按固定参数重新推演并计算残差统计。

完整结果包含 `residual_id, law_id, probe_ids, trajectories, description, warnings`。每条 `trajectories` 项包含：

- `probe_id`、`used_for_fit`、`times[K]`、`a_est_times`。
- `residuals.r[K,2] = r_pred-r_obs`。
- `residuals.v[K,2] = v_pred-v_obs`。
- `residuals.a[K-2,2] = a_pred[1:-1]-a_est`；无内部点时 `[]`。
- `statistics.r/v/a`：逐分量的 `mean[2], rmse[2], max_abs[2]`。无样本时三者为 `null`，并给出 `reason`。
- `correlations.r/v/a.x/y.t/x/y/vx/vy`：每项为 `{value, reason}`。

相关性使用同一轨迹的观测状态特征，速度和位置残差用全部点，加速度残差用内部点。少于 3 点或变量标准差低于 `1e-12` 时，相关系数为 `null` 并说明原因。这里的分量 RMSE 与验证工具的二维向量 RMSE 含义不同。相关性不等于因果关系，加速度差分也有离散偏差，工具不自动断言缺少某种力项。

## 7. `submit(law_id, claims, physical_explanation)`

`physical_explanation` 是必填的非空字符串（最多 20,000 字符，可分段），与所提交 `law_id` 的冻结公式和参数绑定。说明各项作用方向与状态依赖、参数含义和单位、由公式支持的运动性质、实验/验证记录依据、适用范围与不可辨识性。区分观测证据、数学推论和待检验的物理假说；低误差不代表已唯一识别机制。该字段是面向用户的答案，不是模型隐藏思考过程。缺失、空白或类型错误会在结束会话前被拒绝，Agent 可以补充后重试。

`claims` 必须恰含：

```json
{"dynamics_order":2,"hidden_matter":false,"time_dependence":false}
```

此处数值和布尔值只展示格式。`dynamics_order` 必须为整数 1 或 2：1 表示作用决定速度，2 表示作用决定加速度；`hidden_matter` 表示存在位置不可见的作用源；`time_dependence` 表示固定完整状态后仍显式依赖时间。声明不改变当前统一的候选加速度提交接口。

框架从所选版本生成可信解释器代码与固定元数据，不执行模型生成的任意 Python。产物在 `submissions/<submission_id>/`，包括 `law.py, law.pyc, law.json, claims.json, physical_explanation.txt`。物理解释作为文本单独保存，不进入可执行代码。检查项目包括参数最多 5 个且有限、编译成功、代码可执行、训练记录全部观测状态上的输出为有限二维数组。

返回并存档：`submission_id, law_id, claims, status, checks, reasons, session_ended, meaning`。`status` 为 `accepted` 或 `rejected`。`checks` 可含 `format, finite_parameters, executable, finite_observed_state_outputs, parameter_count, state_encoding`。受理成功立即结束会话；拒绝时给出原因。外层 `ok=true` 加上 `status=rejected` 是合法结果，主 Agent 不能把它当成成功提交。

返回和提交档案还包含原文 `physical_explanation`，并随最终 `result.json` 和网页公开导出保留。`accepted` 只代表本地格式和执行检查成功，不代表规律或物理解释正确、机制唯一或所有未见状态都数值稳定；没有运行隐藏评测，也不会泄漏评测信息。

### 当前导出代码的状态约定

导出函数签名是 `acceleration(t, bodies, params=None)`，其中 `bodies` 在本地实际上是一个完整状态对象：

```python
state = {
    "r": [x, y],
    "v": [vx, vy],
    "visible": [{"body_id": "公开编号", "position": [bx, by]}],
    "properties": {},
}
prediction = acceleration(absolute_time, state)
```

返回 `[ax, ay]`。`visible` 必须传入该 law 的 `known_bodies`（全部冻结的观测估计位置），不是上例那样固定只放一项，也不能替换为模拟器真值或后续更新的位置估计。默认 `params=None` 使用所选版本冻结的 `PARAMS`；程序接口也接受名称完全匹配的显式参数字典。本地受理和独立评测使用默认冻结参数和冻结位置。此通用导出函数本身不校验外部调用者的坐标来源。这是本地适配约定，不能声称已经兼容正式环境的状态编码或提交 API。

## 受限表达式 DSL

公式解释器解析 AST 并逐节点计算，不使用 `eval` 执行模型文本。

| 语法 | 当前行为 |
| --- | --- |
| 状态符号 | `t, x, y, vx, vy`；任一加速度分量均可使用全部状态 |
| 待拟合参数 | 唯一名称；以英文字母开头，后接至多 31 个字母、数字或下划线；不得含 `__`、占用保留名或声明后不使用 |
| 算术 | `+ - * / **`、括号、一元正负号 |
| 单参数函数 | `sin, cos, exp, log, sqrt, abs` |
| 可见天体求和 | `sum_b(expression)`；内部可用 `bx, by`，读取此 law 冻结的观测估计位置；不可嵌套 `sum_b` |
| 属性 | `q('mass')` 或 `q('charge')`；该轨迹必须实际含相应键，缺少时失败 |
| 结构字面量 | 公式中只接受整数 `0, 1, -1`；字面指数接受整数 `-3..3`，浮点写法如 `1.0` 不接受 |
| 系数与偏置 | 必须使用待拟合参数；拒绝其他数值字面量、纯常量算术、常量函数、常量求和，以及直接加减非零字面量偏置 |
| 禁用 | 属性访问、索引、导入、任意代码、比较、条件表达式、列表推导和未知函数等 |

参数初值和上下界必须有限，绝对值不大于 `1e12`。默认界为 `[-1e12, 1e12]`；必须满足 `lower < upper` 且初值在区间内。最多 5 个标量参数，禁止通过表达式硬塞拟合常数绕过该限制。

两分量合计最多 256 个 AST 节点，检查深度最多 16。超限错误报告实际计数和所在分量，并提示提取公因子或合并求和；语法/资源拒绝不代表物理假设被观测否定。计算中指数绝对值不超过 32，中间量必须有限且绝对值不大于 `1e12`。零除、函数定义域错误、过大状态、积分发散或超时会形成错误/失败信息。语法检查不是任意代数表达式的等价证明；科研使用者仍应保持参数化结构清楚、可解释。

下例只演示包含交叉速度项的合法语法，不代表当前环境的规律：

```json
{
  "law_spec": {"ax":"-drag*vx+turn*vy","ay":"-drag*vy-turn*vx"},
  "parameter_spec": [
    {"name":"drag","initial":0,"lower":-2,"upper":2},
    {"name":"turn","initial":0,"lower":-2,"upper":2}
  ],
  "train_probe_ids": ["已有轨迹编号"]
}
```

## 资源、噪声与本地配置

当前实现以下题面资源约束：初始能量 100 点，每探针 1 点，每批最多 8 枚，每枚最多 50 个时刻；天体观察最多 20 次，每次最多 50 个时刻；物理网格 `0.005`；会话现实时间最多 3600 秒。免费第一束光提供同样 8 个时刻的一次天体观测和两条标准探针轨迹，包含初始时刻，不扣能量或观察机会。第一束光数据只生成一次并存档。

以下设置由本地原型公开，不是题面未公布参数的官方取值：

| 环境配置 | 默认值 / 当前约束 |
| --- | --- |
| `noise` | `false`；为 `true` 时每个位置坐标加入独立零均值高斯噪声，速度不另加噪 |
| `seed` | 仿真器默认 7，示例配置为 42；非负整数 |
| `reference_length` | 10；正有限数；位置噪声标准差为该值的 1% |
| `position_limit` | 5；受控初始位置每坐标范围 `[-5,5]` |
| `velocity_limit` | 3；受控初始速度每坐标范围 `[-3,3]` |
| `time_max` | 30；物理时刻范围 `[0,30]`；至少允许 8 个网格采样点，即不小于 `0.035` |
| `wall_seconds` | 3600；可缩短，但不能超过 60 分钟 |

单位名称、参考长度、投放范围、物理时间范围、初始免费探针的具体初态和采样间隔、可选属性名称，均为本地约定。可见天体静态信息来自初始化任务；算法不读取仿真后台真值。新实验重新独立抽噪声，同一档案读取结果不变。

此外还有本地计算保护：一次拟合最多 25 秒或会话剩余时间（取小值）；单轨迹推演最多 4 秒或剩余时间，最多 12000 次加速度求值，状态幅度超过 `1e7` 时停止。数值后端另限制单条数据物理跨度不超过 100，因此修改环境时间配置时仍须符合数值工具约束。它们是原型的计算保护，不是官方成绩规则。

模型配置中的输出 token 上限、总 token 预算、超时和每次请求的重试上限仍可配置。只有主 Agent 调用模型；调用总次数和对话总轮次不设上限，旧 `max_calls`、`main_max_calls`、`max_turns`、`max_rounds` 字段不再约束新运行。每次 HTTP 尝试包括重试仍计入调用统计；缺少可信服务端 usage 时保守预留 token。有效限额、调用与预算细节记录在 `model_events.jsonl`，完整主对话保存在运行目录。未成功提交且达到无动作回复上限、总 token 或现实时间限制时，结果会明确标为未完成。
