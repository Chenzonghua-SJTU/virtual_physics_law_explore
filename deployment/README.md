# qz-infer 本地 Qwen 部署

E6 无新增工具比较与 E7 可选 PySR 对照均已结束。无新增工具基线冻结为 `eae6745`（`E5: 8 tool best performance`）；当前代码包含可选 PySR，但网页默认关闭。后面保留回退及 E4/E3 的历史部署说明。

后续实验统一使用 Qwen3.8-27B，四张 GPU 各部署一个同配置实例，最多并行四个会话。122B 不再部署，35B 不作为后续选项；历史模型记录和模型文件保留。

服务器项目：`/inspire/hdd/project/26-the-other-shore/263140062/physics_discovery`。
公共模型根目录：`/inspire/hdd/project/26-the-other-shore/public/models`。
项目的服务器 `.venv` 链接到已有 `/opt/shore-test5-forge2`（Python 3.12、vLLM 0.24.0、Torch 2.11.0+cu130）。Mac 的虚拟环境、密钥和 `.git` 未复制；代码、文档、实验汇总和运行档案保留。

## 已冻结：E5: 8 tool best performance

无新增研究工具的候选版本按本轮两种提示词、各两批完整六世界比较，保留 baseline 提示词。冻结提交为 `eae6745`，科学源码提交 `9b9cdca`；复现配置为 `deployment/config.e6.final.json`，选择依据见 `experiments/E5/e6-final-selection.json`。保留 8 个研究工具和已有的 save_draft（实际接口总数 9），累计 token 不限，单次 4096、探索 300 秒、10 能量、关闭思考与噪声。

baseline 两批分别 2/6 达到 90 分，12/12 完成独立评测；concise 两批为 3/6 与 0/6（严格按原始分数），10/12 完成。按预先约定的两批合计高分数、完成数、均分排序选出 baseline。这个提交名表示本轮候选选择，不表示已经达到至少五世界 ≥90 的目标或全局最优。

用户指出的 world_1 53.41 分已核查：Agent 的规律漏掉公开属性依赖。仅用于离线诊断、保持原参数补属性因子后为 97.50；该诊断不是 Agent 成绩，原评价未修改。证据在 `experiments/E5/e6-world1-property-diagnostic.json`。完整逐世界分数、探索/评测/总时长、平均和最大输出 token、循环反馈审计均保留在 E6 批次及审计 JSON 中。

| 开发世界 | baseline R01 | baseline R02 |
|---|---:|---:|
| 01 | 96.50 | 97.50 |
| 02 | 98.00 | 20.65 |
| 03 | 17.51 | 96.50 |
| 04 | 88.83 | 43.91 |
| 05 | 32.37 | 5.75 |
| 06 | 17.00 | 21.10 |

独立测评复查覆盖 24 次 E6 实验、608 条测试轨迹，原分数均复现；六世界完整公式的离线数值对照 152/152 通过，未发现评测器算错。截图中的 world_1、world_2 规律均缺少 `charge/mass`，会话内探针却全取质量、电荷为 1，所以会话内误差低不能推出跨属性测试得分高。world_2 保持参数补全该因子后的诊断分为 93（原提交的错误声明仍保留），不是 Agent 成绩。已修复网页用随机验证 ID 选“最近验证”以及列表隐藏有规则分但预测失败记录的问题；原始实验档案未改。证据见 [全部复查](../experiments/E5/e6-evaluation-audit-all.json)、[六世界积分对照](../experiments/E5/e6-six-world-integrator-audit.json)、[前端验收](../experiments/E5/e6-ui-fix-acceptance.json)。

## E6：无新增工具的循环修复比较

当前配置继续使用原有 9 个工具、10 能量、300 秒探索、单次最多 4096 输出 token，关闭思考与噪声。用户已取消累计 5M token 限制；`model.max_total_tokens: null` 仅取消累计配额，保留完整用量统计。前端高级设置留空表示不限累计用量。

`agent.loop_recovery: true` 修复反复原样调用而不前进的问题：同一错误最多实际重试一次；同一已知数据上的确定性调用也最多实际执行两次。第三次拦截并反馈一次纠正机会，后续模型轮仍重复才结束并保留有效草稿。新观测会更新状态，合法重复采样不受此限制。环境错误保留结构化 code/message。单次输出截断只允许一次短回复恢复，未完整输出的调用不执行。历史配置未开启该开关时仍保持旧行为。

`run_e6_recovery.py` 在四个同型号 27B 端点上，分别完成 baseline / concise 提示词各两批六世界。取消固定模型采样 seed（环境 seed 仍为 42）。按两批共 12 次中 ≥90 分数、完整评测数、均分顺序选定版本，不逐世界择优拼接。协议见 `experiments/E5/e6-protocol-amendment-2.json`。先报告这版完整结果，再开始可选 PySR 世界实验。

```bash
.venv/bin/python -u deployment/run_e6_recovery.py
```

## E7：冻结 E6 后的可选 PySR 对照

`numerics.symbolic_regression_enabled` 默认关闭。打开后仅增加 `symbolic_regression(train_probe_ids, time_budget_seconds)` 一个工具；普通 baseline 仍是 9 个工具。搜索只读取当前会话已获取的指定探针位置、速度、时间和共同提供的 mass/charge，从速度中心差分估计加速度，分别搜索 ax/ay。当前未输入天体集合位置，不预置引力、周期项或开发世界公式。修复版配置为 `deployment/config.e7.power.json`。

输入示例：`{"train_probe_ids":["probe_..."],"time_budget_seconds":25}`。工具输出完整 feature_names、探针编号、两轴搜索完成情况、搜索耗时及最多 3 个候选。每个候选含现有 DSL 的完整 law_spec、最多 5 个 parameter_spec 初值、加速度搜索误差、复杂度和来源。公式、参数、探针编号不会被通用数组预览截断；全部轴公式、拒绝原因和筛选统计存于当前会话的 `audit_path`，不把全部中间搜索式反复塞入模型上下文。

修复版保留 `+ - * / ^ sin cos exp sqrt log abs` 全部算子，支持实数幂。题目第 8 页说明涉及幂律、积分、梯度；用户进一步明确三角、指数、对数也可能出现，因此仅优先简单表达式，不禁用这些运算，也没有限定几个开发世界指数。每次 PySR 搜索均开放全算子，未宣称两阶段搜索。通用稀疏线性候选以 `linear_least_squares` 单独标注，PySR 候选标为 `pysr`；线性候选不冒充进化搜索的发现。

轴候选先按误差、复杂度、参数数目保留，再组合为不超过五参数的二维规律。候选必须在所有已取得状态和已知投放初态可计算，包括首次采样晚于投放的情形，并通过有时间与 RHS 次数上限的短轨迹积分。速度差分的宽窄模板敏感度只作为简单式排序的启发，不是统计置信区间。短轨迹检查只证实有限已知条件下可执行，不代表全域正确；缺少合格候选时返回空列表。筛选超时会保留同一数据上此前已通过检查的候选，未检查的新公式只进入审计。

Agent 仍须用原 fit_law_and_rollout 按位置轨迹拟合，再取得独立新探针验证并自行提交。搜索用过的所有探针会记入发现数据，不能在后续验证中冒充未见数据；搜索失败也保留这项来源记录。每次搜索最多 60 秒，并为拟合/验证/交卷保留至少 35 秒，搜索计入原 300 秒时限。CPU 服务预热在实验开始前完成，进程级硬超时可返回已取得的部分候选；服务不可用有明确失败反馈，不扩大预算。仅开启 SR 时附加 `prompts/symbolic.txt`，提示在有差异训练数据和充足余时下尝试一次搜索、拟合合理候选；关闭时原基线提示词逐字不变。

服务器安装独立 PySR 2.7.2 / Julia 1.13.3 环境，4 个 CPU worker，每个固定 4 线程，保留原 vLLM Python 环境。已安装依赖后可离线启动：

```bash
mkdir -p deployment/pysr-work
env PYTHON_JULIAPKG_EXE="$PWD/.venv-pysr/julia-1.13.3/bin/julia" \
  JULIA_DEPOT_PATH="$PWD/.venv-pysr/julia-depot" PYTHON_JULIAPKG_OFFLINE=yes \
  PYTHON_JULIACALL_THREADS=4 JULIA_NUM_THREADS=4 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python -u -m shore_agent.symbolic_service serve \
  --worker-python "$PWD/.venv-pysr/bin/python" --pool-size 4 --port 8890 \
  --spool-dir deployment/pysr-work
```

服务仅监听 127.0.0.1:8890。确认 `/health` 中 4 个 worker ready 后，再运行纯合成验证或正式比较。依赖首次安装、编译、重启记录见 `deployment/pysr-setup-evidence.json`；合成数据结果不是宇宙测评分数。

`deployment/run_e7.py` 必须读取已冻结的 `e6-final-selection.json` 与 `config.e6.final.json`，交错运行 PySR 开/关各两批完整六世界；四卡各接一个活跃会话，排队不计入探索时间。保留所有尝试，不按世界选最好的结果。E6/E7 均记录每次实验探索耗时、交卷后评测、总耗时、平均/最大输出 token；E7 额外记录搜索次数和耗时。开发世界结果不代表九个隐藏世界泛化能力。

### 修复版 E7 验收

修复功能提交为 `7b9a31d`，正式单批为 `e7-qwen38-pysr-power-20261107-r01`，六世界使用四个同配置 27B 实例，21 个科学源码哈希均与该提交一致。完整算子范围包含三角、指数、对数；不是仅允许幂律。协议见 [修复验收协议](../experiments/E5/e7-power-protocol.json)。

先完成不消耗探索能量的独立合成测试及旧观测回放：合成非整数幂由实际 PySR 找到指数 1.7000266，未搜索初态的位置 RMSE 为 5.40e-6；三次既定回放的 9 个候选均通过初态域检查，原始档案哈希不变。世界 03 回放实际返回两轴 PySR 线性式，按原五条训练轨迹拟合后，五条未搜索轨迹位置 RMSE 为 1.14e-9；世界 04 的可执行性改善，但预测质量没有一致改善。上述均为离线诊断，不能替换 Agent 成绩。[合成与回放汇总](../experiments/E5/e7-power-replay-summary.json)

| 世界 | 原始分数 | 探索秒数 | 总耗时秒数 | 每轮平均输出 token | SR 调用数 |
|---|---:|---:|---:|---:|---:|
| 01 | 90.50 | 188.59 | 193.31 | 718.29 | 1 |
| 02 | 95.00 | 74.46 | 80.97 | 340.22 | 1 |
| 03 | 19.36 | 86.02 | 91.13 | 338.85 | 0 |
| 04 | 27.85 | 217.34 | 224.08 | 未知：一次请求无 usage | 1 |
| 05 | 32.18 | 182.95 | 189.33 | 422.22 | 2 |
| 06 | 23.75 | 139.60 | 153.53 | 335.09 | 1 |

6/6 完成全部测试轨迹预测，2/6 达到 90 分，均分 48.11。探索均不超过 300 秒、能量均不超过 10；每次请求配置输出上限 4096，已有 usage 的输出均未超限（最大 4096）。世界 04 有一次 HTTP 400 未返回 usage，不能声称知道其全会话输出均值；11 次有 usage 请求的均值另存审计，不冒充全会话均值。总耗时含交卷后评测。

实际发生 6 次搜索、18 个候选，18/18 公式及参数完整进入下一轮模型上下文。世界 02 将两轴均来自 PySR 的完整候选原样拟合并提交，得 95 分；世界 05 复用并改名了候选 ax 的结构，自行补充 ay 后提交，得 32.18 分，属于部分结构采用。世界 01/04/06 拒绝候选后另行拟合，世界 03 未调用 SR。因此工具已经能返回并被采用，但本批不证明稳定成功率提高，更不证明隐藏世界泛化。[逐次使用审计](../experiments/E5/e7-power-agent-acceptance.json)、[六世界完整报告](../experiments/E5/e7-qwen38-pysr-power-20261107-r01/report.md)

世界 04 还暴露了通用历史消息问题：一次 4096-token 的 save_draft 参数被截断，服务却报告 tool_calls；Agent 拒绝执行后将坏 JSON 留在历史，下一请求被 vLLM 模板拒绝。后续修复只在开启 loop_recovery 时，将无效历史参数的传输表示改为合法空对象，并附明确失败反馈；原文保存在审计事件，调用不执行、重复调用判断仍使用原文。修复发生于本批结束后，原 27.85 分保留，未追加重跑。

修复通过 141 项相关测试。对原归档历史只调用实际 27B 服务的 `/tokenize` 验证：原样为 HTTP 400，仅修补一个无效参数后为 HTTP 200、38,777 tokens，低于 262,144 上下文上限；没有生成请求，也未重跑探索或重算分数。[真实模板对照](../experiments/E5/e7-power-json-recovery-check.json)、[前端归档核对](../experiments/E5/e7-power-frontend-acceptance.json)。

### 初版 E7 已完成结果与默认选择

PySR 功能提交 `8b5bb7d`；四批实验启动源码为 `97ae517`。全部 80 项源码哈希与该提交一致，开关两组配置仅 `numerics.symbolic_regression_enabled` 不同。模型采样 seed 未固定，符号搜索 seed 为 42。原始逐世界成绩与计时保留在各批次 summary/report；详细复查见 [E7 最终分析](../experiments/E5/e7-final-analysis.json) 和 [源码核对](../experiments/E5/e7-source-verification.json)。

| 批次 | ≥90 的完整世界 | 完整评测 | 均分（不完整按 0） | 每世界平均总耗时 | 每次模型调用平均输出 token |
|---|---:|---:|---:|---:|---:|
| [关闭 R01](../experiments/E5/e7-qwen38-pysr-off-20261107-r01/report.md) | 3/6 | 6/6 | 67.11 | 153.36 s | 495.47 |
| [关闭 R02](../experiments/E5/e7-qwen38-pysr-off-20261107-r02/report.md) | 0/6 | 6/6 | 23.21 | 180.45 s | 327.92 |
| [开启 R01](../experiments/E5/e7-qwen38-pysr-on-20261107-r01/report.md) | 1/6 | 5/6 | 30.68 | 165.81 s | 396.44 |
| [开启 R02](../experiments/E5/e7-qwen38-pysr-on-20261107-r02/report.md) | 1/6 | 5/6 | 31.45 | 179.42 s | 356.19 |

输出 token 均值按各批全部模型调用加权。总耗时包括进程启动、探索与交卷后评测；300 秒限制用于探索，评测耗时单列。24 次 usage 均完整，探索最长 278.36 秒、单次输出最多 4096，能量均不超过 10。

开启组仅 3/12 会话调用 PySR，共耗时 88.95 秒，返回 9 个候选；人工核对完整搜索结果和后续调用，没有候选进入拟合或提交。开启 R02/world_3 的 96 分来自 Agent 另行提出的线性公式，不能归因于 SR 找到了该公式。开启 R01/world_4 两次输出达到上限，用尽一次截断恢复后无提交，结束仍余约 35.76 秒；开启 R02/world_5 提交后候选积分失败，原规则分 10 保留，选型指标按 0 统计。

本轮没有证明可选 PySR 带来收益，默认继续关闭。关闭组两批本身波动很大，不能从两次重复断言 SR 导致性能下降，也不能据此否定符号回归。此次只覆盖无天体坐标、Agent 自愿调用的首版工具，未证明九个隐藏世界的泛化能力。后续优先考察公开可控属性的实验覆盖，再单独评估跨轴参数共享、候选筛选与 Agent 实际采用率，不加入开发世界专用公式；本轮到此收束，不再追加试验。

前端可在 `/baselines?group=E7` 查看四个完整批次及各世界会话，E6/E7 历史记录分别筛选，不用单世界最佳成绩拼成 baseline。

## 历史：恢复 3ba6d63 的 E5 R01

Agent、模型客户端、科学工具、提示词、拟合和评测实现逐文件恢复为该提交。规则为 10 能量、300 秒探索、单次最多 4096 输出 token，关闭思考，探索和独立评测均无噪声。提示词使用原 `main.txt` 加该提交的 `e5.txt`；没有后期诊断、候选公式、HS/谐波、工具筛选或恢复策略。保留原有 8 个工具和 E4 已有的 `save_draft`，共 9 个。

```bash
.venv/bin/python -m shore_agent.web --config deployment/config.e5.web.json --port 8765
```

须显式指定配置，避免无参数启动时加载机器上旧的 `config.local.web.json`。`config.e5.server.json` 与目标提交相同；`config.e5.web.json` 只额外登记现有 122B 服务端点，默认仍为 27B，未固定温度或模型采样 seed。网页入口会先合并 `config.example.json`，保留 5M 总 token 预算。

服务器继续使用 GPU0/1 的两份 27B BF16（8000/8001）和 GPU2+3 的 122B FP8 TP=2（8002）；本次不重启模型或启动新实验。

历史 `experiments/`、`runs/` 不回退，前端继续展示全部历史批次及诊断记录。历史元数据显示和列表性能修复不参与模型上下文或科学工具。回退前代码、配置及协议烟测保存在 Git 分支 `archive/e5-tools-before-rollback-20261107-101323`；后期配置须配合该历史版本使用。

R01 历史结果为 3/6 个世界达到 90 分、5/6 完成独立测评；这不是此次重新运行的结果。开发世界结果不能证明对九个隐藏世界的泛化能力。

## E4 历史部署

E4 当时四张卡各运行一个 Qwen3.8-27B BF16 副本，GPU0..3 对应 8000..8003。统一开启 prefix cache 和图执行，`max_num_seqs=1`；推理关闭思考。当时35B权重不完整，122B暂时没有服务，E4前端禁选两者，不会转用其他模型。

模型冷启动、编译、工具调用烟测在科学会话前完成。`serve_e4.py` 遇到已有监听/自己的存活启动进程即拒绝重启，不会自动杀进程。四个命令可分别在服务器执行：

```bash
.venv/bin/python deployment/serve_e4.py --gpu 0 --port 8000 --mode optimized
.venv/bin/python deployment/serve_e4.py --gpu 1 --port 8001 --mode optimized
.venv/bin/python deployment/serve_e4.py --gpu 2 --port 8002 --mode optimized
.venv/bin/python deployment/serve_e4.py --gpu 3 --port 8003 --mode optimized
```

E4 历史网页配置：

```bash
.venv/bin/python -m shore_agent.web --config deployment/config.e4.server.json --port 8765
```

E4全新六世界实验：

```bash
.venv/bin/python benchmark_v15.py \
  --config deployment/config.e4.server.json --ruleset e4 --no-thinking --workers 4 \
  --model-endpoints http://127.0.0.1:8000/v1,http://127.0.0.1:8001/v1,http://127.0.0.1:8002/v1,http://127.0.0.1:8003/v1 \
  --output experiments/E4/e4-qwen38-nothink-reproduction-01
```

每世界10能量、首次mission后300秒、每次最多4096输出tokens，位置与速度均加噪声，seed42。一个端点只接一个世界；排队不消耗探索时间。及时保存的LLM草稿可在截止时封存，未形成有效配对则如实未完成。评测只在探索结束后启动，其耗时单独记录，不把评测时间伪装成探索时间。完整原始记录仍保留在服务器runs，Git只上传审查后的汇总/报告/实现。

服务优化验证使用合成19,426输入token、256输出token的固定请求，与物理实验独立。旧服务约16.16秒，优化服务热缓存约4.10秒，首个内容约0.12秒；这是联合配置的微基准，不是六世界提速比例。数据见[服务A/B](../experiments/E4/service-ab.json)。

## E3 历史部署（当前未按此拓扑运行）

`config.server.json` 仅使用同机回环接口，不需要云端密钥，默认关闭思考。Qwen 本地开关使用 `chat_template_kwargs.enable_thinking`；工具调用解析器为 `qwen3_xml`，依据 [vLLM 工具调用文档](https://docs.vllm.ai/en/latest/features/tool_calling/)。科学 Agent 的提示词、工具和拟合策略保持不变。

| 模型 | GPU | 推理端口 | 配置 |
|---|---|---|---|
| Qwen3.8-27B | 0 | 8000 | 原始 BF16，六世界默认模型 |
| Qwen3.8-27B 第二实例 | 1 | 8001 | 独立重复批次，与 GPU 0 分开记录 |
| Qwen3.6-35B-A3B | — | — | 公共目录仅有未完成分片且缺 tokenizer，暂不可用 |
| Qwen3.5-122B-A10B | 2、3 | 8002 | 公共目录提供的 FP8 权重，TP=2 |

35B 没有替换成其他模型，前端显示“本机未部署”并禁选。若以后补齐完整权重，需要先停止 GPU 1 的27B副本并修改启动脚本为35B，再在 `config.server.json` 的 `local_model_endpoints` 中加入 `qwen3.6-35b-a3b: http://127.0.0.1:8001/v1`。

在服务器项目目录启动模型（跳过已运行或正在预热的自有进程及已监听端口，不终止其他进程）：

```bash
.venv/bin/python deployment/start_models.py
```

启动前端：

```bash
nohup .venv/bin/python -m shore_agent.web --config deployment/config.server.json --port 8765 > deployment/web.log 2>&1 < /dev/null &
```

在 Mac 建立转发后访问 http://127.0.0.1:8765（该端口必须空闲）：

```bash
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -L 127.0.0.1:8765:127.0.0.1:8765 qz-infer
```

服务器六世界实验（每次用全新输出目录）：

```bash
.venv/bin/python benchmark_v15.py --config deployment/config.server.json --no-thinking --workers 3 --output experiments/v15-local-qwen38-nothink-20261107-r01
```

实验使用无噪声、seed=42、每世界100能量/3600秒/5M累计token，单次输出上限65536。前端自动读取同目录 `runs/`，展示运行进度、真实提交和独立评测。批量实验由编排器管理，前端只能查看；失败不会伪装成得分。

推理服务仅绑定127.0.0.1。模型冷启动和CUDA编译发生在实验计时之前；模型日志、启动命令与PID保存在 `deployment/`。服务停止或SSH断开后，按上述命令恢复，不必重新上传代码或重做已完成实验。

按用户四卡并行要求，`deployment/run_parallel.py` 等待8001/8002服务健康后启动27B第二批和122B第一批，各三个并发；与原27B第一批合计18个独立探索、最多9个会话并发。`deployment/status.py` 输出三批的简明实时状态。所有批次逐世界独立保留，不能择优合并为一次baseline。

122B 的 FP8 线性层及 MoE 使用 Triton 后端，避开当前 CUDA 工具链的 FlashInfer JIT 编译不兼容；未改权重。27B 保持原始 BF16。前端 `/baselines` 每5秒读取真实汇总，按模型及批次展示六世界结果并链接到原始探索会话。

Mac 可运行 `.venv/bin/python -u deployment/tunnel.py` 保持 SSH 转发，断线自动重连。服务器的模型、批量实验和前端使用独立进程，不随 SSH 断线终止。
