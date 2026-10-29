import importlib.util
from pathlib import Path
import sys
import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('ide_gateway_capacity', SCRIPTS / 'ide_gateway_capacity.py')
capacity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capacity)


def test_empty_and_degraded_responses_never_count_as_valid_completions():
    rows = [{'outcome': status, 'seconds': .2} for status in ['empty', 'degraded', 'transport_error']]
    result = capacity.summary(rows)
    assert result['validRate'] == 0
    assert result['validP95'] is None
    assert sum(result['outcomes'].values()) == 3


def test_failed_requests_remain_in_overall_latency_and_success_denominator():
    result = capacity.summary([{'outcome': 'valid', 'seconds': .4},
                               {'outcome': 'transport_error', 'seconds': 8}])
    assert result['validRate'] == .5
    assert result['p95'] == 8
    assert result['validP95'] == .4


def test_nearest_rank_percentiles_and_no_samples_are_explicit():
    assert capacity.percentile([], .95) is None
    assert capacity.percentile(list(range(1, 21)), .5) == 10
    assert capacity.percentile(list(range(1, 21)), .95) == 19
    assert capacity.percentile(list(range(1, 21)), .99) == 20
    assert capacity.summary([])['count'] == 0


@pytest.mark.parametrize('result,expected', [
    (None, 'null_result'),
    ([], 'invalid_result'),
    ({}, 'missing_status'),
    ({'status': 'degraded'}, 'degraded'),
    ({'status': 'ready', 'revision': 2, 'items': [{'label': 'printf'}]}, 'stale'),
    ({'status': 'ready', 'revision': 1, 'items': []}, 'empty'),
    ({'status': 'ready', 'revision': 1, 'items': [{'label': 'sprintf'}]}, 'empty'),
    ({'status': 'ready', 'revision': 1, 'items': [{'label': 'printf', 'filterText': None}]}, 'valid'),
])
def test_completion_classification_keeps_null_data_out_of_transport_failures(result, expected):
    assert capacity.completion_outcome(result, 1, 'c') == expected


@pytest.mark.parametrize('operation', ['sync', 'state'])
def test_null_sync_and_recovery_keep_failure_and_operation_explicit(operation):
    with pytest.raises(capacity.ReplyDataError) as error:
        capacity.response_revision(None, operation)
    assert error.value.outcome == operation + '_null_result'
    assert capacity.response_revision({'revision': 4}, operation) == 4
    for value in ({'revision': True}, {'revision': 0}, []):
        with pytest.raises(capacity.ReplyDataError):
            capacity.response_revision(value, operation)
