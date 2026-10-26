"""Pure lifecycle evidence tests: no load, HTTP, Redis, Docker or services."""
import copy
import importlib.util
import json
from pathlib import Path
import stat
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from ide_capacity_lifecycle import Lifecycle
spec = importlib.util.spec_from_file_location('capacity_lifecycle_target', SCRIPTS / 'ide_gateway_capacity.py')
capacity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capacity)


def stage_fields():
    return dict(stageIndex=1, activeUsers=100, onlineUsers=500, startedAtUnix=1000.0,
                startMonotonic=100.0, plannedSteadyStartAtUnix=1020.0,
                plannedSteadyStartMonotonic=120.0, plannedStageEndMonotonic=195.0)


def test_disabled_writer_does_not_open_files_or_read_clocks(monkeypatch):
    import ide_capacity_lifecycle as lifecycle
    def forbidden(*_args, **_kwargs):
        raise AssertionError('Disabled lifecycle must have no I/O or clock side effects')
    monkeypatch.setattr(lifecycle.os, 'open', forbidden)
    monkeypatch.setattr(lifecycle.time, 'time', forbidden)
    monkeypatch.setattr(lifecycle.time, 'monotonic', forbidden)
    writer = Lifecycle()
    writer.emit('stage_started', **stage_fields())
    writer.close()


def test_events_have_explicit_phase_anchors_order_and_cleanup_terminal(tmp_path):
    path = tmp_path / 'lifecycle.jsonl'
    writer = Lifecycle(path)
    fields = stage_fields()
    before = copy.deepcopy(fields)
    writer.emit('stage_started', **fields)
    writer.emit('stage_completed', stageIndex=1, activeUsers=100, onlineUsers=500,
                steadySamples=3000, diagnosticPassed=True)
    writer.emit('cleanup_completed', attemptedSessions=500, closedSessions=500,
                stagesStarted=1, stagesCompleted=1, allStagesComplete=True)
    writer.close()
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert fields == before
    assert [row['event'] for row in rows] == ['stage_started', 'stage_completed', 'cleanup_completed']
    assert [row['sequence'] for row in rows] == [1, 2, 3]
    assert rows[0]['plannedSteadyStartMonotonic'] + 5 == 125.0
    assert rows[0]['plannedStageEndMonotonic'] == 195.0
    assert all(row['clockDomain'] == 'load-client-host-monotonic' for row in rows)
    assert all('emittedAtUnix' in row and 'emittedMonotonic' in row for row in rows)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_file_and_symlink_targets_are_never_overwritten(tmp_path):
    path = tmp_path / 'existing.jsonl'
    path.write_text('original bytes\n')
    with pytest.raises(FileExistsError):
        Lifecycle(path)
    link = tmp_path / 'link.jsonl'
    link.symlink_to(path)
    with pytest.raises(FileExistsError):
        Lifecycle(link)
    assert path.read_text() == 'original bytes\n'


@pytest.mark.parametrize('secret_field', ['username', 'password', 'cookie', 'source', 'code', 'sessionId', 'actor'])
def test_unapproved_identity_source_and_session_fields_are_rejected_without_leaking(tmp_path, secret_field):
    path = tmp_path / 'events.jsonl'
    writer = Lifecycle(path)
    fields = {**stage_fields(), secret_field: 'private-sentinel-never-write'}
    with pytest.raises(ValueError, match='Unsupported'):
        writer.emit('stage_started', **fields)
    writer.close()
    assert path.read_text() == ''


@pytest.mark.parametrize('field,value', [('activeUsers', 'private-sentinel'),
    ('stageIndex', True), ('startMonotonic', float('nan')), ('startMonotonic', float('inf'))])
def test_secret_strings_and_invalid_numbers_cannot_hide_under_allowed_keys(tmp_path, field, value):
    path = tmp_path / 'events.jsonl'
    writer = Lifecycle(path)
    fields = stage_fields()
    fields[field] = value
    with pytest.raises(ValueError, match='Invalid'):
        writer.emit('stage_started', **fields)
    writer.close()
    assert 'private-sentinel' not in path.read_text()


def test_lifecycle_preserves_capacity_summary_and_rows(tmp_path):
    rows = [{'outcome': 'valid', 'seconds': .5}, {'outcome': 'null_result', 'seconds': 2.0}]
    original_rows = copy.deepcopy(rows)
    before = capacity.summary(rows)
    writer = Lifecycle(tmp_path / 'events.jsonl')
    writer.emit('stage_completed', stageIndex=1, activeUsers=100, onlineUsers=500,
                steadySamples=len(rows), diagnosticPassed=False)
    writer.close()
    assert capacity.summary(rows) == before
    assert rows == original_rows
    assert before['validRate'] == .5 and before['p95'] == 2.0 and before['validP95'] == .5


def test_interrupted_stage_reports_cleanup_without_claiming_stage_complete(tmp_path):
    path = tmp_path / 'events.jsonl'
    writer = Lifecycle(path)
    writer.emit('stage_started', **stage_fields())
    writer.emit('cleanup_completed', attemptedSessions=500, closedSessions=500,
                stagesStarted=1, stagesCompleted=0, allStagesComplete=False)
    writer.close()
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(rows) == 2 and rows[-1]['allStagesComplete'] is False
    assert rows[-1]['closedSessions'] == rows[-1]['attemptedSessions'] == 500
