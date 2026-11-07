"""Validation chronology in the read-only detail projection, not UUID order."""
import json
import os

import pytest

from shore_agent import web_jobs
from shore_agent.web_jobs import RunManager, _write


@pytest.fixture
def archive(tmp_path):
    manager = RunManager(tmp_path)
    directory = manager.runs_dir / 'validation-order'
    (directory / 'records/validation').mkdir(parents=True)
    _write(directory / 'result.json', {
        'status': 'incomplete', 'mode': 'autonomous_discovery',
        'budget': {'energy_remaining': 7},
    })
    yield manager, directory
    manager.close()


def validation(directory, identifier, law='law_1', rmse=.1):
    record = {'validation_id': identifier, 'law_id': law, 'test_probe_ids': ['probe_test'],
              'errors': {'overall': {'position_rmse': rmse}}}
    _write(directory / 'records/validation' / (identifier + '.json'), record)
    return record


def completion(record, *, tool_log=False, ok=True):
    item = {'result': {'ok': ok, 'data': {
        'validation_id': record['validation_id'], 'law_id': record['law_id']}}}
    item.update({'tool': 'validate_law'} if tool_log else
                {'event': 'tool_finished', 'name': 'validate_law'})
    return item


def write_log(directory, filename, events):
    (directory / filename).write_text(''.join(json.dumps(item) + '\n' for item in events))


def detail(manager, directory):
    return manager.snapshot(directory.name)


def test_completion_order_overrides_uuid_and_keeps_same_law_latest(archive):
    manager, directory = archive
    earlier = validation(directory, 'validation_ffff', rmse=.02633)
    later = validation(directory, 'validation_1111', rmse=.10871)
    other_law = validation(directory, 'validation_0000', law='law_2', rmse=.001)
    write_log(directory, 'events.jsonl', [completion(earlier), completion(later), completion(other_law)])
    # An inconsistent secondary log must not override the authoritative events.
    write_log(directory, 'tools.jsonl', [completion(later, tool_log=True), completion(earlier, tool_log=True)])
    before = {p: p.read_bytes() for p in directory.rglob('*') if p.is_file()}

    snapshot = detail(manager, directory)
    records = snapshot['records']['validations']
    assert records == [earlier, later, other_law]
    # This is the same filter + last selection used by the frontend.
    selected = [r for r in records if r['law_id'] == 'law_1'][-1]
    assert selected['validation_id'] == later['validation_id']
    assert selected['errors']['overall']['position_rmse'] == .10871
    assert snapshot['validation_order']['source'] == 'events.jsonl'
    assert snapshot['validation_order']['chronology_complete'] is True
    assert {p: p.read_bytes() for p in before} == before


@pytest.mark.parametrize('status_events_present', [False, True])
def test_legacy_archive_uses_tools_when_completion_events_missing(archive, status_events_present):
    manager, directory = archive
    earlier = validation(directory, 'validation_ffff')
    later = validation(directory, 'validation_1111')
    if status_events_present:
        write_log(directory, 'events.jsonl', [{'event': 'session_started'}])
    write_log(directory, 'tools.jsonl', [completion(earlier, tool_log=True), completion(later, tool_log=True)])

    snapshot = detail(manager, directory)
    assert snapshot['records']['validations'] == [earlier, later]
    assert snapshot['validation_order']['source'] == 'tools.jsonl'
    assert snapshot['validation_order']['chronology_complete'] is True


def test_unlogged_archive_is_stable_without_inferred_times(archive):
    manager, directory = archive
    second = validation(directory, 'validation_ffff')
    first = validation(directory, 'validation_1111')
    # File modification time is deliberately opposite to stable filename order.
    os.utime(directory / 'records/validation/validation_1111.json', (300, 300))
    os.utime(directory / 'records/validation/validation_ffff.json', (100, 100))

    snapshot = detail(manager, directory)
    assert snapshot['records']['validations'] == [first, second]
    assert detail(manager, directory)['records']['validations'] == [first, second]
    assert snapshot['validation_order'] == {
        'source': 'stable_record_order', 'chronology_complete': False,
        'unmatched_validation_ids': ['validation_1111', 'validation_ffff'],
        'unmatched_placement': 'stable_record_order_before_logged_records',
    }
    assert all('timestamp' not in r for r in snapshot['records']['validations'])


def test_partial_logs_keep_unknown_records_stable_and_reject_wrong_identity(archive):
    manager, directory = archive
    known_earlier = validation(directory, 'validation_ffff')
    known_later = validation(directory, 'validation_aaaa')
    unknown_b = validation(directory, 'validation_bbbb')
    unknown_c = validation(directory, 'validation_cccc')
    wrong_law = completion(unknown_b)
    wrong_law['result']['data']['law_id'] = 'another_law'
    write_log(directory, 'events.jsonl', [
        completion(known_earlier), completion(known_later), wrong_law,
        completion(unknown_c, ok=False),
        {'event': 'tool_started', 'name': 'validate_law', 'result': completion(unknown_c)['result']},
    ])

    snapshot = detail(manager, directory)
    assert snapshot['records']['validations'] == [unknown_b, unknown_c, known_earlier, known_later]
    assert snapshot['validation_order']['chronology_complete'] is False
    assert snapshot['validation_order']['unmatched_validation_ids'] == ['validation_bbbb', 'validation_cccc']
