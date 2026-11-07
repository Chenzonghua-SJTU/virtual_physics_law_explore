# qz-infer 本地 Qwen 部署

当前在 `3ba6d63`（E5 R01）的科学工具上进行 E6 无新增工具比较；后面保留回退及 E4/E3 的历史部署说明。

服务器项目：`/inspire/hdd/project/26-the-other-shore/263140062/physics_discovery`。
公共模型根目录：`/inspire/hdd/project/26-the-other-shore/public/models`。
项目的服务器 `.venv` 链接到已有 `/opt/shore-test5-forge2`（Python 3.12、vLLM 0.24.0、Torch 2.11.0+cu130）。Mac 的虚拟环境、密钥和 `.git` 未复制；代码、文档、实验汇总和运行档案保留。

## E6：无新增工具的循环修复比较

当前配置继续使用原有 9 个工具、10 能量、300 秒探索、单次最多 4096 输出 token，关闭思考与噪声。用户已取消累计 5M token 限制；`model.max_total_tokens: null` 仅取消累计配额，保留完整用量统计。前端高级设置留空表示不限累计用量。

`agent.loop_recovery: true` 修复反复原样调用而不前进的问题：同一错误最多实际重试一次；同一已知数据上的确定性调用也最多实际执行两次。第三次拦截并反馈一次纠正机会，后续模型轮仍重复才结束并保留有效草稿。新观测会更新状态，合法重复采样不受此限制。环境错误保留结构化 code/message。单次输出截断只允许一次短回复恢复，未完整输出的调用不执行。历史配置未开启该开关时仍保持旧行为。

`run_e6_recovery.py` 在四个同型号 27B 端点上，分别完成 baseline / concise 提示词各两批六世界。取消固定模型采样 seed（环境 seed 仍为 42）。按两批共 12 次中 ≥90 分数、完整评测数、均分顺序选定版本，不逐世界择优拼接。协议见 `experiments/E5/e6-protocol-amendment-2.json`。先报告这版完整结果，再开始可选 PySR 世界实验。

```bash
.venv/bin/python -u deployment/run_e6_recovery.py
```

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
