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
        self.messages = []
        self.last_budget = {}
        self.submission = None
        self.session_ended = False
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

    def _finish(self, status, reason):
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
            for call in calls:
                name = call['function']['name']
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
