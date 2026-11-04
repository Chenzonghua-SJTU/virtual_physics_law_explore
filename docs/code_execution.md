# 可选 Python 分析工具与 E2/E3

`run_code` 由主 Agent 直接使用，没有新增子 Agent。默认关闭；网页高级设置的「允许 Agent 编写分析代码」可开启。执行环境不可用时开关禁用；不会自动降级为宿主 Python。CLI 在配置中设置 `code_execution.enabled=true`。

## 准备执行环境

需要可用的 Docker 引擎。Mac 上本项目使用专用 Colima profile，不改变当前 Docker context，不挂载用户目录：

```sh
colima start shore-code --cpu 4 --memory 6 --disk 20 --mount none --activate=false --ssh-config=false
docker --context colima-shore-code build -t shore-code:e3-v2 code_sandbox
```

Linux / 其他 Docker 环境可使用 `docker build -t shore-code:e3-v2 code_sandbox`，配置中的 `docker_context` 可指定受信任服务端 context。Mac 存在上述 profile 的 socket 时自动选用它。镜像仅包含执行器及 numpy/scipy/sympy/matplotlib，不复制项目、实验记录或仿真源码。构建 context 由 `.dockerignore` 限制为 Dockerfile 和 runner.py。

若官方默认下载源不可达，本次本机构建使用：

```sh
docker --context colima-shore-code build \
  --build-arg BASE_IMAGE=public.ecr.aws/docker/library/python:3.11-slim \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  -t shore-code:e3-v2 code_sandbox
```

默认每次1CPU、1GiB内存、90秒计算期限（容器启动/传输有最多8秒宽限）、64进程/线程、128MiB工作目录、32MiB临时目录。限时也受会话剩余时间限制；主机监督超时强制结束容器。容器非root、只读根文件系统、无网络、无宿主挂载、无Docker socket、丢弃全部 capabilities、禁止新增权限；Docker默认seccomp继续生效。每次重新创建并最终删除容器。标准库和任意Python语法可用，安全边界是容器，不是Python字符串或AST过滤器。

## 工具协议（v2）

`run_code`只有两个必填参数：`code`和`inputs`。不要求Agent编写输出schema。

```json
{
  "code": "import numpy as np\np = inputs['trajectories'][0]\nresult = {'n_samples': len(p['times']), 'mean_speed': np.linalg.norm(p['v_obs'], axis=1).mean()}",
  "inputs": {
    "trajectories": {"record_type": "probe", "record_ids": ["probe_0001"]}
  }
}
```

脚本直接使用预置的`inputs`，把输出赋给`result`；旧的`analyze(inputs)`函数形式仍兼容（脚本定义result时以它为准）。仅print的脚本也能运行：结果为null、返回stdout及无结构化结果提示，不会仅因缺少函数或result要求重跑。执行成功不等于科学正确，也不保证返回了有用分析。

每个别名对应完整记录的列表，单条也是列表；同类记录建议合并到一个别名。支持已有`probe/body_observation/law/validation/residual/code_execution`；最多16别名，每别名102条。只通过记录编号引用数据，不接受文件路径，不传入真实规律、隐藏评测、模型消息或密钥。输入逐条保留SHA256。探针`times/r_obs/v_obs`和`a_est_times/a_est`的时间轴可能不同，后者可能缺失；读取时应检查字段及形状。

NumPy数组和标量、元组自动转换为JSON；NaN/Infinity明确报错，不能静默补零或变null。最大结果2MiB；大表可主动输出到`output/`。对支持的结果只进行序列化，不替模型修改公式、填缺失值、插值或修复算法。

完整执行记录保存在`records/code_execution/`，代码、输入及产物仍保存在`code_executions/`。默认返回执行编号、状态、结果、精简日志、错误位置与输入字段/形状、产物清单；不重复回传代码、输出schema、来源哈希或容器元信息。小型比较表不再因超过6行而被截成3行。结果预览约8000字符，stdout/stderr各1500字符；超限显式标记truncated。原始记录保留允许大小内完整结果与有界日志（每路16000字符），不是由另一个模型总结。

按字段及行读取示例：

```json
{"record_type":"code_execution","record_ids":["code_example"],"field_path":["result","fits"],"offset":0,"limit":20}
```

上述参数交给`call_back`，要求唯一已取得记录及明确类型。field_path由字典键和非负列表下标组成；offset/limit对列表或字符串分页（最多1000项/字符），大页仍可能预览，可继续缩小范围。默认summary也使用精简代码结果视图；detail=full显式取回完整记录。后续代码可直接引用之前的code_execution记录并读`result`，不必先将数组全部送回对话。

`output/`导出最多10个PNG/JSON/CSV/TXT文件、总计8MiB；ASCII简单文件名、不递归目录/符号链接，校验格式/大小/哈希。网页可下载产物；完整实验导出继续保留代码和科学记录，不包含私有思考。

错误包含类型、错误行、相关代码和已取得输入的字段/形状。完整堆栈留档，默认返回精简版本。框架不自动更改代码重试。每次新容器、无隐含变量状态；资源、网络与宿主隔离约束不变。会话历史仍完整发送，本次不增加历史压缩、子Agent或研究状态更新。

## 科研边界

代码是对已有观测的计算；代码自行估计的系数仍需通过正式候选拟合、整条轨迹独立验证与提交。最终law.py仍由受限表达式和冻结参数生成；本次不开放任意Python规律提交。训练/验证数据来源继续留档，按验证结果修改候选后须再取新实验验证。

控制组使用原始main.txt与7个schema。实验组只把工具数量/代码权限文字改为8个，再追加code.txt的接口、资源与证据说明；不加反思步骤，不强制调用代码，不规定假设或分析路线。

## E2 R02 预注册设计

实验已完成，最终执行的是15次代码组复测，结果见[E2 R02报告](../benchmarks/E2/R02.md)，修改沿革见[实验与修改记录](experiment_history.md)。本节保留原始计划与范围调整，不是要求再次启动30次实验。

**范围调整：** 用户明确要求改完仅复测代码组15次。实际主结果为世界3/4/5各5次简化code；此前已结束的6次原工具组只单独保留，1次在途原工具组取消，其他原工具组不再启动。代码组不中断、不重跑，源码和配置不变。以下30次描述是最初方案；原调度快照和调整记录均保存在`benchmarks/E3/`。本轮不是完整的新随机对照，E2 R01仅作跨批次参考。

E2 R02重新运行世界3/4/5 × baseline/简化code × 每组5次，共30次，不复用E2 R01为本轮控制。high、总5M、单次输出393216、会话3600秒、3并发、单线程数值库、seed=42、v4、无噪声、隐藏评测20条/seed=1871与E2 R01一致。调度seed=2026110403。主指标仍为完整隐藏位置RMSE<1e-6；同时记录题目分、耗时、Token、代码错误类别和返回大小。

对比中的baseline仍为原main.txt和7工具；code使用普通脚本、自动科学类型序列化、精简返回、按字段读取及必要接口说明。只改上述接口，不增加强制反思、拟合频率或科学策略。E2 R01作为跨批次描述性对照；错误率下降需区分接口改进与“仅print不再报协议错”的状态定义变化，不能据此单独推断科学能力提高。

启动前冻结源码、配置及新镜像ID，保留E2 R01镜像及原记录。每个单元只运行一次，科学失败不补跑；遇到账户401/402停止队列。原始30次调度入口为`benchmark_code_v2.py`；范围调整后的实际续跑控制器为`benchmarks/E3/continue_code_only.py`，它用于接管当时在途会话，不是可重复使用的新实验启动命令。结果保存在`benchmarks/E3/`及本地`runs/E3-*`。运行中冻结代码未修改；只复核现有结果可使用E2 R02报告中的审计命令，无需模型调用。

## E2 R01 预注册设计

实验已完成，结果见[E2 R01报告](../benchmarks/E2/R01.md)。以下保留最初预注册；首次运行遭遇账户HTTP402后，用户恢复额度并授权补跑21个受影响单元，补跑前记录了协议调整，原9个正常完成单元及所有失败档案保留。科学失败没有重跑，源码、配置、镜像保持冻结。

世界3/4/5 × baseline/code × 5次，共30次；两组全部新跑，E1仅作背景。固定DeepSeek Flash、thinking=true、reasoning_effort=high、总预算5M、单次输出393216、请求超时1800秒、现实会话3600秒、一次API重试、无模型调用次数上限。固定physics_version=v4、环境seed=42、无噪声、固定布局；独立评测20条隐藏轨迹，seed=1871。

每个重复内随机打乱6个任务，调度seed=2026110402；固定3并发、数值库单线程。两组使用相同环境/数值工具/评测；只差可选代码工具及必要接口说明。保存运行前代码哈希、完整配置、镜像ID；执行期间检查冻结内容不变，任何失败保留，不补跑。默认软件包镜像构建耗时不计入探索；每次容器启动和运行开销计入探索。

主指标：完整独立评测位置RMSE < 1e-6 的次数，分母为全部计划尝试。同时报告受理率、评测率、题目公式得分、RMSE分布、总耗时中位数、API等待时间、全部工具耗时、代码调用次数/成功率/容器耗时/报告CPU时间。缺失分数不当作0分。实验组未调用代码也保留，不剔除故障，不用事后阈值替换主指标。

代码用途在结束后依据公开代码、结果和后续工具调用归类，给出具体执行编号和证据；区分成功执行、产生新分析、影响后续候选、最终规律成功。仅凭先后顺序不能证明某次代码调用造成成功；组间对照衡量「开放代码能力及其说明」的整体效果，每格仅5次不能证明普遍优越。

运行：`.venv/bin/python benchmark_code.py --ask-key`。输出在`benchmarks/E2/`；原始会话在`runs/E2-*`，已结束会话进入工作台历史。测试真实容器：`SHORE_CODE_INTEGRATION=1 .venv/bin/python -m pytest tests/test_code_execution.py -q`。

隔离参数依据[Docker容器运行文档](https://docs.docker.com/engine/containers/run/)配置。
