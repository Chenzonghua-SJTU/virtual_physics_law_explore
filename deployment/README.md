# qz-infer 本地 Qwen 部署

以下先列 E5 实验配置，后面保留 E4/E3 历史部署说明；历史启动命令不代表当前服务状态。

服务器项目：`/inspire/hdd/project/26-the-other-shore/263140062/physics_discovery`。
公共模型根目录：`/inspire/hdd/project/26-the-other-shore/public/models`。
项目的服务器 `.venv` 链接到已有 `/opt/shore-test5-forge2`（Python 3.12、vLLM 0.24.0、Torch 2.11.0+cu130）。Mac 的虚拟环境、密钥和 `.git` 未复制；代码、文档、实验汇总和运行档案保留。

## E5：10 能量、300 秒、每次输出 4096 token

探索与独立评测均无噪声，模型关闭思考，E3 主提示词原文保留。探索计时包含模型和科学工具；提交后的独立评测单列，总耗时另含 worker 启动与收尾。累计输入加输出仍保留原有 5M 预算，不能把它与每次输出上限混为一谈。

R14/R15 的服务布局为 GPU0/1 各一份 27B BF16（8000/8001），GPU2+3 为一份 122B FP8、TP=2（8002）。每个端点只安排一场探索，不让任务排队挤占该场的 300 秒。模型与合成接口预热先完成，再启动计时。35B 当前未加载，不能静默用其他模型替代。

27B 的完整六世界复测命令示例（输出目录必须全新）：

```bash
.venv/bin/python benchmark_v15.py \
  --config deployment/config.e5.hs-seed43.json --ruleset e5 --no-thinking \
  --model qwen3.8-27b --workers 2 \
  --model-endpoints http://127.0.0.1:8000/v1,http://127.0.0.1:8001/v1 \
  --output experiments/E5/my-new-six-world-batch
```

`config.e5.hs-t1.json` 与 `hs-t02.json` 对照温度，`hs-seed43.json` 与 `hs-seed44.json` 仅改变模型采样 seed；物理环境 seed 始终为 42。`hs-qwen122.json` 用于单独的 122B 对照，启动时显式传 `--model qwen3.5-122b-a10b --workers 1 --model-endpoints http://127.0.0.1:8002/v1`。

新增可选配置 `config.e5.harmonic-fit.json`（27B）和 `config.e5.harmonic-fit-qwen122.json`（122B）用于后续实验，不能在尚未测评时声称优于旧配置：

- `numerics.diagnostics_harmonic`：在已取得观测上比较完整一次位置项乘自由频率 sin/cos；每折重新选择频率，报告可辨识性与采样别名限制。最多 2 秒且受剩余探索时间约束。
- `numerics.diagnostics_on_fit`：拟合残差有警告时，补充诊断该 law 已选择的训练轨迹；不读独立评测、不消耗新探针、不自动替换公式或提交。重复训练集在同一会话缓存诊断。

两个开关默认关闭，仅 E5 生效。候选仍需普通拟合和新轨迹验证；诊断重构 CV 不是独立预测得分。完整批次和失败都在 `/baselines` 展示；报告见 [`experiments/E5`](../experiments/E5/README.md)，不拼接跨批次最高分。

## E4 历史部署

E4 当时四张卡各运行一个 Qwen3.8-27B BF16 副本，GPU0..3 对应 8000..8003。统一开启 prefix cache 和图执行，`max_num_seqs=1`；推理关闭思考。当时未提供 35B/122B 服务，前端禁选两者，不会转用其他模型。

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
