"""Acceptance observation waits for the advertised product deadline plus cleanup."""
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('acceptance_timeout_contract',
    Path(__file__).parents[1] / 'scripts/ide_redis_dev_acceptance.py')
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


@pytest.mark.parametrize('limit,wait', [(20,30),(40,50),(60,70),(1800,1810)])
def test_observation_wait_uses_advertised_run_limit(limit, wait):
    session = {'runLimitSeconds': limit}
    assert acceptance.run_timeout_observation_seconds(session) == wait
    assert session == {'runLimitSeconds': limit}


@pytest.mark.parametrize('value', [None, True, False, 0, -1, float('inf'), float('nan'), 1801, '60'])
def test_invalid_or_excessive_observation_budget_fails_closed(value):
    with pytest.raises(ValueError):
        acceptance.run_timeout_observation_seconds({'runLimitSeconds': value})
