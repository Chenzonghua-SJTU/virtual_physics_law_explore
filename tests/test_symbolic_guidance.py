"""Verify SR guidance delivery and agreement with the callable interface, without models."""
import copy
from pathlib import Path

import pytest
from jsonschema import ValidationError, validate

from shore_agent.agent import Agent
from shore_agent.model import ModelError
from shore_agent.schemas import tool_schemas


GUIDANCE = (Path(__file__).resolve().parents[1] / 'shore_agent/prompts/symbolic.txt').read_text(
    encoding='utf-8')


class CaptureClient:
    usage = {'calls': 0, 'completion_tokens': 0, 'total_tokens': 0}

    def complete(self, messages, tools=None, role='main'):
        self.request = copy.deepcopy({'messages': messages, 'tools': tools})
        raise ModelError('test_capture_only')


class PromptRuntime:
    code_enabled = False
    last_valid_draft = None

    def __init__(self, ruleset, symbolic):
        self.ruleset = ruleset
        self.symbolic_enabled = symbolic
        self.schemas = tool_schemas(ruleset=ruleset, symbolic_enabled=symbolic)

    def budget(self):
        return {'wall_seconds_remaining': 300, 'energy_remaining': 10,
                'session_ended': False}

    def mission(self):
        return {'ok': True, 'data': {}, 'budget': self.budget()}

    def finalize_draft(self, reason):
        return None


@pytest.mark.parametrize('ruleset,symbolic', [('e3', False), ('e5', False), ('e5', True)])
def test_guidance_is_delivered_exactly_when_search_is_available(tmp_path, ruleset, symbolic):
    client = CaptureClient()
    runtime = PromptRuntime(ruleset, symbolic)
    result = Agent(client, runtime, tmp_path, {}).run()
    assert result['reason'] == 'test_capture_only'
    system = client.request['messages'][0]['content']
    assert (GUIDANCE in system) is symbolic
    assert system.count(GUIDANCE) == int(symbolic)
    names = {item['function']['name'] for item in client.request['tools']}
    assert ('symbolic_regression' in names) is symbolic
    assert client.usage['calls'] == 0


def test_recommended_search_budgets_and_sampling_limits_are_callable():
    functions = {item['function']['name']: item['function'] for item in
                 tool_schemas(ruleset='e5', symbolic_enabled=True)}
    search_schema = functions['symbolic_regression']['parameters']
    assert '47秒' in GUIDANCE and '上限60秒' in GUIDANCE
    for seconds in (40, 47, 50, 60):
        validate({'train_probe_ids': ['current_session_probe'],
                  'time_budget_seconds': seconds}, search_schema)
    with pytest.raises(ValidationError):
        validate({'train_probe_ids': ['current_session_probe'],
                  'time_budget_seconds': 61}, search_schema)
    probe_schema = functions['insert_probe']['parameters']
    assert 'n_samples含初态、最多50' in GUIDANCE
    assert '(n_samples-1)*dt' in GUIDANCE
    assert probe_schema['properties']['n_samples']['maximum'] == 50
    assert probe_schema['properties']['probes']['maxItems'] == 8
    assert functions['fit_law_and_rollout']['parameters']['properties']['parameter_spec']['maxItems'] == 5


def test_guidance_keeps_complementary_sampling_and_evidence_boundaries():
    # These are the observed regressions, not expectations about any universe's law.
    requirements = (
        '属性差异探针', '密采样局部轨迹', '不同绝对t0的同初态对照',
        '长轨迹', '不要统一缩短总时长', 'timeout不是调用失败',
        '不能原样交拟合', '重命名参数避免意外共享',
        '预算充足应尝试替代结构', '不能作独立验证',
        '约6枚付费训练探针', '1–2个相同完整初态', '天体可见不证明力来自天体',
        '免费粗轨迹可仅作定性依据', '先原式拟合再考虑改写',
        '仍只有单t0', '新验证应包含较长时域', 'r^(1-p)', '未知源强度不等于hidden_matter',
    )
    assert all(item in GUIDANCE for item in requirements)
    assert len(GUIDANCE) <= 1500, 'Keep this supplemental prompt short.'
    assert 'world_' not in GUIDANCE and 'probe_000' not in GUIDANCE
