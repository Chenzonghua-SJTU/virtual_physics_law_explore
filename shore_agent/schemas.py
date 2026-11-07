"""The complete model-facing action surface: current-session file tools and scientific actions."""
IDS = {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1, 'uniqueItems': True, 'maxItems': 102}
NUM = {'type': 'number'}
VECTOR = {'type': 'array', 'items': NUM, 'minItems': 2, 'maxItems': 2}


def obj(properties, required=None):
    return {'type': 'object', 'properties': properties,
            'required': list(properties) if required is None else required, 'additionalProperties': False}


def tool(name, description, properties, required=None):
    return {'type': 'function', 'function': {'name': name, 'description': description,
            'parameters': obj(properties, required)}}


SCHEMAS = [
    tool('observe_body', '获取指定绝对物理时刻的全体可见天体位置；天体可能运动。时刻严格递增且对齐任务网格，一次最多50时刻并消耗一次观察额度。新任务的第一束光已免费提供8时刻天体位置；追加观测用于扩展或加密时间覆盖。返回观测预览，完整数组按返回路径用read_file获取。',
         {'times': {'type': 'array', 'items': NUM, 'minItems': 1, 'maxItems': 50}}),
    tool('insert_probe', '真实投放一批探针；dt是采样间隔，K包含初态。加速度仅由观测速度中心差分估计。返回档案编号和明确标注的预览；完整数组按返回路径用read_file获取。',
         {'probes': {'type': 'array', 'minItems': 1, 'maxItems': 8,
                     'items': obj({'r0': VECTOR, 'v0': VECTOR, 'properties': obj({'mass': NUM, 'charge': NUM}, [])})},
          't0': NUM, 'dt': NUM, 'n_samples': {'type': 'integer', 'minimum': 1, 'maximum': 50}}),
    tool('fit_law_and_rollout', '拟合二维加速度候选，可依赖绝对t,x,y,vx,vy、当前瞬时天体位置及公开属性。新版sum_b在每个积分时刻从已取得的天体时间序列插值，使用sum_b需观测覆盖完整训练时段；缺少覆盖时先observe_body。使用任务DSL；最多5标量参数，禁止把拟合常数写入公式。目标为每条训练轨迹位置MSE等权平均；输出冻结公式、参数和训练输入快照。局部优化不保证全局最优。',
         {'law_spec': obj({'ax': {'type': 'string', 'maxLength': 600}, 'ay': {'type': 'string', 'maxLength': 600}}),
          'parameter_spec': {'type': 'array', 'maxItems': 5, 'items': obj({'name': {'type': 'string'}, 'initial': NUM, 'lower': NUM, 'upper': NUM}, ['name', 'initial'])},
          'train_probe_ids': IDS}),
    tool('validate_law', '固定公式与参数，在未参与该版本拟合的整条轨迹上验证。新版使用当次已取得的天体时间序列作为外部状态输入，并保存来源快照；范围不足请补observe_body，绝不重拟合参数。返回相对观测误差，包含天体插值误差，不设通过阈值。根据验证修改过候选后必须用新实验做最终检查。',
         {'law_id': {'type': 'string'}, 'test_probe_ids': IDS}),
    tool('list_files', '列出当前探索会话的公开实验文件或目录，不访问其他会话、源码或隐藏评测。返回路径供read_file和run_code使用。',
         {'path': {'type':'string','maxLength':300}, 'offset': {'type':'integer','minimum':0},
          'limit': {'type':'integer','minimum':1,'maximum':200}}, []),
    tool('read_file', '按路径读取当前会话已取得的公开文件。offset/limit按Unicode字符分页，返回next_offset；不静默截断。二进制产物可交run_code的read_bytes读取。',
         {'path': {'type':'string','minLength':1,'maxLength':300}, 'offset': {'type':'integer','minimum':0},
          'limit': {'type':'integer','minimum':1,'maximum':20000}}, ['path']),
    tool('analyze_residual', '确定性残差诊断：预测减观测、预测加速度减差分估计。报告均值、RMSE、最大值及与t,x,y,vx,vy的相关性；未定义相关返回null及原因，相关不代表因果。',
         {'law_id': {'type': 'string'}, 'probe_ids': IDS}),
    tool('submit', '提交固定已拟合版本；本地accepted仅指格式/有限输出/可执行性检查成功，立即结束会话，不表示物理正确。阶数1表示作用决定速度、2表示作用决定加速度；hidden_matter表示位置不可见的源；time_dependence表示固定完整状态后显式时间依赖。',
         {'law_id': {'type': 'string'},
          'physical_explanation': {'type': 'string', 'minLength': 1, 'maxLength': 20000, 'pattern': r'\S',
                                   'description': '用中文解释提交公式的物理含义：各项的作用方向与状态依赖、参数含义和单位、可由公式推导的运动性质、支持解释的实验/验证编号，以及适用范围和不可辨识性。区分观测证据、数学推论与物理假说，不得只复述公式或以低误差证明机制唯一。可分段。'},
          'claims': obj({'dynamics_order': {'type': 'integer', 'enum': [1, 2]},
                                                   'hidden_matter': {'type': 'boolean'}, 'time_dependence': {'type': 'boolean'}})})
]

CODE_SCHEMA = tool('run_code',
    '在隔离Python环境运行脚本，将结果赋给result。files可省略，默认[]；需要数据时选择list_files或工具返回的当前会话路径。'
    '代码中read_json(path)/read_file(path)/read_bytes(path)读取所选完整文件的只读快照，不必抄写数据；available_files列出本次路径。'
    'probe_arrays(record,time_axis="acceleration")按估计加速度时刻对齐，默认精确匹配。'
    'numpy/scipy/sympy/matplotlib可用，output/可导出png/json/csv/txt。每次新容器、无网络/宿主目录，90秒/1GiB/1CPU。'
    'NumPy结果自动转JSON；NaN/Infinity报错。返回精简结果和产物路径，完整结果可用read_file读取。'
    '执行成功不代表科学正确，仍需正式拟合、验证和submit。',
    {'code': {'type':'string','minLength':1,'maxLength':60000},
     'files': {'type':'array','items':{'type':'string','minLength':1,'maxLength':300},'uniqueItems':True,'maxItems':128}}, ['code'])


DYNAMICS_DIAGNOSTIC_SCHEMA = tool('diagnose_dynamics',
    '仅E5：显式选择本会话已取得的probe_ids，从相邻位置/速度观测做积分回归与近似径向幂次诊断。'
    '报告线性/非线性结构、公开属性比例的描述性证据和可辨识性限制；这些是观测近似，不是真实动力学或可提交答案。'
    '不读取隐藏真值、不投放新探针、不自动拟合或提交law；消耗正常工具运行时间。'
    '返回诊断预览，完整结果可按workspace_files路径read_file。用于此诊断的数据属于开发数据，最终检查应另用新轨迹。',
    {'probe_ids': IDS})


def tool_schemas(code_enabled=False, *, ruleset='e3', diagnostics_enabled=False, diagnostics_compact=False):
    import copy
    schemas = copy.deepcopy(SCHEMAS + ([CODE_SCHEMA] if code_enabled else []))
    if ruleset in ('e4', 'e5'):
        draft = copy.deepcopy(next(s for s in schemas if s['function']['name'] == 'submit'))
        draft['function']['name'] = 'save_draft'
        draft['function']['description'] = ('保存你明确选择的已拟合law_id及你依据观测判断的claims。'
            '格式与有限输出验证成功才替换上份草稿，不结束探索。预算截止时封存最后及时有效配对；'
            '不会自动选择规律、补写claims或检查物理真值。')
        schemas.append(draft)
    if ruleset == 'e5' and diagnostics_enabled is True:
        schemas.append(copy.deepcopy(DYNAMICS_DIAGNOSTIC_SCHEMA))
        if diagnostics_compact is True:
            descriptions = {item['function']['name']: item['function'] for item in schemas}
            descriptions['diagnose_dynamics']['description'] += (
                '优先用于已取得的第一束光与后续开发轨迹，避免手算比例。摘要并列给出各阶空间回归的训练/整轨迹交叉验证误差与主要项；'
                '请比较这些误差，若高阶明显改善，不要仅因径向幂次接近1就忽略非线性或交叉项。'
                '系数是候选结构与拟合初值的线索，仍须显式fit_law_and_rollout与新轨迹validate_law；'
                '不要把CV当最终验证，不要把近似径向投影当中心力已成立。')
            descriptions['insert_probe']['description'] += (
                '本轮只有10能量，每枚探针消耗1点。先利用免费观测与诊断确定实验目的；'
                '分批设计以保留修改候选后的新验证轨迹，不要在第一个假设前花尽能量。')
            descriptions['fit_law_and_rollout']['description'] += (
                'DSL语法提示：非整数数字幂与常数算术被禁不代表该物理结构被否定；平方根用sqrt(E)，'
                '例如E的三次平方根幂写成E*sqrt(E)，倒数写成1/(E*sqrt(E))，E须换为合法状态表达式。'
                '除法后多个因子作分母时必须加括号，a/b*c等于(a/b)*c。'
                '无噪声观测下，converged只表示优化停止；residual_scale_check有警告且时间仍充足时应继续比较结构或初值，不能声称已准确解释。')
    return schemas
