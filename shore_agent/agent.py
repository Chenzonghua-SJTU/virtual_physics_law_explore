"""Transparent main research loop. Files are restricted to acquired current-session data."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from .model import ModelError
from .store import append_event


def _save(path, value):
    temp = Path(path).with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temp.replace(path)


class Agent:
    def __init__(self, client, tool_runtime, run_dir: Path, config: dict):
        self.client = client
        self.runtime = tool_runtime
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.config = config
        self.messages = []
        self.last_budget = {}
        self.submission = None
        self.session_ended = False
        self.ruleset = getattr(tool_runtime, 'ruleset', 'e3')
        self.guidance_profile = config.get('guidance_profile', 'baseline')
        if self.guidance_profile not in ('baseline', 'e3', 'concise'):
            raise ValueError('guidance_profile must be baseline, e3 or concise')
        self.e4 = self.ruleset in ('e4', 'e5')
        self.finish_reserve_seconds = 30.0 if self.e4 else 0.0
        self.max_no_action = config.get('max_no_action', 3)
        if isinstance(self.max_no_action, bool) or not isinstance(self.max_no_action, int) or self.max_no_action < 1:
            raise ValueError('max_no_action must be a positive integer')
        self.loop_recovery = config.get('loop_recovery', False)
        if type(self.loop_recovery) is not bool:
            raise ValueError('loop_recovery must be boolean')
        self._repeat_states = {}
        self._last_observation_version = None
        self._fallback_observation_version = 0
        self._length_recovered = False

    _DETERMINISTIC_TOOLS = frozenset({'read_file', 'list_files', 'fit_law_and_rollout',
                                    'validate_law', 'analyze_residual', 'observe_body'})

    def _observation_version(self):
        records = getattr(getattr(self.runtime, 'store', None), 'records', None)
        if isinstance(records, dict):
            return (len(records.get('probe', {})), len(records.get('body_observation', {})))
        return self._fallback_observation_version

    def _repeat_key(self, name, args, raw_args):
        version = self._observation_version()
        if version != self._last_observation_version:
            self._repeat_states.clear()
            self._last_observation_version = version
        def normalized(value):
            if isinstance(value, float) and value.is_integer():
                return int(value)
            if isinstance(value, list):
                return [normalized(v) for v in value]
            if isinstance(value, dict):
                return {k: normalized(v) for k, v in value.items()}
            return value
        canonical = (json.dumps(normalized(args), sort_keys=True, separators=(',', ':'), allow_nan=False)
                     if args is not None else 'invalid_json:' + raw_args.strip())
        # File contents/listings can change after a new law, validation or code
        # artifact without acquiring another physical observation. Bind ONLY
        # this file call to its public view; do not reset fit/validate counters.
        file_view = None
        if name in ('list_files', 'read_file') and args is not None:
            reader = getattr(getattr(self.runtime, 'files', None), name, None)
            if callable(reader):
                try:
                    view = reader(**args)
                except Exception as exc:
                    view = {'error_type': type(exc).__name__, 'error': str(exc)[:500]}
                file_view = hashlib.sha256(json.dumps(view, sort_keys=True, ensure_ascii=False,
                                                      allow_nan=False).encode('utf-8')).hexdigest()
        return name, canonical, file_view

    def _repeat_block_reason(self, key):
        state = self._repeat_states.get(key, {})
        if state.get('same_failures', 0) >= 2:
            return 'repeated_tool_failure_limit'
        if key[0] in self._DETERMINISTIC_TOOLS and state.get('attempts', 0) >= 2:
            return 'repeated_deterministic_call_limit'
        return None

    def _record_repeat(self, key, result):
        name = key[0]
        if result.get('ok') and name in ('insert_probe', 'observe_body'):
            records = getattr(getattr(self.runtime, 'store', None), 'records', None)
            if not isinstance(records, dict):
                self._fallback_observation_version += 1
            # Actual acquired-observation counts reset on the next call. A new
            # law/validation ID never advances this version.
            if name == 'insert_probe' or self._observation_version() != self._last_observation_version:
                self._repeat_states.pop(key, None)
                return None
            # Re-reading a cached body observation is not a fresh measurement.
        state = self._repeat_states.setdefault(key, {'attempts': 0, 'same_failures': 0})
        state['attempts'] += 1
        error = result.get('error') or {}
        # Stable error codes identify the same failure even when a backend adds
        # a request ID or changing time value to its human-readable message.
        code = error.get('code')
        fingerprint = ('code:' + code if isinstance(code, str) and code else
                       json.dumps(error, sort_keys=True, ensure_ascii=False, allow_nan=False))
        if result.get('ok'):
            state['same_failures'] = 0
            state.pop('error_fingerprint', None)
        else:
            state['same_failures'] = state['same_failures'] + 1 if state.get('error_fingerprint') == fingerprint else 1
            state['error_fingerprint'] = fingerprint
        if result.get('ok') and (name not in self._DETERMINISTIC_TOOLS or state['attempts'] < 2):
            return None
        notice = {'tool': name, 'identical_attempts_without_new_observations': state['attempts'],
                  'same_error_failures': state['same_failures'], 'budget': copy.deepcopy(self.last_budget)}
        if name in ('list_files', 'read_file'):
            notice['relevant_file_view_unchanged'] = True
        if not result.get('ok'):
            notice['last_error'] = {'code': error.get('code'), 'message': str(error.get('message', ''))[:500]}
        notice['instruction'] = (
            '本次操作没有取得新的探针或天体观测。请修改参数、改用其他必要操作，或保存/提交已有候选；'
            '不要把新的law_id或validation_id当作新证据。首次失败最多允许一次原样重试；'
            '同错误失败两次或确定性调用执行两次后，再原样调用会被阻止，并给一次改变操作的机会；'
            '下一轮仍原样重复才结束本轮探索，保留已有有效草稿。')
        self._event('loop_recovery_feedback', **notice)
        return json.dumps(notice, ensure_ascii=False, allow_nan=False)

    def _persist(self):
        _save(self.run_dir / 'messages.json', self.messages)

    def _event(self, kind, **data):
        append_event(self.run_dir / 'events.jsonl', {'event': kind, **data})

    def _failure(self, code):
        return {'ok': False, 'data': None, 'error': {'code': code, 'message': code},
                'budget': self.last_budget}

    def _finish(self, status, reason):
        if self.e4 and self.submission is None and status != 'submitted':
            draft = self.runtime.finalize_draft(reason)
            if draft is not None:
                self.submission = draft
                self.session_ended = True
                status = 'submitted'
                reason = ('deadline_saved_draft' if 'wall' in reason or 'deadline' in reason
                          else 'saved_draft_after_' + reason)
        budget_reader = getattr(self.runtime, 'budget', None)
        if callable(budget_reader):
            try:
                current_budget = budget_reader()
                if isinstance(current_budget, dict):
                    self.last_budget = current_budget
                else:
                    self._event('budget_refresh_failed', reason='invalid_budget_response')
            except Exception:
                # Preserve the last known budget without leaking backend details.
                self._event('budget_refresh_failed', reason='budget_unavailable')
        result = {'status': status, 'reason': reason, 'submission': self.submission,
                  'model_usage': copy.deepcopy(self.client.usage), 'budget': self.last_budget}
        self._persist()
        _save(self.run_dir / 'result.json', result)
        self._event('session_finished', **result)
        return result

    @staticmethod
    def _valid_calls(calls):
        if not isinstance(calls, list) or len(calls) > 32:
            return False
        ids = set()
        for call in calls:
            if (not isinstance(call, dict) or call.get('type') != 'function'
                    or not isinstance(call.get('id'), str) or not call['id']
                    or call['id'] in ids or not isinstance(call.get('function'), dict)
                    or not isinstance(call['function'].get('name'), str)
                    or not isinstance(call['function'].get('arguments'), str)):
                return False
            ids.add(call['id'])
        return True

    def run(self):
        mission = self.runtime.mission()
        self.last_budget = mission.get('budget') or {}
        prompt = (Path(__file__).parent / 'prompts' / 'main.txt').read_text(encoding='utf-8')
        if self.ruleset == 'e4':
            prompt += ('\n\nE4时间约束：首次mission开始后总探索预算300秒，包含模型与科学工具。'
                       '调用save_draft明确保存你选择的law_id和你根据观测判断的三个claims；'
                       '保存成功后可继续改进，最后及时有效配对会在截止或提前结束时保留。'
                       '未明确给出claims的候选不会自动成为草稿。剩余时间少时优先save_draft或submit，'
                       '不要等待长篇说明。系统在最后30秒优先封存已保存配对；没有草稿时仍由你决定提交，'
                       '截止时没有有效配对会如实记为未完成。')
        elif self.ruleset == 'e5' and self.guidance_profile != 'e3':
            filename = 'e5_concise.txt' if self.guidance_profile == 'concise' else 'e5.txt'
            prompt += '\n\n' + (Path(__file__).parent / 'prompts' / filename).read_text(encoding='utf-8')
        if getattr(self.runtime, 'symbolic_enabled', False):
            prompt += '\n\n' + (Path(__file__).parent / 'prompts' / 'symbolic.txt').read_text(encoding='utf-8')
        if getattr(self.runtime, 'code_enabled', False):
            prompt = prompt.replace('不可访问任意文件、Shell、网络、源码或任意 Python。',
                                    '代码只可通过run_code在隔离环境执行，不可访问宿主文件、网络或仿真源码。')
            prompt += '\n\n' + (Path(__file__).parent / 'prompts' / 'code.txt').read_text(encoding='utf-8')
        self.messages = [{'role': 'system', 'content': prompt},
                         {'role': 'user', 'content': '当前任务与合法初始观测：\n' +
                          json.dumps(mission, ensure_ascii=False, allow_nan=False)}]
        self._persist()
        if not mission.get('ok'):
            return self._finish('error', 'mission_unavailable')
        if self.last_budget.get('session_ended') is True:
            return self._finish('incomplete', 'session_already_ended')
        no_action = 0
        # A turn cap would impose another model-call cap. Continue until submit,
        # a resource/error termination, or repeated replies without tool actions.
        turn = 0
        while True:
            if self.e4:
                remaining = self.runtime.budget()['wall_seconds_remaining']
                if remaining <= self.finish_reserve_seconds:
                    if self.runtime.last_valid_draft is not None:
                        return self._finish('incomplete', 'deadline_reserve')
                    if remaining <= 0:
                        return self._finish('incomplete', 'wall_time_exhausted_without_saved_draft')
            turn += 1
            try:
                message = self.client.complete(self.messages, tools=self.runtime.schemas, role='main')
            except ModelError as exc:
                return self._finish('incomplete', exc.code)
            self.messages.append(copy.deepcopy(message))
            self._persist()
            content = message.get('content')
            if content:
                print(f'研究进展：{content}', flush=True)
                self._event('research_progress', turn=turn, content=content)
            finish_reason = self.client.last_finish_reason
            # A length-limited reply may end halfway through JSON: never execute it.
            if finish_reason not in ('stop', 'tool_calls'):
                if self.loop_recovery and finish_reason == 'length' and not self._length_recovered:
                    self._length_recovered = True
                    self._event('model_length_recovery', turn=turn, discarded_message=copy.deepcopy(message))
                    # Drop incomplete calls from the model conversation, keeping
                    # their original response in the audit event above.
                    self.messages[-1] = {'role': 'assistant', 'content': content or '上次回复达到输出上限，工具未执行。'}
                    self.messages.append({'role': 'user', 'content':
                        '上一轮达到单次4096 token上限，所有工具调用均未执行。仅允许这一次恢复。'
                        '请缩短说明，使用完整、简短的工具参数继续；不要续写半截JSON。'
                        '现有观测和候选仍有效，可以直接执行必要操作或保存/提交已有候选。'})
                    self._persist()
                    continue
                if self.loop_recovery and finish_reason == 'length' and self._length_recovered:
                    return self._finish('incomplete', 'model_finish_length_recovery_exhausted')
                return self._finish('incomplete', f'model_finish_{finish_reason}')
            calls = message.get('tool_calls') or []
            if not self._valid_calls(calls):
                return self._finish('error', 'malformed_tool_call_protocol')
            if not calls:
                no_action += 1
                if no_action >= self.max_no_action:
                    return self._finish('incomplete', 'consecutive_no_action_limit')
                self.messages.append({'role': 'user', 'content':
                    '尚未收到成功提交。请根据现有证据决定下一步并执行必要工具；'
                    '自然语言结束不会提交。资源不足或证据不足时请如实说明，不要编造结果。'})
                self._persist()
                continue
            no_action = 0
            loop_stop_reason = None
            recovery_feedback = []
            for call in calls:
                name = call['function']['name']
                print(f'工具调用：{name}', flush=True)
                key = None
                executed_or_invalid = False
                if loop_stop_reason is not None:
                    result = self._failure('loop_recovery_terminated')
                elif self.session_ended:
                    result = self._failure('session_ended')
                elif self.client.remaining_seconds() <= 0:
                    self.session_ended = True
                    result = self._failure('wall_time_exhausted')
                else:
                    try:
                        args = json.loads(call['function']['arguments'])
                        if not isinstance(args, dict):
                            raise ValueError()
                        # NaN/Infinity are accepted by Python's decoder but not our protocol.
                        json.dumps(args, allow_nan=False)
                    except (TypeError, ValueError):
                        args = None
                        result = self._failure('invalid_tool_arguments_json')
                        executed_or_invalid = True
                    if self.loop_recovery:
                        key = self._repeat_key(name, args, call['function']['arguments'])
                        block_reason = self._repeat_block_reason(key)
                    else:
                        block_reason = None
                    if block_reason is not None:
                        state = self._repeat_states[key]
                        new_blocked_turn = state.get('blocked_turn') != turn
                        if new_blocked_turn:
                            state['blocked_turn'] = turn
                            state['blocked_turns'] = state.get('blocked_turns', 0) + 1
                        if state['blocked_turns'] >= 2:
                            loop_stop_reason = block_reason
                        try:
                            current_budget = self.runtime.budget()
                            if isinstance(current_budget, dict):
                                self.last_budget = current_budget
                        except Exception:
                            self._event('budget_refresh_failed', reason='loop_recovery_budget_unavailable')
                        result = self._failure(block_reason)
                        executed_or_invalid = False
                        notice = {'tool': name, 'identical_attempts_without_new_observations': state['attempts'],
                                  'blocked_model_turns': state['blocked_turns'], 'budget': copy.deepcopy(self.last_budget),
                                  'instruction': '本次重复调用未执行。请现在修改参数、改用其他必要操作，或保存/提交已有候选。'
                                  '这是一次恢复机会；下一轮仍原样重复会结束探索并保留已有有效草稿。'}
                        self._event('loop_recovery_blocked', name=name, reason=block_reason,
                                    attempts=state['attempts'], execution_skipped=True,
                                    continuation_allowed=loop_stop_reason is None, notice=notice)
                        if new_blocked_turn and loop_stop_reason is None:
                            recovery_feedback.append(json.dumps(notice, ensure_ascii=False, allow_nan=False))
                    elif args is not None:
                        executed_or_invalid = True
                        self._event('tool_started', tool_call_id=call['id'], name=name, arguments=args)
                        try:
                            result = self.runtime.execute(name, args)
                        except Exception:
                            # Tool exceptions are a failure, never a success or raw backend dump.
                            result = self._failure('tool_execution_error')
                if isinstance(result.get('budget'), dict):
                    self.last_budget = result['budget']
                if self.loop_recovery and executed_or_invalid:
                    notice = self._record_repeat(key, result)
                    if notice is not None:
                        recovery_feedback.append(notice)
                self.messages.append({'role': 'tool', 'tool_call_id': call['id'],
                                      'content': json.dumps(result, ensure_ascii=False, allow_nan=False)})
                self._event('tool_finished', tool_call_id=call['id'], name=name, result=result)
                self._persist()
                data = result.get('data') or {}
                if (name == 'submit' and result.get('ok') and data.get('status') == 'accepted'
                        and data.get('session_ended') is True):
                    self.submission = data
                    self.session_ended = True
                elif data.get('session_ended') is True or self.last_budget.get('session_ended') is True:
                    self.session_ended = True
                print(f'工具结果：{name} {"ok" if result.get("ok") else "failed"}', flush=True)
            # All calls in an assistant reply have matching tool messages, even when
            # an earlier submit ended the session and later calls were skipped.
            if self.submission is not None:
                return self._finish('submitted', 'submission_accepted_locally')
            if self.session_ended:
                return self._finish('incomplete', 'session_ended_without_accepted_submission')
            if loop_stop_reason is not None:
                return self._finish('incomplete', loop_stop_reason)
            if recovery_feedback:
                self.messages.append({'role': 'user', 'content': '工具调用恢复反馈：\n' + '\n'.join(recovery_feedback)})
                self._persist()
