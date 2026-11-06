# 物理规律发现 Agent · 本地原型

一个普通 CPU 可运行、没有 Agent 框架依赖的 Python 项目。由一个主 Agent 自主决定实验和工具顺序，确定性程序完成拟合、推演、残差诊断、验证和归档。旧规则提供八个工具，E4 增加显式 `save_draft`；可额外启用隔离的 `run_code`，让主 Agent 编写 Python 分析代码；已移除分析子 Agent 和 summarize_data 工具。

这是开发原型：现已在本地接入 `shore-contest-starter-v15` 的六个公开开发世界，同时保留原七个世界。外部模型 API 不满足正式比赛的模型和外网限制；本次接入不等同于正式隐藏环境或官方提交协议接入。

## 旧版 / 新版物理世界

工作目录继续使用 `physics_discovery`，启动命令不变：

```bash
.venv/bin/python -m shore_agent.web --port 8765
```

在 [本地研究台](http://127.0.0.1:8765) 顶部切换「新版 · v15」与「旧版」。新版提供六个公开开发世界，旧版保留七个原型世界；历史会话和回收站均显示版本，查看历史时自动切到对应版本。首次打开默认新版。没有版本标记的历史档案仍按旧版解释，原有配置文件和 CLI 默认不变。

最初接入只改变环境和模型适配。E4 在此基础上加入新预算、截止保护与显式草稿工具，保留表达式、拟合和数据历史策略。当前服务器使用本地 Qwen，关闭思考；云端配置仍可用于历史设置复现。新版世界复用 v15 的真实力场、固定步长积分、可见背景、首光、合法投放范围和噪声尺度；源码快照存于 `shore_v15/vendor`，无需切换到 starter 目录运行。实际公式只在观测子进程和结束后的评测中使用，不进入 Agent 任务包。

为适配原 Agent 的 `mass` / `charge` 工具字段，新版世界 1、2、4 中 `mass` 对应 v15 的 `p2`，`charge` 对应 `p1`，默认均为 1、范围均为 [0.5, 2]；世界 3、5、6 保留 `mass`，范围 [0.5, 4]。原工具批次中每枚探针对应一次独立 v15 实验，因此同批探针可使用不同源控制值；这与标准 Console 的单次 launch 共享 `p1` 不同。映射与合法范围会写入任务包，Agent 仍通过原有工具操作。

规则由 `environment.ruleset` 单独标记：未标记及 `e3` 保留 100 能量、3600 秒；`e4` 固定 10 能量、300 秒、位置与速度噪声、关闭思考、每调用最多 4096 输出 tokens。E4 只支持新版六世界；旧版历史仍可查看。节约分按对应规则预算计算。候选仍用现有 Agent 数值工具推演，独立评测仍是本地协议，不代表官方成绩或正式 SDK 兼容。

命令行可以明确指定新版；初始化只读取首光，不调用模型：

```bash
.venv/bin/python -m shore_agent.cli init --world-set v15 --world world_1 --run-dir runs/v15-first-light
.venv/bin/python -m shore_agent.cli run --world-set v15 --world world_6 --run-dir runs/v15-world6
# 原七个世界
.venv/bin/python -m shore_agent.cli init --world-set legacy --world world_7 --run-dir runs/legacy-first-light
```

新版档案使用 `environment.world_set="v15"` 和 `physics_version="shore_v15"`；旧版使用 `legacy`（或无标记）及原来的 v1–v4。下文关于七世界和 v4 的实验说明保留为旧版背景。

## E3 / E4 服务器实验

[E3](experiments/E3/README.md) 归档了规则修改前的三个服务器批次（两个 27B 批次、一个 122B 批次，18 次探索），保留原 run ID、原始结果及源码快照。E4 按顺序只实施：统一规则；截止保护与模型显式草稿；推理服务 prefix cache、图执行与每卡单活跃世界。没有压缩历史，也没有迁移正式 SDK。

E4 使用四个本地 Qwen3.8-27B 实例，六世界各一次全新探索，排队和模型预热不计入 mission 的 300 秒，提交后的独立评测单独计时。截止前有效的草稿可封存；没有有效提交的世界不会生成得分。没有三轮限制，也不自动重试整场实验。35B 权重不完整；122B 的两张卡已转为两个 27B 实例，前端明确显示这两个模型未部署。

启动与复现见[服务器部署说明](deployment/README.md)。[前端实验总览](http://127.0.0.1:8765/baselines)分别显示 E3 和 E4，列出每次探索/评测/总耗时、每轮平均输出及单次最大输出。

## 实验与迭代

所有实验记录存放在[experiments目录](experiments/)，[experiment.md总记录](experiments/experiment.md)说明每轮新增内容、实验设置、结果、失败与范围调整。推理强度实验记作E1；general code工具实验统一记作E2，并按R01、R02……迭代。

| 实验轮次 | 对应迭代 | 做了哪些实验 | 主要结果 | 详细记录 / Git提交 |
|---|---|---|---|---|
| E1 | 增加可配置的low/high/max推理强度 | 世界3/4/5 × 三档强度 × 各5次，共45次 | 高精度low 9/15、high 15/15、max 13/15；后续固定high | [报告](experiments/E1/README.md) · 实现`f0291f2` / 结果`e340213` |
| E2 R01 | 首次加入可选隔离Python工具run_code，支持自编数据分析与产物导出 | 固定high，世界3/4/5 × 原工具/加代码 × 各5次，共30个计划单元 | 原工具12/15、加代码13/15；代码组世界3改善，世界5退步 | [报告](experiments/E2/R01.md) · 实现`44e05bc` / 结果`1ea408e` |
| E2 R02 | 普通脚本入口、自动NumPy转换、精简结果返回及按字段读取 | 固定high，仅重测修改后的代码组，世界3/4/5各5次，共15次 | 高精度15/15；代码未成功调用比例20.6%→11.9%，返回消息中位大小减少约72% | [报告](experiments/E2/R02.md) · 实现`7fc4e94` / 结果`13a063e` |
| E2 R03 | inputs可省略；实际字段/形状提示、按编号读取和显式时间对齐 | 工程回归、真实容器与HTTP接口检查；尚未运行新探索 | 731项测试通过，尚无新探索成功率 | [迭代记录](experiments/E2/R03.md) |
| E2 R04 | 删除call_back，以当前会话文件路径统一浏览、读取和代码输入 | 完整回归及真实Docker文件读取；未新增真实探索 | 748项测试通过；历史独立会话不开放 | [迭代记录](experiments/E2/R04.md) |
| v15 / Qwen baseline | 接入六个 v15 世界和 Qwen，科学探索核心不变 | Qwen3.8-27B，关闭思考，六世界各一次真实探索 | 已完成：4/6提交并评测，2/6未完成；仅世界2达到RMSE<1e-6 | [最终分析](experiments/v15-qwen38-nothink-baseline-20261107-r02/analysis.md) · [逐界报告](experiments/v15-qwen38-nothink-baseline-20261107-r02/report.md) |

上述 E1/E2 高精度指完整独立隐藏轨迹评测的位置RMSE<1e-6。E2 R01的额度恢复补跑仍属于同一轮；E2 R02误排的原工具组尝试单独保留，不计入15次主结果。E2 R01与R02是跨批次比较，且简化后允许纯print脚本正常执行，不能把指标变化直接解释为推理能力提升。完整协议、耗时、用量和失败案例见各轮报告。

[E2轮次索引](experiments/E2/README.md)汇总general code迭代；更早的五世界扩展、观测来源、时间项及七世界工程改动可从[世界与版本说明](docs/worlds.md)、[初期五世界报告](docs/five-worlds-results.md)和[experiments目录](experiments/)追溯。历史会话ID与JSON中的旧路径保留为原始证据，目录迁移映射见[总记录](experiments/experiment.md)。

### v15 / Qwen 六世界 baseline（已完成）

早期云 API 批次为 `v15-qwen38-nothink-baseline-20261107-r02`：Qwen3.8-27B、`thinking=false`、无噪声、seed=42，六个世界各启动一次全新自主探索，最多三个并行。每世界仍为 100 能量、60 分钟、5M 总 token、65536 单次输出上限，代码工具关闭；失败不自动补跑。之前开启思考的 R01 已按用户要求中断并保留，不混入本次六界结果；此处 R01/R02 仅为 v15 baseline 批次，不改变 E2 编号。

六界已全部结束：世界1、2、4、5提交并完成独立评测，世界3因下一次模型请求的 token 预算不足结束，世界6以HTTP 400结束。仅世界2的完整评测位置RMSE低于1e-6；世界1漏软化项，世界4衰减结构错误，世界5漏非线性与方向差异。共170次模型请求、12,031,490个API已返回tokens，三并行历时约12分30秒。每世界仅一次试验，不代表稳定成功率；分数、误差和证据见[最终分析](experiments/v15-qwen38-nothink-baseline-20261107-r02/analysis.md)。

在 `physics_discovery` 下复现相同设置，输出目录和对应 `runs/` 目录必须尚不存在：

```bash
.venv/bin/python benchmark_v15.py \
  --config config.qwen.example.json --model qwen3.8-27b \
  --no-thinking --workers 3 --ask-key \
  --output experiments/v15-qwen38-nothink-reproduction-01
```

`--ask-key` 隐藏输入密钥；也可提前设置 `DASHSCOPE_API_KEY` 后省略该参数。密钥只经 stdin 传入工作进程，不写入参数、档案或报告。`--no-thinking` 必须显式保留：驱动为兼容旧批次默认启用思考，即使 Qwen 示例或本机网页配置已关闭思考。

每次探索保存在 `runs/<输出目录名>-world_N`，可在本地网页查看。编排器运行时更新输出目录的 `summary.json` 和 `report.md`，本轮最终数据已经归档；完整设置与源码哈希在 `manifest.json`。仅 accepted 提交进入独立评测，使用全部 v15 固定案例，仍按本地 100 能量口径计分。Tokens 只统计 API 已返回的 usage；超时或失败请求可能未返回用量，不代表没有消耗。未提交的两个世界没有评测分数，不能记作零RMSE。

## 快速开始

克隆仓库，在项目目录打开终端（Python 3.9 或更新版本）：

```bash
git clone https://github.com/Chenzonghua-SJTU/virtual_physics_law_explore.git
cd virtual_physics_law_explore
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
```

`requirements-tested.txt` 记录开发时验证的精确依赖版本；跨平台安装优先使用 `requirements.txt`。虚拟环境需要在克隆后自行创建。

首个 Git 版本为 `v0.1.0`，后续开发在 `main` 分支继续；可用 `git show v0.1.0` 查看首版提交。首版包含七个实验世界、单 Agent 探索、网页工作台、物理解释提交与按题目公式计算的会话后独立测评分数。本地探索档案 `runs/`、密钥、缓存及机器配置不提交；仓库保留经过检查的基准汇总与开发报告。

### 在网页中运行探索

本机网页已配置阿里云百炼，支持选择 **Qwen3.8-27B**、**Qwen3.6-35B-A3B**、**Qwen3.5-122B-A10B**，默认 Qwen3.8-27B，当前默认关闭思考（`thinking=false`）。网页启动时自动读取不含密钥的 `config.local.web.json`；`config.qwen.example.json` 同样关闭思考，可复制为本机配置。显式 `--config` 优先于本机配置；原 `config.example.json` 保留 DeepSeek 和 `thinking=true`，历史会话仍显示实际使用的模型及思考设置。

密钥只保存在运行进程内。可在网页输入，或启动时隐藏输入并供本次服务使用：

```bash
.venv/bin/python -m shore_agent.web --port 8765 --prompt-api-key
```

Qwen 通过百炼 OpenAI 兼容接口调用，保留思考开关，使用 `enable_thinking` 和流式响应；完整接收思考、工具调用与用量后交给原 Agent。Qwen 不发送 DeepSeek 的 low/high/max 参数，因此页面隐藏该设置。三个模型的单次输出上限分别为 131072、65536、65536，默认仍为 65536。模型、接口或预算错误会明确失败，不自动改用其他模型。接口依据：[思考模式](https://help.aliyun.com/zh/model-studio/deep-thinking)、[API Key 与地域](https://help.aliyun.com/zh/model-studio/get-api-key)。

在项目目录运行：

```bash
.venv/bin/python -m shore_agent.web --port 8765
```

打开 [彼岸研究台](http://127.0.0.1:8765)，选择世界版本、世界编号和模型，输入对应服务的 API Key，点击「开始探索」。网页会启动真实的主 Agent，持续展示研究进展、探针轨迹、候选规律和验证结果；成功提交后自动做对应世界的独立评测。可中途停止、重看已有运行、删除或恢复历史会话并下载公开结果 JSON。密钥仅用于本次进程运行，不写入配置、日志或浏览器存储。服务启动时已配置 `DASHSCOPE_API_KEY`（Qwen）或 `DEEPSEEK_API_KEY`（原 DeepSeek 配置）时，网页可留空密钥。

这是一套本机网页与 Python 服务：Python/SciPy 负责真实拟合和模拟，启动后保持终端运行即可。详细操作和运行边界见 [网页使用说明](docs/web.md)。

高级设置中的「允许 Agent 编写分析代码」需要先准备 Docker 执行镜像，见[代码工具与实验设计](docs/code_execution.md)。现在使用普通脚本接口：按当前会话文件路径直接读取完整数据、设置result，NumPy结果自动转换，不必编写函数或输出schema。模型收到精简结果，完整记录及产物保留；代码只能在无网络、无宿主挂载的容器中运行。

### 命令行运行

先离线查看任务包和免费第一束光（每次必须使用新的空目录）：

```bash
python -m shore_agent.cli init --run-dir runs/my-initial-observation
```

命令行真实 API 启动：通过环境变量提供密钥，不要写进配置或文件。在 macOS 默认 zsh 中可用隐藏输入：

```bash
read -s 'DEEPSEEK_API_KEY?DeepSeek API key: '
echo
export DEEPSEEK_API_KEY
python -m shore_agent.cli run --config config.example.json --run-dir runs/my-discovery
unset DEEPSEEK_API_KEY
```

有噪声模式加 `--noise`，选择世界加 `--world world_3`（可选 world_1–world_7，默认原始世界 world_1）。世界6引入移动天体，世界7引入固定天体下的周期强度；开发者定义及评测边界见 [世界说明](docs/worlds.md)。CLI 不会把命令行当作模型提示，主 Agent 不接收 README、PDF、开发需求、测试文件或独立评测结果。没有密钥时会保存合法初始观测及 `incomplete` 结果，明确标注没有调用 API。

查看结果及提交后独立评测：

```bash
python -m shore_agent.cli inspect --run-dir runs/my-discovery
python evaluate.py --run-dir runs/my-discovery --n-probes 20
```

评测器只接受已经 `accepted` 且 `session_ended=true` 的提交档案，否则拒绝。它在另一个进程中读取真值并生成 `evaluation.json`，不是 Agent 工具，也不把结果送回运行会话。评测参数、随机种子、未见初态和失败案例均保存；这不是官方隐藏测试成绩。

## 工程测试与自主发现必须区分

```bash
python offline_smoke.py --run-dir runs/my-offline-clean
python evaluate.py --run-dir runs/my-offline-clean
python offline_smoke.py --noise --run-dir runs/my-offline-noisy
python evaluate.py --run-dir runs/my-offline-noisy
```

`offline_smoke.py` 手工指定一个通用五参数仿射候选和声明，仅验证实际工具管线。它不是科研 Agent、不是 mock 大模型发现，更不能作为自主发现成功的证据。单元测试里的 mock 仅验证消息协议、预算和接口边界。

已运行的结果与限制见 [开发验证报告](docs/verification.md)。原始运行记录（包括真实失败记录）保留在开发者本机的 `runs/`，不随 Git 仓库发布。历史报告中的运行 ID 和本机工作台链接用于溯源；克隆后需自行运行实验以生成档案。

## 结构和信任边界

```text
shore_agent/agent.py           主循环、进展、完整消息和结束状态
shore_agent/model.py           HTTP/主 Agent 模型预算
shore_agent/prompts/           主 Agent 提示词
shore_agent/schemas.py         八个默认工具及可选代码工具 JSON Schema
shore_agent/runtime.py         工具执行、档案、残差诊断与提交
shore_agent/expressions.py     AST 数学解释器（不执行模型代码）
shore_agent/numerics.py        观测驱动的拟合与候选推演
shore_agent/store.py           不可覆盖的实验/规律版本记录
shore_agent/environment.py     JSON stdio 子进程适配器
shore_agent/web.py             仅本机可访问的网页服务与 HTTP API
shore_agent/web_jobs.py        运行管理、历史与公开结果投影
shore_agent/web_worker.py      每次探索的独立进程与提交后评测
web/                          网页界面、轨迹图与持续更新
shore_sim/                    独立仿真后端；真值仅在此包
shore_worlds.py               公开世界编号与中性名称；没有力场信息
evaluate.py                   提交后独立真值评测；不属于工具
benchmark_worlds.py            通过本机服务执行所有世界同预算基准
offline_smoke.py               明确标记的手工候选工程测试
tests/                        数值、资源、隔离及模型协议测试
```

仿真后端通过 `python -m shore_sim.worker` 子进程运行，API Key 从它的环境移除。运行时数值模块没有仿真器导入；观测和数值工具通过接口/进程隔离提供合法数据。可选 `run_code` 单独使用 Docker 容器，不挂载项目、宿主文件或凭证，不开放网络和隐藏评测；不能在宿主直接执行模型代码。新版天体状态只来自题目允许的已知t=0初态、第一束光及后续位置观测；拟合只读取这些合法输入。

每个运行目录包含：

| 文件/目录 | 含义 |
|---|---|
| `config.json`, `mission.json` | 生效配置、任务包与缓存第一束光 |
| `records/<type>/<id>.json` | 完整不可变科学记录；每次拟合生成新 law_id |
| `code_executions/<id>/` | 自编分析代码、输入文件快照、来源哈希及图表/数据产物（旧档案保留原协议） |
| `tools.jsonl` | 工具参数、返回、实验预算与耗时 |
| `messages.json` | 完整主 Agent 历史，包含 reasoning_content 和匹配的 tool_call_id |
| `model_messages.jsonl` | 主 Agent 模型请求消息和完整回复；旧档案可能包含分析子 Agent 调用 |
| `model_events.jsonl` | 模型配置、返回模型标识、指纹、调用/用量/耗时/脱敏错误 |
| `events.jsonl` | 用户可见研究进展、调用和结束状态 |
| `submissions/<id>/` | 自包含 `law.py`、`claims.json`、固定规律记录与物理解释 `physical_explanation.txt` |
| `result.json` | submitted/incomplete/error 及明确结束原因 |
| `evaluation.json` | 仅会话结束后独立评测输出 |
| `evaluation_score.json` | 旧评测的题目公式评分补算，与原评测文件哈希绑定；不改写原结果 |

日志不包含密钥和 Authorization header。`reasoning_content` 为遵循 API 协议保存和回传，终端只展示进展 `content` 与工具状态。消息历史不做有损压缩；总 token 预算触尽时如实停止。HTTP 失败且服务端未返回用量时，按请求的保守额度预留 token，不能将其当成实际计费量。

## 配置与资源

下述默认数值说明旧版/E3 配置；E4 的强制覆盖以文首及 `config.e4.example.json` 为准。

`config.example.json` 可以设置模型、base_url、思考模式/强度、超时、重试、单次输出及总 token 上限。主 Agent 不再限制模型调用总次数或对话轮次，旧配置中的 `max_calls`、`main_max_calls`、`max_turns`、`max_rounds` 不再约束新运行；有效调用限额记录为 `null`。每次输出默认最多 65,536 token（含思考），总预算 5,000,000 token，单次请求超时 600 秒。每次 HTTP 尝试包括重试仍计入调用统计，实际 token 用量由服务端 usage 记录，未知用量另外保守预留。总 token、现实时间、单次重试次数及连续三次无工具回复的限制继续生效；未成功提交时如实结束为未完成。

网页高级设置可选择 low / high / max 推理强度；本地模型接入见[部署说明](docs/local_deployment.md)。主 Agent 默认启用 low 强度思考。45次推理强度消融的完整结果见[E1报告](experiments/E1/README.md)，本轮建议在高级设置选择high。新探索不创建分析子 Agent，也不提供 summarize_data 工具；数据解释和假设生成由主 Agent 完成，精确计算继续交给数值工具。旧会话、分析报告和原始失败记录保留，历史用量按其原配置展示。

核验日期：2026-11-01。当前默认 `deepseek-flash`；官方页面显示它对应 DeepSeek-V4.1-Flash-1017，旧 `deepseek-v4-flash` 名称虽可接受，已经重定向至新模型，不能声称锁定原权重。使用显式 `thinking` 和 `reasoning_effort`；带工具的历史中所有 assistant 的 `reasoning_content` 完整保留，包括没有调用工具的回复。[官方模型页面](https://api-docs.deepseek.com/quick_start/pricing/)、[思考与工具协议](https://api-docs.deepseek.com/guides/thinking_mode/)。

本地投放坐标逐分量在 [-5,5]，初速在 [-3,3]，物理时间 [0,30]，公开参考长度 10，可选属性 `mass`、`charge`。这些是本项目配置，不是声称已公布的官方参数。属性在本例动力学中不影响运动，模型可实验检验；不得把此开发说明发送给运行模型。

每会话 100 能量、每探针 1 点、每批最多 8 枚、每条最多 50 样本；observe 最多 20 次、每次最多 50 时刻。时刻必须对齐 0.005；首次成功 mission 起计现实时间，最多 60 分钟；重复读取不重置。模型思考与请求顺序不推进物理时间，投放时刻t0也不重置背景。v4按题目提供已知天体t=0初态，以及两条免费八样本探针轨迹、同八时刻的天体位置；第一束光不扣能量或observe次数。后续 `observe_body(times)` 消耗一次观察额度。

有噪声时，各位置坐标独立加入高斯噪声，标准差为参考长度的 1%（默认 0.1）；速度不额外加噪。新实验抽新噪声，读取旧记录不抽样。固定 seed 使本地观测可复现；生成的 UUID 和现实耗时不保证逐字一致，API 模型输出也不保证确定性。

v4按天体编号和绝对时间聚合观测，只对相同时刻重复样本求均值；已知t=0位置优先于该时刻的带噪读数。sum_b在积分器各时刻使用分段线性插值后的源位置，超出已观测时间范围报body_time_coverage，需先补充观测。只依赖t/r/v的候选不要求天体覆盖。law冻结公式、参数及训练输入快照；新验证与残差使用当次合法天体观测快照并归档，不改写law或旧验证。天体状态是外部输入，不是额外拟合参数。历史v1–v3仍保持静态平均与冻结位置语义。

主提示词保留既有科学探索职责，修正免费第一束光的信息来源，并增加绝对时间、动态天体输入和time_dependence的区分说明。天体运动导致受力变化不自动等于显式时间依赖；必须固定完整瞬时状态后判断。提示词和世界选择标签均不提供各世界真实公式、系数或声明答案。

v4提交的acceleration(t,bodies,params)接收调用方当前可见天体状态。会话后独立评测以真瞬时可见位置作为该外部输入，不拟合源运动、不向探索进程返回真值；输出中明确标注此本地状态契约。PDF没有细化bodies的正式编码，这不是声称已完成官方接口对接，也不能将其误差与旧版冻结带噪位置的结果直接混比。

## 数学与已知限制

完整 [工具接口、数组和表达式文档](docs/tools.md)。公式允许完整状态和跨轴项、时间函数、公开属性及可见天体求和；数值系数/偏移必须声明为最多五个标量参数。AST 有复杂度、指数和有限值限制。优化目标是各轨迹位置 MSE 等权平均，速度单独报告。优化为局部最小二乘，不能保证全局最优。

验证严格冻结版本参数并拒绝训练轨迹重叠；工具不会自动裁定“通过”。最终新数据是否受此前模型选择影响，需要主 Agent 根据完整研究历史判断，第一版不做统计上的自适应选择校正。自然语言解释仍需以工具计算和独立实验检验，不能因模型表述自信就视为科学结论。

数值工作有单轨迹 4 秒、拟合默认 25 秒与求导次数上限，并受剩余会话时间约束。HTTP timeout 是客户端阶段超时；返回后重查总现实时间，超时回复不会执行工具。第一版不支持从中断会话恢复执行，旧档案可直接阅读；禁止在非空目录启动以避免悄悄重置预算。

提交代码使用统一 `acceleration(t,bodies,params)`；本地 `bodies` 状态编码在工具文档中定义。正式官方环境未取得，不能声称接口完全兼容。预测等价模型可能无法唯一恢复源结构；本原型不把高预测精度等同于唯一物理解释。尚未实现正式九宇宙、模型训练、容器交付或分布式执行。

扩大预算后的五世界真实测试：见 [第二轮结果](docs/five-worlds-large-budget-results.md)（5/5 自主提交并完成独立评测；单世界单次试验）。

单 Agent 七工具复测：见 [第三轮结果](docs/five-worlds-single-agent-results.md)，五世界全部自主提交并完成独立评测。

观测来源修正后的首批五世界实跑及两个失败世界的原版本复测，见 [观测来源诊断与复测报告](docs/observation-source-results.md)。首批包含一次高误差提交和一次预算结束；复测均取得低误差，说明同一版本仍存在探索路径波动，不能将一次五世界成功解释为稳定成功率。

当前物理与观测协议版本为 `v4`：新增世界6（移动源线性回复）、世界7（固定源周期调制），原五世界保持v3力场，包括世界5的g=1、s=1。历史v1/v2/v3按归档版本读取与评测，无版本会话继续按v1处理。历史真实探索及当前定义见[分版本说明](docs/worlds.md)。
