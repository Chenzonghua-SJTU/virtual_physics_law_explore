# 可选 Python 分析工具与 E2

`run_code` 由主 Agent 直接使用，没有新增子 Agent。默认关闭；网页高级设置的「允许 Agent 编写分析代码」可开启。执行环境不可用时开关禁用；不会自动降级为宿主 Python。CLI 在配置中设置 `code_execution.enabled=true`。

## 准备执行环境

需要可用的 Docker 引擎。Mac 上本项目使用专用 Colima profile，不改变当前 Docker context，不挂载用户目录：

```sh
colima start shore-code --cpu 4 --memory 6 --disk 20 --mount none --activate=false --ssh-config=false
docker --context colima-shore-code build -t shore-code:e2-v1 code_sandbox
```

Linux / 其他 Docker 环境可使用 `docker build -t shore-code:e2-v1 code_sandbox`，配置中的 `docker_context` 可指定受信任服务端 context。Mac 存在上述 profile 的 socket 时自动选用它。镜像仅包含执行器及 numpy/scipy/sympy/matplotlib，不复制项目、实验记录或仿真源码。构建 context 由 `.dockerignore` 限制为 Dockerfile 和 runner.py。

若官方默认下载源不可达，本次本机构建使用：

```sh
docker --context colima-shore-code build \
  --build-arg BASE_IMAGE=public.ecr.aws/docker/library/python:3.11-slim \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  -t shore-code:e2-v1 code_sandbox
```

默认每次1CPU、1GiB内存、90秒计算期限（容器启动/传输有最多8秒宽限）、64进程/线程、128MiB工作目录、32MiB临时目录。限时也受会话剩余时间限制；主机监督超时强制结束容器。容器非root、只读根文件系统、无网络、无宿主挂载、无Docker socket、丢弃全部 capabilities、禁止新增权限；Docker默认seccomp继续生效。每次重新创建并最终删除容器。标准库和任意Python语法可用，安全边界是容器，不是Python字符串或AST过滤器。

## 工具协议

```json
{
  "code": "import numpy as np\ndef analyze(inputs):\n    p = inputs['trajectories'][0]\n    return {'n_samples': len(p['times']), 'mean_speed': float(np.linalg.norm(p['v_obs'], axis=1).mean())}",
  "inputs": {
    "trajectories": {"record_type": "probe", "record_ids": ["probe_0001"]}
  },
  "output_schema": {
    "type": "object",
    "required": ["n_samples", "mean_speed"],
    "properties": {"n_samples": {"type": "integer"}, "mean_speed": {"type": "number"}}
  }
}
```

每个输入别名映射为完整记录内容的列表，单条也是列表。支持本会话已有 `probe/body_observation/law/validation/residual/code_execution`；不接受文件路径，也不传入真实世界配置、隐藏评测、模型消息或凭证。后续代码通过 `inputs['previous'][0]['result']` 复用已有计算结果。输入记录逐个保存SHA256，原始记录不会被修改。代码可以自行处理这些公开输入，不能借工具产生新观测。

`analyze(inputs)` 的返回值须可序列化为有限JSON（最大2MiB）；numpy数组显式转`.tolist()`，标量转`.item()`。输出schema支持type、properties、required、items、additionalProperties、enum、数值/长度界限、description；不支持$ref、正则及组合schema，避免远程schema读取和复杂验证。

返回 `execution_id/status/result/stdout/stderr/error/artifacts/elapsed_seconds`，以及容器镜像ID、资源限制、执行器报告的CPU时间/峰值RSS。`success` 只表示代码运行和输出格式合格，不能解释为科学正确。`schema_error/error/timeout/memory_limit/output_limit/protocol_error/unavailable` 均是可供Agent调整的结果；外层`ok=true`只代表工具完成归档。代码计算耗时计入现实会话预算，不额外扣探针能量。

`output/` 内可输出最多10个PNG/JSON/CSV/TXT文件，合计不超过8MiB。文件名仅ASCII字母数字及`_.-`，不递归导出目录或符号链接。日志每路最多16000字符，超出标注截断。宿主再次校验输出格式、大小、文件名与PNG签名，只写出已验证文件；不解压来自模型的归档。图片和数据可从网页日志下载；下载也核验记录中的文件哈希并拒绝符号链接。以纯附件方式返回产物，不把代码文本当HTML执行。

完整结果保存为 `records/code_execution/code_<id>.json`，并支持`call_back`。`code_executions/code_<id>/`保留analysis.py、完整inputs.json、output_schema.json和artifacts。网页导出的实验JSON包含分析代码、数据引用与计算结果，不包含私有思考。

## 科研边界

代码是对已有观测的计算；代码自行估计的系数仍需通过正式候选拟合、整条轨迹独立验证与提交。最终law.py仍由受限表达式和冻结参数生成；本次不开放任意Python规律提交。训练/验证数据来源继续留档，按验证结果修改候选后须再取新实验验证。

控制组使用原始main.txt与7个schema。实验组只把工具数量/代码权限文字改为8个，再追加code.txt的接口、资源与证据说明；不加反思步骤，不强制调用代码，不规定假设或分析路线。

## E2 预注册设计

世界3/4/5 × baseline/code × 5次，共30次；两组全部新跑，E1仅作背景。固定DeepSeek Flash、thinking=true、reasoning_effort=high、总预算5M、单次输出393216、请求超时1800秒、现实会话3600秒、一次API重试、无模型调用次数上限。固定physics_version=v4、环境seed=42、无噪声、固定布局；独立评测20条隐藏轨迹，seed=1871。

每个重复内随机打乱6个任务，调度seed=2026110402；固定3并发、数值库单线程。两组使用相同环境/数值工具/评测；只差可选代码工具及必要接口说明。保存运行前代码哈希、完整配置、镜像ID；执行期间检查冻结内容不变，任何失败保留，不补跑。默认软件包镜像构建耗时不计入探索；每次容器启动和运行开销计入探索。

主指标：完整独立评测位置RMSE < 1e-6 的次数，分母为全部计划尝试。同时报告受理率、评测率、题目公式得分、RMSE分布、总耗时中位数、API等待时间、全部工具耗时、代码调用次数/成功率/容器耗时/报告CPU时间。缺失分数不当作0分。实验组未调用代码也保留，不剔除故障，不用事后阈值替换主指标。

代码用途在结束后依据公开代码、结果和后续工具调用归类，给出具体执行编号和证据；区分成功执行、产生新分析、影响后续候选、最终规律成功。仅凭先后顺序不能证明某次代码调用造成成功；组间对照衡量「开放代码能力及其说明」的整体效果，每格仅5次不能证明普遍优越。

运行：`.venv/bin/python benchmark_code.py --ask-key`。输出在`benchmarks/E2/`；原始会话在`runs/E2-*`，已结束会话进入工作台历史。测试真实容器：`SHORE_CODE_INTEGRATION=1 .venv/bin/python -m pytest tests/test_code_execution.py -q`。

隔离参数依据[Docker容器运行文档](https://docs.docker.com/engine/containers/run/)配置。
