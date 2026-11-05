# 可选 Python 分析工具与 E2

`run_code` 由主 Agent 直接使用，没有新增子 Agent。默认关闭；网页高级设置的「允许 Agent 编写分析代码」可开启。执行环境不可用时开关禁用；不会自动降级为宿主 Python。CLI 在配置中设置 `code_execution.enabled=true`。

## 准备执行环境

需要可用的 Docker 引擎。Mac 上本项目使用专用 Colima profile，不改变当前 Docker context，不挂载用户目录：

```sh
colima start shore-code --cpu 4 --memory 6 --disk 20 --mount none --activate=false --ssh-config=false
docker --context colima-shore-code build -t shore-code:e2-r04 code_sandbox
```

Linux / 其他 Docker 环境可使用 `docker build -t shore-code:e2-r04 code_sandbox`，配置中的 `docker_context` 可指定受信任服务端 context。Mac 存在上述 profile 的 socket 时自动选用它。镜像仅包含执行器及 numpy/scipy/sympy/matplotlib，不复制项目、实验记录或仿真源码。构建 context 由 `.dockerignore` 限制为 Dockerfile 和 runner.py。

若官方默认下载源不可达，本次本机构建使用：

```sh
docker --context colima-shore-code build \
  --build-arg BASE_IMAGE=public.ecr.aws/docker/library/python:3.11-slim \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  -t shore-code:e2-r04 code_sandbox
```

默认每次1CPU、1GiB内存、90秒计算期限（容器启动/传输有最多8秒宽限）、64进程/线程、128MiB工作目录、32MiB临时目录。限时也受会话剩余时间限制；主机监督超时强制结束容器。容器非root、只读根文件系统、无网络、无宿主挂载、无Docker socket、丢弃全部 capabilities、禁止新增权限；Docker默认seccomp继续生效。每次重新创建并最终删除容器。标准库和任意Python语法可用，安全边界是容器，不是Python字符串或AST过滤器。

## 工具协议（v4 / E2 R04）

`call_back`已从当前模型工具和运行时移除，改为`list_files`和`read_file`。默认8个工具，启用run_code后9个。旧日志仍可在前端展示，但不会重新开放旧接口。

### 当前会话文件目录

这些是应用提供的虚拟路径，不是宿主操作系统路径：

```text
observations/probe_0001.json
observations/body_0001.json
laws/law_1.json
validations/validation_*.json
residuals/residual_*.json
submissions/submission_*.json
analyses/code_*/analysis.py
analyses/code_*/result.json
analyses/code_*/record.json
analyses/code_*/stdout.txt
analyses/code_*/stderr.txt
analyses/code_*/artifacts/output.csv
```

只登记当前会话已经取得的记录，以及通过导出校验的分析产物。任务包的workspace列出初始文件；后续工具的workspace_files列出新增文件。不会扫描运行目录或宿主磁盘，不提供历史会话、仿真源码、模型消息、配置密钥或独立隐藏评测。字面路径穿越、绝对路径和符号链接均不可用于获取额外数据。

```json
{"path":"observations/","offset":0,"limit":100}
```

上述参数调用list_files：返回直接子目录/文件，按路径排序，最多200项，用next_offset继续分页。

```json
{"path":"observations/probe_0001.json","offset":0,"limit":12000}
```

上述参数调用read_file：offset/limit是Unicode字符位置/数量，最多20000字符，返回content、total_chars、next_offset、truncated及完整文件SHA256。没有field_path或record_type；JSON保留完整结构，由代码自行解析。二进制产物应传给run_code读取。

### 代码读取相同路径

run_code只要求code；files可省略，默认空列表。需要数据时显式选择至多128个路径，总计不超过16MiB。框架验证路径属于当前会话，将完整字节快照发送给容器，不挂载宿主目录。

```json
{
  "files": ["observations/probe_0001.json"],
  "code": "p = read_json('observations/probe_0001.json')\ns = probe_arrays(p, time_axis='acceleration')\nresult = {'t': s['t'], 'r': s['r'], 'a_est': s['a'], 'alignment': s['alignment']}"
}
```

脚本中read_json(path)解析完整JSON，read_file(path)返回完整UTF-8文本，read_bytes(path)返回二进制字节，available_files列出本次传入路径。它们读取只读快照；read_json每次返回独立对象，修改对象不会改写快照或原记录。未在files中选择的文件不能读取，即使它已经属于当前会话。虚拟路径不支持宿主open访问；CSV可用StringIO(read_file(path))处理，PNG可用BytesIO(read_bytes(path))处理。写入仅通过output/显式产物。

任务包与新观测的code_inputs列出真实字段、路径和数组形状。探针记录times为(N,)，r_obs/v_obs为(N,2)；a_est有自己的a_est_times。probe_arrays(p)返回观测时刻的t/r/v；time_axis="acceleration"按估计加速度时刻返回t/r/v/a。默认精确匹配；需插值时显式interpolation="linear"，禁止外推、静默截短或补零。a仍是差分估计，alignment说明方法。天体记录使用times/body_ids/positions_obs，位置轴为(时间,天体,xy)，不能默认天体静止。

普通脚本赋值result即可；兼容已有analyze(inputs)形式及仅print输出，但新模型接口不再使用inputs/别名协议。NumPy数组/标量和元组自动转换，NaN/Infinity明确报错。结果最多2MiB；默认结果预览约8000字符，stdout/stderr各1500字符，超限明确标注。允许大小内完整结果及每路最多16000字符日志保留。精简返回不重复代码/来源哈希，详细信息见analyses下的文件。

output/最多导出10个PNG/JSON/CSV/TXT文件，总计8MiB；只接受普通文件，校验名称、格式及哈希，不递归或导出符号链接。产物可经read_file或后续run_code读取，也可从网页下载。输入文件路径/哈希/字节数及实际快照分别保存在执行记录和code_executions/<id>/input_files.json；旧档案格式不改写。

每次新容器，无网络、宿主挂载或隐含变量状态。没有自动修代码重试、历史压缩或额外子Agent。执行成功不代表科学正确，读取文件不产生新的观测。

## 科研边界

代码是对已有观测的计算；代码自行估计的系数仍需通过正式候选拟合、整条轨迹独立验证与提交。最终law.py仍由受限表达式和冻结参数生成；本次不开放任意Python规律提交。训练/验证数据来源继续留档，按验证结果修改候选后须再取新实验验证。

历史E2 R01/R02控制组使用原始main.txt与7个schema，代码组增加run_code。E2 R04改变了读取接口，不能将新配置直接当作历史控制组；重新比较需另行冻结配置。

## E2 R02 预注册设计

实验已完成，最终执行的是15次代码组复测，结果见[E2 R02报告](../experiments/E2/R02.md)，修改沿革见[实验与修改记录](../experiments/experiment.md)。本节保留原始计划与范围调整，不是要求再次启动30次实验。

**范围调整：** 用户明确要求改完仅复测代码组15次。实际主结果为世界3/4/5各5次简化code；此前已结束的6次原工具组只单独保留，1次在途原工具组取消，其他原工具组不再启动。代码组不中断、不重跑，源码和配置不变。以下30次描述是最初方案；原调度快照和调整记录均保存在`experiments/E2/R02/`。本轮不是完整的新随机对照，E2 R01仅作跨批次参考。

E2 R02重新运行世界3/4/5 × baseline/简化code × 每组5次，共30次，不复用E2 R01为本轮控制。high、总5M、单次输出393216、会话3600秒、3并发、单线程数值库、seed=42、v4、无噪声、隐藏评测20条/seed=1871与E2 R01一致。调度seed=2026110403。主指标仍为完整隐藏位置RMSE<1e-6；同时记录题目分、耗时、Token、代码错误类别和返回大小。

对比中的baseline仍为原main.txt和7工具；code使用普通脚本、自动科学类型序列化、精简返回、按字段读取及必要接口说明。只改上述接口，不增加强制反思、拟合频率或科学策略。E2 R01作为跨批次描述性对照；错误率下降需区分接口改进与“仅print不再报协议错”的状态定义变化，不能据此单独推断科学能力提高。

启动前冻结源码、配置及新镜像ID，保留E2 R01镜像及原记录。每个单元只运行一次，科学失败不补跑；遇到账户401/402停止队列。原始30次调度入口为`benchmark_code_v2.py`；范围调整后的实际续跑控制器为`experiments/E2/R02/continue_code_only.py`，它用于接管当时在途会话，不是可重复使用的新实验启动命令。结果保存在`experiments/E2/R02/`及本地`runs/E3-*`。运行中冻结代码未修改；只复核现有结果可使用E2 R02报告中的审计命令，无需模型调用。

## E2 R01 预注册设计

实验已完成，结果见[E2 R01报告](../experiments/E2/R01.md)。以下保留最初预注册；首次运行遭遇账户HTTP402后，用户恢复额度并授权补跑21个受影响单元，补跑前记录了协议调整，原9个正常完成单元及所有失败档案保留。科学失败没有重跑，源码、配置、镜像保持冻结。

世界3/4/5 × baseline/code × 5次，共30次；两组全部新跑，E1仅作背景。固定DeepSeek Flash、thinking=true、reasoning_effort=high、总预算5M、单次输出393216、请求超时1800秒、现实会话3600秒、一次API重试、无模型调用次数上限。固定physics_version=v4、环境seed=42、无噪声、固定布局；独立评测20条隐藏轨迹，seed=1871。

每个重复内随机打乱6个任务，调度seed=2026110402；固定3并发、数值库单线程。两组使用相同环境/数值工具/评测；只差可选代码工具及必要接口说明。保存运行前代码哈希、完整配置、镜像ID；执行期间检查冻结内容不变，任何失败保留，不补跑。默认软件包镜像构建耗时不计入探索；每次容器启动和运行开销计入探索。

主指标：完整独立评测位置RMSE < 1e-6 的次数，分母为全部计划尝试。同时报告受理率、评测率、题目公式得分、RMSE分布、总耗时中位数、API等待时间、全部工具耗时、代码调用次数/成功率/容器耗时/报告CPU时间。缺失分数不当作0分。实验组未调用代码也保留，不剔除故障，不用事后阈值替换主指标。

代码用途在结束后依据公开代码、结果和后续工具调用归类，给出具体执行编号和证据；区分成功执行、产生新分析、影响后续候选、最终规律成功。仅凭先后顺序不能证明某次代码调用造成成功；组间对照衡量「开放代码能力及其说明」的整体效果，每格仅5次不能证明普遍优越。

运行：`.venv/bin/python benchmark_code.py --ask-key`。输出在`experiments/E2/`；原始会话在`runs/E2-*`，已结束会话进入工作台历史。测试真实容器：`SHORE_CODE_INTEGRATION=1 .venv/bin/python -m pytest tests/test_code_execution.py -q`。

隔离参数依据[Docker容器运行文档](https://docs.docker.com/engine/containers/run/)配置。
