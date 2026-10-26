"""Optional, exclusive JSONL lifecycle evidence without actors or source data."""
import json
import math
import os
from pathlib import Path
import time


SCHEMAS = {
    'stage_started': {
        'stageIndex': int, 'activeUsers': int, 'onlineUsers': int,
        'startedAtUnix': float, 'startMonotonic': float,
        'plannedSteadyStartAtUnix': float, 'plannedSteadyStartMonotonic': float,
        'plannedStageEndMonotonic': float,
    },
    'stage_completed': {
        'stageIndex': int, 'activeUsers': int, 'onlineUsers': int,
        'steadySamples': int, 'diagnosticPassed': bool,
    },
    'cleanup_completed': {
        'attemptedSessions': int, 'closedSessions': int,
        'stagesStarted': int, 'stagesCompleted': int, 'allStagesComplete': bool,
    },
}


class Lifecycle:
    """A single producer; no file, clock reads or I/O when the option is absent."""
    def __init__(self, path=None):
        self.stream, self.sequence = None, 0
        if path is not None:
            fd = os.open(Path(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                self.stream = os.fdopen(fd, 'w', encoding='utf-8')
            except BaseException:
                os.close(fd)
                raise

    def emit(self, event, **fields):
        if self.stream is None:
            return
        schema = SCHEMAS.get(event)
        if schema is None or fields.keys() != schema.keys():
            raise ValueError('Unsupported lifecycle event or fields')
        for name, expected in schema.items():
            value = fields[name]
            if expected is float:
                valid = type(value) in (int, float) and math.isfinite(value) and value >= 0
            else:
                valid = type(value) is expected and (expected is bool or value >= 0)
            if not valid:
                raise ValueError('Invalid lifecycle field type')
        self.sequence += 1
        record = {'schemaVersion': 1, 'sequence': self.sequence, 'event': event,
                  'clockDomain': 'load-client-host-monotonic',
                  'emittedAtUnix': time.time(), 'emittedMonotonic': time.monotonic(), **fields}
        self.stream.write(json.dumps(record, sort_keys=True, allow_nan=False) + '\n')
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def close(self):
        if self.stream is not None:
            self.stream.close()
            self.stream = None
