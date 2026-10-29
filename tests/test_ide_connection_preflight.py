import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'connection_preflight', Path(__file__).parents[1] / 'scripts/ide_connection_preflight.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def settings(database):
    return {'redis-url': 'redis://:private@gateway-redis:6379/' + database,
            'prefix': 'owned:'}


def test_same_endpoint_accepts_default_database_without_disclosing_credentials():
    worker = {'SDUOJ_IDE_REDIS_URL': 'redis://:private@gateway-redis:6379/0',
              'SDUOJ_IDE_PREFIX': 'owned:'}
    report = module.compare(settings(''), worker)
    assert report['matched'] and report['database'] == 0
    assert 'private' not in str(report) and 'redis://' not in str(report)


@pytest.mark.parametrize('url', ['redis://host/2', 'redis://gateway-redis:6380/2',
                                  'redis://gateway-redis:6379/0'])
def test_host_port_and_database_mismatch_each_fail_closed(url):
    with pytest.raises(ValueError):
        module.compare(settings('2'), {'SDUOJ_IDE_REDIS_URL': url,
                                      'SDUOJ_IDE_PREFIX': 'owned:'})


def test_prefix_mismatch_and_unsupported_database_fail_closed():
    with pytest.raises(ValueError):
        module.compare(settings('2'), {'SDUOJ_IDE_REDIS_URL': 'redis://gateway-redis/2',
                                      'SDUOJ_IDE_PREFIX': 'another:'})
    for uri in ('http://gateway-redis/2', 'redis://gateway-redis/-1',
                'redis://gateway-redis/2?db=0'):
        with pytest.raises(ValueError):
            module.endpoint(uri)
