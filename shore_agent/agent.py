"""Transparent main research loop. Files are restricted to acquired current-session data."""
from __future__ import annotations

import copy
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
        self.guidance_profile = config.get('guidance_profile', 'e5')
        if self.guidance_profile not in ('e3', 'e5'):
            raise ValueError('guidance_profile must be e3 or e5')
        self.messages = []
        self.last_budget = {}
        self.submission = None
        self.session_ended = False
        self.ruleset = getattr(tool_runtime, 'ruleset', 'e3')
        self.e4 = self.ruleset in ('e4', 'e5')
        failure_feedback = config.get('repeated_tool_failure_feedback', False)
        if type(failure_feedback) is not bool:
            raise ValueError('repeated_tool_failure_feedback must be boolean')
        self.repeated_tool_failure_feedback = self.ruleset == 'e5' and failure_feedback
        self._failed_tool_counts = {}
        budget_aware_tools = config.get('budget_aware_tools', False)
        if type(budget_aware_tools) is not bool:
            raise ValueError('budget_aware_tools must be boolean')
        self.budget_aware_tools = self.ruleset == 'e5' and budget_aware_tools
        strict_tool_recovery = config.get('strict_tool_recovery', False)
        if type(strict_tool_recovery) is not bool:
            raise ValueError('strict_tool_recovery must be boolean')
        self.strict_tool_recovery = self.ruleset == 'e5' and strict_tool_recovery
        if self.strict_tool_recovery and getattr(client, 'strict_tools', False) is not True:
            raise ValueError('strict_tool_recovery requires client.strict_tools=true')
        self.finish_reserve_seconds = 30.0 if self.e4 else 0.0
        self.max_no_action = config.get('max_no_action', 3)
        if isinstance(self.max_no_action, bool) or not isinstance(self.max_no_action, int) or self.max_no_action < 1:
            raise ValueError('max_no_action must be a positive integer')

    def _persist(self):
        _save(self.run_dir / 'messages.json', self.messages)

    def _event(self, kind, **data):
        append_event(self.run_dir / 'events.jsonl', {'event': kind, **data})

    def _failure(self, code):
        return {'ok': False, 'data': None, 'error': {'code': code, 'message': code},
                'budget': self.last_budget}

    def _model_tools(self, budget):
        """Advertise public resource limits without changing runtime execution."""
        if not self.budget_aware_tools:
            return self.runtime.schemas
        energy = budget.get('energy_remaining')
        observations = budget.get('observations_remaining')
        schemas = []
        for schema in copy.deepcopy(self.runtime.schemas):
            function = schema['function']
            if function['name'] == 'insert_probe':
                if type(energy) in (int, float) and energy == 0:
                    continue
                if type(energy) is int and energy > 0:
                    probes = function['parameters']['properties']['probes']
                    maximum = probes.get('maxItems')
                    if type(maximum) is int:
                        probes['maxItems'] = min(maximum, energy)
            elif (function['name'] == 'observe_body'
                  and type(observations) in (int, float) and observations == 0):
                continue
            schemas.append(schema)
        return schemas

    def _track_tool_failure(self, name, args, result):
        """Observe actual tool outcomes without changing them or invoking tools."""
        if not (self.repeated_tool_failure_feedback or self.strict_tool_recovery) or args is None:
            return None, None
        key = (name, json.dumps(args, sort_keys=True, ensure_ascii=False, allow_nan=False))
        if result.get('ok') is True:
            self._failed_tool_counts.pop(key, None)
            return key, None
        if result.get('ok') is not False:
            return key, None
        count = self._failed_tool_counts.get(key, 0) + 1
        self._failed_tool_counts[key] = count
        if count < 2:
            return key, None
        constraints = []
        schema = next((s['function']['parameters'] for s in self.runtime.schemas
                       if s['function']['name'] == name), {})
        for field, value in args.items():
            maximum = schema.get('properties', {}).get(field, {}).get('maxItems')
            if isinstance(value, list) and type(maximum) is int and len(value) > maximum:
                constraints.append(f'参数 {field} 当前有 {len(value)} 项，公开 schema 上限为 {maximum} 项。'
                                   '请自行减少数量；如分批调用，先核对剩余观察次数和能量。')
        error = copy.deepcopy(result.get('error'))
        if 'energy_budget' in json.dumps(error, ensure_ascii=False):
            constraints.append('这批请求超过剩余能量；请自行减少本批消耗，或改用已经取得的观测继续分析。')
        return key, {'tool': name, 'arguments': copy.deepcopy(args),
                     'repeat_count': count, 'error': error, 'constraints': constraints}

    def _append_failure_feedback(self, pending, turn):
        """Append only after every tool call in the assistant turn has a reply."""
        notices = list(pending.values())
        lines = ['工具失败恢复提醒（调度层提示，不是新观测或工具执行结果）：']
        for notice in notices:
            error_text = json.dumps(notice['error'], ensure_ascii=False, allow_nan=False)
            if len(error_text) > 800:
                error_text = error_text[:800] + '…（完整错误见上方原始工具结果）'
            lines.append(f"{notice['tool']} 的同名同参数调用已失败 {notice['repeat_count']} 次。"
                         f'本次错误：{error_text}')
            lines.extend(notice['constraints'])
            if notice['repeat_count'] >= 3:
                lines.append('此前恢复提醒后仍在重复失败。请停止这一无进展调用，重新选择合法下一步。')
        lines.append('当前剩余预算：' + json.dumps(self.last_budget, ensure_ascii=False, allow_nan=False))
        lines.append('不得原样重试。请依据错误和预算修改参数或改用已有数据；'
                     '失败不等于物理假设被否定。所有选择仍由你决定，需重新发出完整合法调用；'
                     '不要声称失败操作成功，也不要虚构观测或提交。')
        content = '\n'.join(lines)
        self.messages.append({'role': 'user', 'content': content})
        self._event('repeated_tool_failure_feedback', turn=turn, failures=notices,
                    budget=copy.deepcopy(self.last_budget), content=content)
        self._persist()

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
        elif self.ruleset == 'e5' and self.guidance_profile == 'e5':
            prompt += '\n\n' + (Path(__file__).parent / 'prompts' / 'e5.txt').read_text(encoding='utf-8')
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
        length_recoveries = 0
        pending_strict_recovery = []
        # A turn cap would impose another model-call cap. Continue until submit,
        # a resource/error termination, or repeated replies without tool actions.
        turn = 0
        while True:
            current_budget = None
            if self.e4:
                current_budget = self.runtime.budget()
                remaining = current_budget['wall_seconds_remaining']
                if remaining <= self.finish_reserve_seconds:
                    if self.runtime.last_valid_draft is not None:
                        return self._finish('incomplete', 'deadline_reserve')
                    if remaining <= 0:
                        return self._finish('incomplete', 'wall_time_exhausted_without_saved_draft')
            turn += 1
            model_tools = self._model_tools(current_budget)
            advertised_names = {tool['function']['name'] for tool in model_tools}
            try:
                if pending_strict_recovery:
                    # Consume the override for this request only. No tool or
                    # parameters are selected here; the model retains that choice.
                    triggers, pending_strict_recovery = pending_strict_recovery, []
                    self._event('strict_tool_recovery_requested', turn=turn,
                                tool_choice='required', triggers=triggers,
                                advertised_tool_names=sorted(advertised_names),
                                budget=copy.deepcopy(current_budget))
                    message = self.client.complete(self.messages, tools=model_tools, role='main',
                                                   tool_choice_override='required')
                else:
                    # Preserve the original signature for default clients/fakes.
                    message = self.client.complete(self.messages, tools=model_tools, role='main')
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
                if self.ruleset == 'e5' and finish_reason == 'length' and length_recoveries == 0:
                    length_recoveries += 1
                    self._event('model_length_recovered', turn=turn,
                                original_message=copy.deepcopy(message),
                                model_usage=copy.deepcopy(self.client.usage))
                    # Keep valid earlier exchanges, but do not resend a partial
                    # tool call or feed a repetitive truncated reply back in.
                    self.messages[-1] = {'role': 'assistant', 'content':
                        '上一条回复达到单次输出上限，已中止；其中没有工具被执行。'}
                    self.messages.append({'role': 'user', 'content':
                        '这是本次探索唯一一次输出截断恢复，原有时间、能量和每次输出上限不变。'
                        '停止重复文字与手算，利用已有观测和工具继续；重新给出完整、简洁的工具调用，'
                        '不要续写上条回复或残缺JSON。'})
                    self._persist()
                    continue  # The unchanged deadline checks run before any new request.
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
            pending_failure_feedback = {}
            unadvertised_calls = []
            for call in calls:
                name = call['function']['name']
                if self.strict_tool_recovery and name not in advertised_names:
                    unadvertised_calls.append({'reason': 'unadvertised_tool', 'tool': name,
                                               'tool_call_id': call['id']})
                args = None
                print(f'工具调用：{name}', flush=True)
                if self.session_ended:
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
                    if args is not None:
                        self._event('tool_started', tool_call_id=call['id'], name=name, arguments=args)
                        try:
                            result = self.runtime.execute(name, args)
                        except Exception:
                            # Tool exceptions are a failure, never a success or raw backend dump.
                            result = self._failure('tool_execution_error')
                if isinstance(result.get('budget'), dict):
                    self.last_budget = result['budget']
                self.messages.append({'role': 'tool', 'tool_call_id': call['id'],
                                      'content': json.dumps(result, ensure_ascii=False, allow_nan=False)})
                self._event('tool_finished', tool_call_id=call['id'], name=name, result=result)
                self._persist()
                failure_key, feedback = self._track_tool_failure(name, args, result)
                if feedback is not None:
                    pending_failure_feedback[failure_key] = feedback
                elif failure_key is not None and result.get('ok') is True:
                    pending_failure_feedback.pop(failure_key, None)
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
            if pending_failure_feedback and self.repeated_tool_failure_feedback:
                self._append_failure_feedback(pending_failure_feedback, turn)
            if self.strict_tool_recovery:
                pending_strict_recovery = unadvertised_calls + [
                    {'reason': 'repeated_tool_failure', **copy.deepcopy(notice)}
                    for notice in pending_failure_feedback.values()]
                if pending_strict_recovery:
                    self._event('strict_tool_recovery_scheduled', turn=turn, next_turn=turn + 1,
                                tool_choice='required', triggers=pending_strict_recovery,
                                budget=copy.deepcopy(self.last_budget))
