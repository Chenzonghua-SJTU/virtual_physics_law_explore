# 使用本地 DeepSeek 模型

对工作台而言，主要是把 API 地址和模型名换成本地服务提供的值。推理强度仍可选 `low` / `high` / `max`，Agent 提示词和工具不需要改。这里的配置负责连接已经启动的模型服务，不负责下载模型或分配 GPU。

1. 复制 `config.local.example.json` 为自己的配置，修改 `model.base_url` 和 `model.model`。地址应包含服务的 `/v1` 前缀，模型名应与服务返回的名称一致。
2. 启动工作台：

   ```bash
   .venv/bin/python -m shore_agent.web --config config.local.example.json --port 8765
   ```

   打开 `http://127.0.0.1:8765`，选择世界和推理强度后开始探索。命令行也可使用：

   ```bash
   .venv/bin/python -m shore_agent.cli run --config config.local.example.json --world world_3
   ```

3. 示例允许同机 `127.0.0.1` / `localhost` / `::1` 服务不设密钥。如果服务需要密钥，把 `api_key_required` 设为 `true`，将密钥放在 `api_key_env` 指定的环境变量中；示例使用 `LOCAL_LLM_API_KEY`，不会自动使用已有的云端密钥。连接远端 GPU 服务器时，可使用有认证的地址，或将服务端口通过 SSH 转发到本机。

总预算默认 **5,000,000 token**，统计一次探索累计的输入和输出。它不是模型单次上下文长度；单轮输出上限由 `max_tokens_per_call` 设置，示例为 65,536，还需符合本地模型服务的限制。模型调用次数没有上限，时间和探索能量预算仍生效。

## 推理参数如何传递

`model.reasoning_protocol` 必须对应服务实际支持的协议，没有自动探测或失败后换档：

| 配置 | 实际发送的参数（以 high 为例） | 使用条件 |
| --- | --- | --- |
| `deepseek`（默认） | `thinking: {"type":"enabled"}`、`reasoning_effort: "high"` | DeepSeek 云端 API，或明确实现相同协议的本地服务 |
| `chat_template` | `chat_template_kwargs: {"thinking":true,"reasoning_effort":"high"}`，并发送同值的顶层 `reasoning_effort` | 显式 `deployment: "local"`；已核验相应 DeepSeek 模型模板的 vLLM / SGLang |

本地协议同时传两处同值的 effort，是因为已查阅的 vLLM V4 tokenizer 从模板参数读取，而 SGLang V4 适配器从顶层请求读取。关闭 `thinking` 时，明确发送关闭开关，不再发送 effort。已有云端请求格式保持不变。本地仅接受三个明确档位；不同服务对 `medium` 等别名的映射并不一致。

已根据以下官方资料核验协议（2026-11-04）：

- [DeepSeek 思考模式文档](https://api-docs.deepseek.com/guides/thinking_mode/)：云端开关、low/high/max 及工具对话的 `reasoning_content` 回传要求。
- [vLLM DeepSeek V4 tokenizer](https://docs.vllm.ai/en/latest/api/vllm/tokenizers/deepseek_v4/)：`thinking`、`reasoning_effort` 模板参数及三个档位。
- [SGLang DeepSeek V4 指南](https://github.com/sgl-project/sglang/blob/main/docs/cookbook/autoregressive/DeepSeek/DeepSeek-V4.mdx)：思考开关和 reasoning / tool-call 解析器；[V4 适配器源码](https://github.com/sgl-project/sglang/blob/main/python/sglang/srt/entrypoints/openai/serving_deepseek_recipe.py)：将请求的 effort 传给模型编码器。

这些是所查阅版本的支持情况，不代表所有 OpenAI 兼容服务、历史版本或同名权重都支持。部署时应记录模型具体版本、服务版本及解析器配置，确认 low/high/max 在服务端实际生成了对应的模型输入；仅收到 HTTP 200 不能证明参数生效。还要用一次工具调用及下一轮回传检查工具 ID、参数和推理字段是否完整。

`model_events.jsonl` 会记录协议、请求档位、实际发送的推理参数、响应模型名和 fingerprint，便于核对；这是请求记录，不是服务端生效证明。客户端完整保存并回传 assistant 消息（包括 `reasoning_content`，也保留服务使用的 `reasoning` 字段），不会把这些推理内容打印到终端或进展栏。密钥不会写入记录。

本次已用 mock HTTP 测试验证参数、认证、历史消息回传和错误处理；尚未连接真实本地 GPU 服务，三档在本地模型上的实际效果仍需部署时验证。云端模型别名也可能指向更新的 V4.1 权重，不能仅凭“Flash”名称认定与本地 V4 checkpoint 完全相同。
