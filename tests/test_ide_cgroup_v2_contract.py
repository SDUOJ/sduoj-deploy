import copy
import importlib.util
import os
from pathlib import Path
import pytest


def module(name):
    path = Path(__file__).resolve().parents[1] / 'scripts' / (name + '.py')
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


runtime = module('ide_cgroup_v2_runtime_check')
setup = module('ide_cgroup_v2_setup')


def test_provision_preserves_delegated_directory_access_under_private_umask(tmp_path, monkeypatch):
    parent = tmp_path / 'sduoj-ide-private-umask'
    monkeypatch.setattr(setup, 'validate', lambda root, name: parent)
    monkeypatch.setattr(setup.os, 'geteuid', lambda: 0)
    owners = []
    monkeypatch.setattr(setup.os, 'chown', lambda path, uid, gid: owners.append((path, uid, gid)))
    previous = os.umask(0o077)
    try:
        report = setup.provision(tmp_path, parent.name)
    finally:
        os.umask(previous)
    assert parent.stat().st_mode & 0o777 == 0o755
    assert (parent / 'debug').stat().st_mode & 0o777 == 0o755
    assert report['limits'] == setup.LIMITS
    assert report['debugLimits'] == setup.DEBUG_LIMITS
    assert all(uid == gid == 10001 for path, uid, gid in owners)
    assert parent not in [path for path, uid, gid in owners]


def fixture():
    expected = {'image': 'sha256:' + 'a' * 64, 'name': 'sduoj-ide-node1', 'owner': 'test-owner'}
    instance = {'Id': 'b' * 64, 'Image': expected['image'], 'State': {'Running': True},
                'Config': {'User': '10001:10001', 'Labels': {'owner': 'test-owner'},
                           'Env': ['SDUOJ_IDE_DEV_DEBUG_LAB=0']},
                'HostConfig': {'Privileged': False, 'ReadonlyRootfs': True,
                               'SecurityOpt': ['seccomp=unconfined', 'apparmor=unconfined'],
                               'CgroupnsMode': 'host', 'CgroupParent': '/sduoj-ide-node1',
                               'CapAdd': ['CAP_SETUID', 'CAP_SETGID'], 'CapDrop': ['ALL'],
                               'NanoCpus': 4000000000, 'Memory': 6442450944, 'PidsLimit': 1024},
                'Mounts': [{'Destination': '/sys/fs/cgroup', 'RW': True,
                            'Type': 'bind',
                            'Source': '/sys/fs/cgroup/sduoj-ide-node1'},
                           {'Destination': '/run/ide-config', 'RW': False, 'Type': 'bind', 'Source': '/accepted'}]}
    info = {'CgroupVersion': '2', 'CgroupDriver': 'cgroupfs', 'Architecture': 'aarch64'}
    return expected, instance, info


def test_accepts_exact_single_worker_contract():
    expected, instance, info = fixture()
    assert runtime.check_contract(info, instance, [instance], expected)['passed']


@pytest.mark.parametrize('field,value', [('Privileged', True), ('ReadonlyRootfs', False),
    ('PidMode', 'host'), ('NetworkMode', 'host'), ('CgroupnsMode', 'private'),
    ('CapAdd', ['SYS_ADMIN', 'SETUID', 'SETGID']), ('CapDrop', []),
    ('Memory', 4 * 1024**3), ('CgroupParent', '/other')])
def test_permission_and_resource_drift_fails_closed(field, value):
    expected, instance, info = fixture()
    instance['HostConfig'][field] = value
    with pytest.raises(ValueError):
        runtime.check_contract(info, instance, [instance], expected)


def test_aggregate_cannot_be_shared_between_live_workers():
    expected, instance, info = fixture()
    other = copy.deepcopy(instance)
    other['Id'] = 'c' * 64
    with pytest.raises(ValueError, match='exclusive'):
        runtime.check_contract(info, instance, [instance, other], expected)
    other['State']['Running'] = False
    assert runtime.check_contract(info, instance, [instance, other], expected)['passed']


@pytest.mark.parametrize('field,value', [('CgroupVersion', '1'), ('CgroupDriver', 'systemd'),
                                       ('Architecture', 'x86_64')])
def test_host_mismatch_fails_closed(field, value):
    expected, instance, info = fixture()
    info[field] = value
    with pytest.raises(ValueError):
        runtime.check_contract(info, instance, [instance], expected)


def test_dev_bypass_and_host_root_mount_are_rejected():
    expected, instance, info = fixture()
    instance['Config']['Env'] = ['SDUOJ_IDE_DEV_DEBUG_LAB=1']
    with pytest.raises(ValueError):
        runtime.check_contract(info, instance, [instance], expected)
    instance['Config']['Env'] = ['SDUOJ_IDE_DEV_DEBUG_LAB=0']
    instance['Mounts'][0]['Source'] = '/sys/fs/cgroup'
    with pytest.raises(ValueError):
        runtime.check_contract(info, instance, [instance], expected)


@pytest.mark.parametrize('name', ['', 'root', '../sduoj-ide-node', 'sduoj-ide-x/child'])
def test_provision_refuses_unscoped_names(tmp_path, name, monkeypatch):
    monkeypatch.setattr(setup, 'filesystem_type', lambda path: 0x63677270)
    (tmp_path / 'cgroup.controllers').write_text('cpu memory pids')
    (tmp_path / 'cgroup.subtree_control').write_text('cpu memory pids')
    with pytest.raises(ValueError):
        setup.validate(tmp_path, name)


def test_provision_never_reuses_an_existing_aggregate(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, 'filesystem_type', lambda path: 0x63677270)
    (tmp_path / 'cgroup.controllers').write_text('cpu memory pids')
    (tmp_path / 'cgroup.subtree_control').write_text('cpu memory pids')
    (tmp_path / 'sduoj-ide-node').mkdir()
    with pytest.raises(ValueError, match='existing'):
        setup.validate(tmp_path, 'sduoj-ide-node')

release=module('ide_cgroup_v2_release')

def test_empty_bundle_is_rejected(tmp_path):
 import json
 (tmp_path/'qualification-lock.json').write_text(json.dumps({'status':'NODE_QUALIFIED_NOT_PRODUCTION_ACTIVATED','productionActivated':False,'files':{}}))
 with pytest.raises(ValueError):release.validate_bundle(tmp_path)

@pytest.mark.parametrize('value',[float('nan'),float('inf'),True,None])
def test_nonfinite_or_boolean_timing_is_rejected(value):
 assert not release.finite(value)

@pytest.mark.parametrize('field,value',[('Devices',[{'PathOnHost':'/dev/sda'}]),('SecurityOpt',['seccomp=unconfined']),('MaskedPaths',['/proc/kcore'])])
def test_outer_security_drift_rejected(field,value):
 expected,instance,info=fixture();instance['HostConfig'][field]=value
 with pytest.raises(ValueError):runtime.check_contract(info,instance,[instance],expected)

def test_extra_host_mount_and_stopped_runtime_rejected():
 expected,instance,info=fixture();instance['Mounts'].append({'Type':'bind','Source':'/','Destination':'/host','RW':False})
 with pytest.raises(ValueError):runtime.check_contract(info,instance,[instance],expected)
 expected,instance,info=fixture();instance['State']['Running']=False
 with pytest.raises(ValueError):runtime.check_contract(info,instance,[instance],expected)

def test_real_capacity_schema_and_raw_recompute():
 import json
 p=Path('/Volumes/SSD/sduoj-dev/work/artifacts/ide-worker-tuning-20261025/resource-matrix-r6-p7-final-1/p7/raw.json')
 if not p.exists():pytest.skip('Local historical raw fixture unavailable')
 raw=json.loads(p.read_text());release.validate_capacity(raw)
 raw['stages'][2]['byLanguage']['java']['validP95']=float('nan')
 with pytest.raises(ValueError):release.validate_capacity(raw)
