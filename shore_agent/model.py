"""Small HTTP adapter with bounded requests for the single research Agent."""
from __future__ import annotations

import copy
import json
import math
import os
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .store import append_event


class ModelError(RuntimeError):
    """A deliberately redacted error; never includes HTTP headers or bodies."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _positive(config, key, default, *, integer=False):
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f'{key} must be positive and finite')
    if integer and int(value) != value:
        raise ValueError(f'{key} must be an integer')
    return int(value) if integer else float(value)


class DeepSeekClient:
    """Every HTTP attempt (including retries) consumes the research Agent budget.

    Current official protocol requires reasoning_content to survive *all*
    assistant turns in a tool-enabled conversation, even turns without calls.
    We therefore forward full message dictionaries without rebuilding them.
    """

    def __init__(self, config: dict, run_dir: Path, remaining_seconds, *, transport=None):
        self.config = dict(config)
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.remaining_seconds = remaining_seconds
        self.model = config.get('model', 'deepseek-flash')
        self.base_url = config.get('base_url', 'https://api.deepseek.com').rstrip('/')
        parsed = urlsplit(self.base_url)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment):
            raise ValueError('base_url must be an HTTP(S) URL without credentials/query/fragment')
        self.timeout = _positive(config, 'timeout_seconds', 90)
        # Call counts remain auditable but no longer terminate a session. Ignore
        # obsolete caps in older configurations, including the per-role cap.
        self.max_calls = None
        self.max_tokens_per_call = _positive(config, 'max_tokens_per_call', 4096, integer=True)
        self.max_total_tokens = _positive(config, 'max_total_tokens', 150000, integer=True)
        self.role_limits = {'main': None}
        self.max_retries = config.get('max_retries', 1)
        if isinstance(self.max_retries, bool) or not isinstance(self.max_retries, int) or not 0 <= self.max_retries <= 5:
            raise ValueError('max_retries must be an integer between 0 and 5')
        self.reasoning_effort = config.get('reasoning_effort', 'high')
        if self.reasoning_effort not in ('low', 'medium', 'high', 'max'):
            raise ValueError('Invalid reasoning_effort')
        self.thinking = config.get('thinking', True)
        if not isinstance(self.thinking, bool):
            raise ValueError('thinking must be boolean')
        self.usage = {'calls': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0,
                      'conservative_reserved_tokens': 0, 'elapsed_seconds': 0.0,
                      'roles': {role: {'calls': 0, 'prompt_tokens': 0, 'completion_tokens': 0,
                                       'total_tokens': 0} for role in self.role_limits}}
        self.last_finish_reason = None
        self._prompt_reference = None
        self._http = httpx.Client(transport=transport, follow_redirects=False)
        append_event(self.run_dir / 'model_events.jsonl', {
            'event': 'configuration', 'model': self.model, 'base_url': self.base_url,
            'thinking': self.thinking,
            'reasoning_effort': self.reasoning_effort,
            'timeout_seconds': self.timeout,
            'max_calls': self.max_calls, 'max_tokens_per_call': self.max_tokens_per_call,
            'max_total_tokens': self.max_total_tokens, 'role_limits': self.role_limits,
            'max_retries': self.max_retries,
            'model_alias_note': 'Model names are provider-managed aliases; weights are not pinned.'})

    def close(self):
        self._http.close()

    def _quota(self, role):
        if role not in self.role_limits:
            raise ModelError('invalid_model_role')
        if self.remaining_seconds() <= 0:
            raise ModelError('wall_time_exhausted')
        if self.usage['total_tokens'] + self.usage['conservative_reserved_tokens'] >= self.max_total_tokens:
            self.usage['request_budget'] = {'status': 'blocked', 'reason': 'total_budget_exhausted',
                'available_tokens': max(0, self.max_total_tokens - self.usage['total_tokens']
                                         - self.usage['conservative_reserved_tokens'])}
            raise ModelError('model_token_budget_exhausted')

    @staticmethod
    def _prompt_context(body):
        return {k: v for k, v in body.items() if k not in ('messages', 'max_tokens')}

    def _prompt_estimate(self, body):
        """Reuse measured tokens only for an identical, unedited message prefix.

        The suffix is still bounded by UTF-8 bytes, with extra framing allowance.
        Changing old messages, tools or model settings invalidates the anchor.
        Never remove history/reasoning or treat provider cache hits as free tokens.
        """
        upper = len(json.dumps(body, ensure_ascii=False).encode('utf-8')) + 512
        ref = self._prompt_reference
        messages = body['messages']
        if (ref is not None and self._prompt_context(body) == ref['context']
                and len(messages) >= len(ref['messages'])
                and messages[:len(ref['messages'])] == ref['messages']):
            suffix = messages[len(ref['messages']):]
            added = len(json.dumps(suffix, ensure_ascii=False).encode('utf-8')) if suffix else 0
            return {'method': 'reported_prefix_plus_utf8_suffix',
                    'estimated_prompt_tokens': ref['prompt_tokens'] + added + 512,
                    'reference_prompt_tokens': ref['prompt_tokens'],
                    'added_message_bytes': added, 'utf8_upper_bound': upper}
        return {'method': 'utf8_upper_bound', 'estimated_prompt_tokens': upper,
                'utf8_upper_bound': upper}

    def complete(self, messages, tools=None, role='main') -> dict:
        self._quota(role)
        key = os.environ.get('DEEPSEEK_API_KEY')
        if not key:
            raise ModelError('missing_deepseek_api_key')
        requested_max = self.max_tokens_per_call
        thinking = self.thinking
        body = {'model': self.model, 'messages': copy.deepcopy(messages), 'stream': False,
                'thinking': {'type': 'enabled' if thinking else 'disabled'}}
        if thinking:
            body['reasoning_effort'] = self.reasoning_effort
        if tools:
            body.update(tools=copy.deepcopy(tools), tool_choice='auto')
        estimate = self._prompt_estimate(body)
        prompt_allowance = estimate['estimated_prompt_tokens']
        for attempt in range(self.max_retries + 1):
            self._quota(role)
            available = self.max_total_tokens - self.usage['total_tokens'] - self.usage['conservative_reserved_tokens']
            output_limit = min(requested_max, available - prompt_allowance)
            self.usage['request_budget'] = dict(estimate, available_tokens=available,
                requested_output_tokens=requested_max, output_token_limit=max(0, output_limit),
                minimum_output_tokens=64, status='blocked' if output_limit < 64 else 'admitted')
            if output_limit < 64:
                append_event(self.run_dir / 'model_events.jsonl', {
                    'event': 'budget_blocked', 'role': role,
                    'budget_usage': copy.deepcopy(self.usage)})
                raise ModelError('model_token_budget_exhausted')
            body['max_tokens'] = int(output_limit)
            timeout = min(_positive(self.config, f'{role}_timeout_seconds', self.timeout), self.remaining_seconds())
            if timeout <= 0:
                raise ModelError('wall_time_exhausted')
            self.usage['calls'] += 1
            self.usage['roles'][role]['calls'] += 1
            reservation = prompt_allowance + output_limit
            self.usage['conservative_reserved_tokens'] += reservation
            started = time.monotonic()
            event = {'event': 'request', 'role': role, 'attempt': attempt + 1,
                     'call_number': self.usage['calls'], 'max_tokens': output_limit,
                     'timeout_seconds': timeout}
            retryable = False
            response_data = None
            try:
                response = self._http.post(self.base_url + '/chat/completions', json=body,
                                           headers={'Authorization': f'Bearer {key}'}, timeout=timeout)
                event['http_status'] = response.status_code
                if response.status_code != 200:
                    retryable = response.status_code in (408, 429) or response.status_code >= 500
                    raise ModelError(f'http_status_{response.status_code}')
                try:
                    response_data = response.json()
                except ValueError:
                    raise ModelError('invalid_api_json') from None
                reported = response_data.get('usage', {}) if isinstance(response_data, dict) else {}
                if (isinstance(reported, dict) and all(isinstance(reported.get(k), int)
                        and not isinstance(reported[k], bool) and reported[k] >= 0
                        for k in ('prompt_tokens', 'completion_tokens', 'total_tokens'))
                        and reported['total_tokens'] >= reported['prompt_tokens'] + reported['completion_tokens']):
                    self.usage['conservative_reserved_tokens'] -= reservation
                    for k in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
                        self.usage[k] += reported[k]
                        self.usage['roles'][role][k] += reported[k]
                    event['usage'] = reported
                    self.usage['request_budget']['reported_prompt_tokens'] = reported['prompt_tokens']
                    self._prompt_reference = {'context': self._prompt_context(body),
                                              'messages': body['messages'],
                                              'prompt_tokens': reported['prompt_tokens']}
                else:
                    event['usage_warning'] = 'missing_or_invalid_usage; full local allowance reserved'
                try:
                    choice = response_data['choices'][0]
                    message = choice['message']
                    finish = choice['finish_reason']
                    if not isinstance(message, dict) or message.get('role') != 'assistant':
                        raise ValueError()
                except (KeyError, IndexError, TypeError, ValueError):
                    raise ModelError('invalid_api_message') from None
                self.last_finish_reason = finish
                event['response_model'] = response_data.get('model')
                event['system_fingerprint'] = response_data.get('system_fingerprint')
                event['finish_reason'] = finish
                event['status'] = 'response'
                # Preserve the full request and response for local protocol auditing.
                append_event(self.run_dir / 'model_messages.jsonl', {
                    'role': role, 'call_number': self.usage['calls'],
                    'messages': messages, 'assistant': message, 'finish_reason': finish})
                if self.remaining_seconds() <= 0:
                    raise ModelError('wall_time_exhausted')
                return copy.deepcopy(message)
            except httpx.TimeoutException:
                retryable = True
                event['error'] = 'api_timeout'
            except httpx.TransportError:
                retryable = True
                event['error'] = 'api_transport_error'
            except ModelError as exc:
                event['error'] = exc.code
            finally:
                elapsed = time.monotonic() - started
                event['elapsed_seconds'] = elapsed
                self.usage['elapsed_seconds'] += elapsed
                event['budget_usage'] = copy.deepcopy(self.usage)
                append_event(self.run_dir / 'model_events.jsonl', event)
            if not retryable or attempt >= self.max_retries:
                raise ModelError(event.get('error', 'api_error')) from None
            # Tiny bounded backoff; every retry also checks the wall clock and quotas.
            pause = min(0.5 * (attempt + 1), max(0, self.remaining_seconds()))
            if pause:
                time.sleep(pause)
        raise ModelError('api_error')
