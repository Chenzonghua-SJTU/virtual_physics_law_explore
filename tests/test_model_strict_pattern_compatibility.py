"""Full explanations survive Qwen grammar without loosening runtime validation."""
import copy
import json

import jsonschema
import pytest

from shore_agent.model import _normalize_strict_schema_patterns
from shore_agent.schemas import tool_schemas
from test_model_strict_tools import local_overrides
from test_qwen_model import answer_stream, client as qwen_client


NORMALIZED_PATTERN = r'^[\s\S]*\S[\s\S]*$'
TEXTS = [
    '本', '本次实验支持这个候选规律。',
    '第一段说明。\n第二段是本次观测支持的解释。',
    '解释中有 spaces 与数字 123。', ' A \n',
    ('这是用于协议验证的长段落，不对应任何物理世界或答案。' * 20
     + '\n\n' + '第二段继续保留完整解释和不确定性说明。' * 20),
]
BLANKS = ['', ' ', '\n\t', '\r\n\t ']


def explanation_schema():
    tool = next(t for t in tool_schemas(ruleset='e5') if t['function']['name'] == 'submit')
    return copy.deepcopy(tool['function']['parameters']['properties']['physical_explanation'])


@pytest.mark.parametrize('choice', [None, 'required'])
def test_only_strict_request_copy_normalizes_submit_and_draft_patterns(tmp_path, monkeypatch, choice):
    schemas = tool_schemas(ruleset='e5')
    original = copy.deepcopy(schemas)
    value, requests, _ = qwen_client(tmp_path, monkeypatch, [answer_stream()],
                                     **local_overrides(strict_tools=True))
    try:
        value.complete([{'role': 'user', 'content': 'synthetic'}], tools=schemas,
                       tool_choice_override=choice)
    finally:
        value.close()
    body = json.loads(requests[0].content)
    assert schemas == original
    for tool, given in zip(body['tools'], schemas):
        expected = copy.deepcopy(given)
        expected['function']['strict'] = True
        if expected['function']['name'] in ('submit', 'save_draft'):
            field = expected['function']['parameters']['properties']['physical_explanation']
            assert field['pattern'] == r'\S'
            field['pattern'] = NORMALIZED_PATTERN
        assert tool == expected
    assert body['tool_choice'] == (choice or 'auto')
    assert body['max_tokens'] == 4096 and body['seed'] == 42


@pytest.mark.parametrize('text', TEXTS + BLANKS + ['\u3000', '\u00a0', '观测' * 10000 + '。'])
def test_jsonschema_semantics_and_length_constraints_remain_identical(text):
    original = explanation_schema()
    normalized = copy.deepcopy(original)
    _normalize_strict_schema_patterns(normalized)
    validator = jsonschema.Draft202012Validator
    assert validator(original).is_valid(text) == validator(normalized).is_valid(text)
    assert normalized == {**original, 'pattern': NORMALIZED_PATTERN}
    if text in TEXTS:
        assert validator(normalized).is_valid(text)
    if text in BLANKS:
        assert not validator(normalized).is_valid(text)


def test_other_regexes_and_non_string_nodes_are_unchanged():
    schema = {'type': 'object', 'properties': {
        'anchored': {'type': 'string', 'pattern': '^[a-z]+$'},
        'unknown': {'pattern': r'\S'},
        'nested': {'type': 'array', 'items': {'type': 'string', 'pattern': r'\S'}}}}
    expected = copy.deepcopy(schema)
    expected['properties']['nested']['items']['pattern'] = NORMALIZED_PATTERN
    _normalize_strict_schema_patterns(schema)
    assert schema == expected


@pytest.mark.parametrize('choice', ['auto', 'required'])
@pytest.mark.parametrize('tool_name', ['submit', 'save_draft'])
def test_installed_xgrammar_accepts_complete_long_and_multiline_explanations(choice, tool_name):
    # Optional serving-environment integration test. This compiles a grammar on
    # CPU using a byte vocabulary; no model weights, HTTP or generation occurs.
    xgr = pytest.importorskip('xgrammar')
    from xgrammar.builtin_structural_tag import get_builtin_structural_tag
    original = explanation_schema()
    normalized = copy.deepcopy(original)
    _normalize_strict_schema_patterns(normalized)
    compiler = xgr.GrammarCompiler(
        xgr.TokenizerInfo([bytes([i]) for i in range(256)], stop_token_ids=[0]), max_threads=1)

    def compile_field(field):
        tool = next(t for t in tool_schemas(ruleset='e5') if t['function']['name'] == tool_name)
        tool['function']['strict'] = True
        tool['function']['parameters']['properties']['physical_explanation'] = field
        tag = get_builtin_structural_tag('qwen_3_coder', [tool], tool_choice=choice, reasoning=False)
        return compiler.compile_grammar(xgr.Grammar.from_structural_tag(tag))

    def accepts_complete(compiled, text):
        matcher = xgr.GrammarMatcher(compiled, terminate_without_stop_token=True)
        output = ('<tool_call>\n<function=' + tool_name + '>\n'
                  '<parameter=law_id>synthetic-law</parameter>\n<parameter=physical_explanation>'
                  + text + '</parameter>\n<parameter=claims>'
                  '{"dynamics_order": 2, "hidden_matter": false, "time_dependence": false}'
                  '</parameter>\n</function>\n</tool_call>')
        return matcher.accept_string(output) and matcher.is_terminated()

    before, after = compile_field(original), compile_field(normalized)
    assert accepts_complete(before, '本')
    for text in TEXTS:
        assert accepts_complete(after, text)
    for text in TEXTS[1:4]:
        assert not accepts_complete(before, text)  # Reproduces the full-match bug.
    for text in BLANKS:
        assert not accepts_complete(after, text)
