"""The complete model-facing action surface: exactly seven tools."""
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
    tool('observe_body', '获取指定绝对物理时刻的全体可见天体位置；天体可能运动。时刻严格递增且对齐任务网格，一次最多50时刻并消耗一次观察额度。新任务的第一束光已免费提供8时刻天体位置；追加观测用于扩展或加密时间覆盖。返回观测预览，完整数组用call_back获取。',
         {'times': {'type': 'array', 'items': NUM, 'minItems': 1, 'maxItems': 50}}),
    tool('insert_probe', '真实投放一批探针；dt是采样间隔，K包含初态。加速度仅由观测速度中心差分估计。返回档案编号和明确标注的预览；完整数组用call_back获取。',
         {'probes': {'type': 'array', 'minItems': 1, 'maxItems': 8,
                     'items': obj({'r0': VECTOR, 'v0': VECTOR, 'properties': obj({'mass': NUM, 'charge': NUM}, [])})},
          't0': NUM, 'dt': NUM, 'n_samples': {'type': 'integer', 'minimum': 1, 'maximum': 50}}),
    tool('fit_law_and_rollout', '拟合二维加速度候选，可依赖绝对t,x,y,vx,vy、当前瞬时天体位置及公开属性。新版sum_b在每个积分时刻从已取得的天体时间序列插值，使用sum_b需观测覆盖完整训练时段；缺少覆盖时先observe_body。使用任务DSL；最多5标量参数，禁止把拟合常数写入公式。目标为每条训练轨迹位置MSE等权平均；输出冻结公式、参数和训练输入快照。局部优化不保证全局最优。',
         {'law_spec': obj({'ax': {'type': 'string', 'maxLength': 600}, 'ay': {'type': 'string', 'maxLength': 600}}),
          'parameter_spec': {'type': 'array', 'maxItems': 5, 'items': obj({'name': {'type': 'string'}, 'initial': NUM, 'lower': NUM, 'upper': NUM}, ['name', 'initial'])},
          'train_probe_ids': IDS}),
    tool('validate_law', '固定公式与参数，在未参与该版本拟合的整条轨迹上验证。新版使用当次已取得的天体时间序列作为外部状态输入，并保存来源快照；范围不足请补observe_body，绝不重拟合参数。返回相对观测误差，包含天体插值误差，不设通过阈值。根据验证修改过候选后必须用新实验做最终检查。',
         {'law_id': {'type': 'string'}, 'test_probe_ids': IDS}),
    tool('call_back', '只读已取得档案，不产生观测、不抽新噪声、不重新计算。full要求明确编号。',
         {'record_type': {'type': 'string', 'enum': ['all', 'body_observation', 'probe', 'law', 'validation', 'residual', 'submission'], 'default': 'all'},
          'record_ids': {'type': ['array', 'null'], 'items': {'type': 'string'}, 'maxItems': 102},
          'detail': {'type': 'string', 'enum': ['summary', 'full'], 'default': 'summary'}}, []),
    tool('analyze_residual', '确定性残差诊断：预测减观测、预测加速度减差分估计。报告均值、RMSE、最大值及与t,x,y,vx,vy的相关性；未定义相关返回null及原因，相关不代表因果。',
         {'law_id': {'type': 'string'}, 'probe_ids': IDS}),
    tool('submit', '提交固定已拟合版本；本地accepted仅指格式/有限输出/可执行性检查成功，立即结束会话，不表示物理正确。阶数1表示作用决定速度、2表示作用决定加速度；hidden_matter表示位置不可见的源；time_dependence表示固定完整状态后显式时间依赖。',
         {'law_id': {'type': 'string'},
          'physical_explanation': {'type': 'string', 'minLength': 1, 'maxLength': 20000, 'pattern': r'\S',
                                   'description': '用中文解释提交公式的物理含义：各项的作用方向与状态依赖、参数含义和单位、可由公式推导的运动性质、支持解释的实验/验证编号，以及适用范围和不可辨识性。区分观测证据、数学推论与物理假说，不得只复述公式或以低误差证明机制唯一。可分段。'},
          'claims': obj({'dynamics_order': {'type': 'integer', 'enum': [1, 2]},
                                                   'hidden_matter': {'type': 'boolean'}, 'time_dependence': {'type': 'boolean'}})})
]

# Baseline is deliberately byte-for-byte unchanged for E2's control arm.
CODE_SCHEMA = tool('run_code',
    '在隔离Python环境运行普通脚本。inputs已可用，把计算结果赋给result；无需定义函数或输出schema。'
    'inputs可省略，默认{}；引用记录时各别名对应完整记录列表，不必抄写观测。'
    'input_info给出实际字段/形状/编号；get_record(alias,id)取记录，probe_arrays(record,time_axis="acceleration")按估计加速度时刻精确对齐。'
    '预装numpy/scipy/sympy/matplotlib；可在output/保存png/json/csv/txt文件。'
    '每次全新容器，90秒/1GiB/1CPU，无网络和宿主文件；不产生新观测，不访问真实规律。'
    'NumPy数组/标量自动转JSON，NaN/Infinity明确报错。返回精简结果、日志/报错、执行编号和产物；'
    '大结果完整存档，可用call_back按field_path和offset/limit读取。失败可修改代码重试。输出不是自动验证通过；'
    '拟合及最终验证/submit仍使用原工具。',
    {'code': {'type': 'string', 'minLength': 1, 'maxLength': 60000},
     'inputs': {'type': 'object', 'minProperties': 0, 'maxProperties': 16,
                'propertyNames': {'pattern': r'^[A-Za-z][A-Za-z0-9_]{0,39}$'},
                'additionalProperties': obj({
                    'record_type': {'type': 'string', 'enum': ['body_observation', 'probe', 'law', 'validation', 'residual', 'code_execution']},
                    'record_ids': IDS})}}, required=['code'])


def tool_schemas(code_enabled=False):
    if not code_enabled:
        return SCHEMAS
    import copy
    schemas = copy.deepcopy(SCHEMAS)
    callback = next(s for s in schemas if s['function']['name'] == 'call_back')
    callback['function']['parameters']['properties']['record_type']['enum'].append('code_execution')
    callback['function']['parameters']['properties'].update({
        'field_path': {'type':'array', 'maxItems':12, 'items':{'type':['string','integer']},
                       'description':'可选：读取单条已取得记录的字段，如["result","fits"]。须明确record_type和唯一record_id。'},
        'offset': {'type':'integer','minimum':0,'description':'field_path所选列表/字符串的起始位置，默认0。'},
        'limit': {'type':'integer','minimum':1,'maximum':1000,'description':'field_path所选列表/字符串最多取多少项/字符，默认20；大块会标记预览。'}
    })
    return schemas + [copy.deepcopy(CODE_SCHEMA)]
