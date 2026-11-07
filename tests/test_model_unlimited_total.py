"""Explicit unlimited cumulative usage still caps each response and enforces time."""
import json

import pytest

from shore_agent.model import ModelError
from test_model import make_client, response, assistant


def test_none_removes_only_cumulative_admission_gate(tmp_path, monkeypatch):
    client, requests = make_client(tmp_path, monkeypatch, [response(assistant())]*2,
        {'max_total_tokens': None, 'max_tokens_per_call': 4096})
    client.usage['total_tokens'] = 20_000_000
    client.usage['conservative_reserved_tokens'] = 10_000_000
    messages = [{'role': 'user', 'content': 'x'*100000}]
    client.complete(messages)
    client.complete(messages)
    assert [r['max_tokens'] for r in requests] == [4096, 4096]
    assert client.usage['total_tokens'] == 20_000_060
    assert client.usage['request_budget']['total_quota_enabled'] is False
    assert client.usage['request_budget']['available_tokens'] is None
    json.dumps(client.usage, allow_nan=False)


def test_missing_usage_remains_accounted_without_stopping_unlimited_run(tmp_path, monkeypatch):
    raw = response(assistant())
    raw['usage'] = {}
    client, requests = make_client(tmp_path, monkeypatch, [raw, raw],
        {'max_total_tokens': None, 'max_tokens_per_call': 4096})
    client.complete([{'role': 'user', 'content': 'mock'}])
    reserved = client.usage['conservative_reserved_tokens']
    client.complete([{'role': 'user', 'content': 'mock'}])
    assert client.usage['conservative_reserved_tokens'] > reserved > 0
    assert len(requests) == 2 and client.usage['completion_tokens'] == 0


def test_wall_clock_still_stops_unlimited_total(tmp_path, monkeypatch):
    client, requests = make_client(tmp_path, monkeypatch, [],
        {'max_total_tokens': None, 'max_tokens_per_call': 4096}, remaining=lambda: 0)
    with pytest.raises(ModelError, match='wall_time_exhausted'):
        client.complete([{'role': 'user', 'content': 'mock'}])
    assert requests == []
