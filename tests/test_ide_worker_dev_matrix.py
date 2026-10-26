"""Pure checks for matrix scope, contracts and cleanup; no SSH/Docker/network."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import urllib.error

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('ide_worker_dev_matrix', SCRIPTS / 'ide_worker_dev_matrix.py')
matrix = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = matrix
spec.loader.exec_module(matrix)
IMAGE = 'sha256:' + 'a' * 64
PREFIX = 'sduoj:ide:release-gates:20261025:'


def template():
    return {'schemaVersion': 1, 'environment': {
        'SDUOJ_IDE_PREFIX': PREFIX, 'SDUOJ_IDE_REDIS_URL': '${AUTOLAB_REDIS_URL}',
        'AUTOLAB_IDE_TOOLCHAIN_TOKEN': '${DEV_RPC_TOKEN}',
        'AUTOLAB_DEBUG_RESIDENT': '8', 'AUTOLAB_DEBUG_ACTIVE': '2',
        'AUTOLAB_DEBUG_BUDGET': '1342177280', 'AUTOLAB_DEBUG_HARD': '1610612736',
        'SDUOJ_IDE_JAVA_PROCESSORS': '2'}}


def health(documents=0, debug_active=0):
    return {'ready': True, 'components': [
        {'role': 'lsp', 'language': lang, 'metrics': {'languages': {lang: {'documents': documents}}}}
        for lang in matrix.LANGUAGES] + [{'role': 'debug', 'metrics': {
            'resident': debug_active, 'active': debug_active, 'queued': 0, 'grantedBytes': 0}}]}


def sample(profile=None, worker_id='matrix-fixture-p0'):
    profile = profile or matrix.PROFILES['p0']
    registry = {'lsp:' + lang: [worker_id + '-' + lang] for lang in matrix.LANGUAGES}
    registry['debug:all'] = [worker_id + '-debug']
    return {'nacosReady': True, 'mini': {'gatewayHealthy': True,
        'memory': {'MemAvailable': 3 * matrix.GiB}}, 'remote': {
            'identity': {'image': IMAGE, 'status': 'running', 'oomKilled': False,
                'NanoCpus': int(profile.cpus * 1e9), 'Memory': profile.memory_gib * matrix.GiB,
                'PidsLimit': 1024}, 'health': health(), 'probe': {
                    'registry': registry, 'memory': {'MemAvailable': 20 * matrix.GiB},
                    'cgroup': {'memory.current': '123456', 'memory.events': 'oom 0\noom_kill 0\nmax 0\n'},
                    'jdtls': [{'flags': ['-Xms1G', '-Xms64m', '-Xmx384m', '-XX:ActiveProcessorCount=2']}]}}}


def args_fixture(tmp_path):
    users = tmp_path / 'users.json'
    users.write_text(json.dumps({'users': [{'username': 'u' + str(i), 'password': 'test-only'} for i in range(500)]}))
    users.chmod(0o600)
    known = tmp_path / 'known_hosts'
    known.write_text('test fixture, not an actual host key\n')
    config = tmp_path / 'template.json'
    config.write_text(json.dumps(template()))
    return matrix.parser().parse_args([
        '--ssh-host', 'experiment-mac', '--host-address', '169.254.68.46',
        '--known-hosts', str(known), '--remote-root', '/private/tmp/sduoj-ide-probe-test',
        '--image-id', IMAGE, '--image-tag', 'sduoj-ide-unified:release-gates-20261025-r6',
        '--output-dir', str(tmp_path / 'out'), '--users', str(users),
        '--gateway-base', 'http://127.0.0.1:18087', '--nacos-base', 'http://127.0.0.1:8848',
        '--config-template', str(config), '--python', sys.executable, '--profiles', 'p0'])


def test_profiles_change_one_dimension_before_combined_downsizing():
    p = matrix.PROFILES
    assert (p['p0'].cpus, p['p0'].memory_gib) == (1.5, 4)
    assert p['p1'].cpus == 4 and p['p1'].memory_gib == p['p0'].memory_gib
    assert p['p2'].cpus == p['p1'].cpus and p['p2'].memory_gib == 8
    assert p['p3'].cpus == p['p2'].cpus and p['p3'].c_cpp_documents == 48
    assert p['p4'].java_processors is None
    assert (p['p5'].cpus, p['p5'].memory_gib) == (2, 6)
    assert p['p5'].guard_bytes == int(5.25 * matrix.GiB)
    assert p['p2'].guard_bytes == 7 * matrix.GiB


def test_configs_preserve_debug_and_secrets_and_remove_p4_override():
    original = template()
    for name, profile in matrix.PROFILES.items():
        value = matrix.profile_config(original, profile)
        env = value['environment']
        assert {k: v for k, v in env.items() if k.startswith('AUTOLAB_DEBUG_')} == {
            k: v for k, v in original['environment'].items() if k.startswith('AUTOLAB_DEBUG_')}
        assert env['AUTOLAB_IDE_TOOLCHAIN_TOKEN'] == '${DEV_RPC_TOKEN}'
        assert env['SDUOJ_IDE_C_MAX_DOCUMENTS'] == str(profile.c_cpp_documents)
        assert env['SDUOJ_IDE_JAVA_MAX_DOCUMENTS'] == '32'
        assert env.get('SDUOJ_IDE_JAVA_PROCESSORS') == (None if name == 'p4' else '2')
    assert original == template()


def test_additional_memory_candidates_keep_residence_cpu_and_jvm_fixed(tmp_path):
    args = args_fixture(tmp_path)
    args.profiles = ['p6', 'p7']
    selected = matrix.validate_args(args)
    assert selected.profiles == ['p6', 'p7']
    p6, p7 = (matrix.PROFILES[name] for name in selected.profiles)
    assert (p6.cpus, p6.memory_gib, p6.c_cpp_documents) == (4, 4, 48)
    assert (p7.cpus, p7.memory_gib, p7.c_cpp_documents) == (4, 6, 48)
    assert p6.java_python_documents == p7.java_python_documents == 32
    assert p6.java_processors == p7.java_processors == 2
    assert p6.guard_bytes == int(3.5 * matrix.GiB)
    assert p7.guard_bytes == int(5.25 * matrix.GiB)
    for profile in (p6, p7):
        env = matrix.profile_config(template(), profile)['environment']
        assert env['SDUOJ_IDE_CLANGD_JOBS'] == '2'
        assert env['SDUOJ_IDE_JAVA_PROCESSORS'] == '2'
        assert env['SDUOJ_IDE_JAVA_HEAP_MB'] == '384'
        assert env['SDUOJ_IDE_C_MAX_DOCUMENTS'] == env['SDUOJ_IDE_CPP_MAX_DOCUMENTS'] == '48'
        assert env['SDUOJ_IDE_JAVA_MAX_DOCUMENTS'] == env['SDUOJ_IDE_PYTHON_MAX_DOCUMENTS'] == '32'
        assert env['AUTOLAB_DEBUG_RESIDENT'] == '8'


def test_original_matrix_default_does_not_silently_expand_with_new_candidates():
    action = next(action for action in matrix.parser()._actions if action.dest == 'profiles')
    assert action.default == ['p0', 'p1', 'p2', 'p3', 'p4', 'p5']
    assert 'p6' in action.choices and 'p7' in action.choices


@pytest.mark.parametrize('url', ['https://127.0.0.1:8848', 'http://example.org:8848',
    'http://127.0.0.1:8848/prod', 'http://u:p@localhost:8848', 'http://localhost:8848?tenant=prod'])
def test_non_dev_or_credential_urls_are_rejected(url):
    with pytest.raises(ValueError):
        matrix.loopback_url(url)


def test_dev_template_refuses_real_secret_and_other_prefix():
    wrong = template()
    wrong['environment']['AUTOLAB_IDE_TOOLCHAIN_TOKEN'] = 'do-not-publish-secret'
    with pytest.raises(ValueError, match='placeholders'):
        matrix.validate_template(wrong, PREFIX)
    with pytest.raises(ValueError, match='exactly'):
        matrix.validate_template(template(), 'sduoj:ide:prod:')


def test_args_refuse_existing_output_and_nonprivate_users(tmp_path):
    args = args_fixture(tmp_path)
    validated = matrix.validate_args(args)
    assert validated.active_list == [100]
    assert validated.python == Path(sys.executable).absolute()
    assert validated.output_dir.name == 'out'
    validated.output_dir.mkdir()
    with pytest.raises(ValueError, match='already exists'):
        matrix.validate_args(args)
    validated.output_dir.rmdir()
    args.users.chmod(0o644)
    with pytest.raises(ValueError, match='mode0600'):
        matrix.validate_args(args)


@pytest.mark.parametrize('field,value', [('existing_worker', 'unrelated-worker'),
    ('remote_root', '/private/tmp/../../etc'), ('image_id', 'mutable:latest'),
    ('image_tag', '--unsafe'), ('network', 'shared-network'), ('active_list', [300])])
def test_mutation_scope_is_constrained(tmp_path, field, value):
    args = args_fixture(tmp_path)
    setattr(args, field, value)
    with pytest.raises(ValueError):
        matrix.validate_args(args)


def test_idle_requires_every_language_and_all_debug_counters_zero():
    assert matrix.is_idle(health())
    assert not matrix.is_idle(health(documents=1))
    assert not matrix.is_idle(health(debug_active=1))
    missing = health()
    missing['components'].pop(0)
    assert not matrix.is_idle(missing)


def test_guards_distinguish_quota_host_and_registry_failures():
    profile = matrix.PROFILES['p0']
    value = sample()
    assert matrix.guard_reason(value, profile, 'matrix-fixture-p0', IMAGE) is None
    value['remote']['probe']['cgroup']['memory.current'] = str(profile.guard_bytes + 1)
    assert matrix.guard_reason(value, profile, 'matrix-fixture-p0', IMAGE) == 'worker_memory_guard'
    value = sample()
    value['mini']['memory']['MemAvailable'] = matrix.GiB - 1
    assert matrix.guard_reason(value, profile, 'matrix-fixture-p0', IMAGE) == 'VM_available_below1GiB'
    value = sample()
    value['remote']['probe']['registry']['lsp:c'].append('another-session-worker')
    assert matrix.guard_reason(value, profile, 'matrix-fixture-p0', IMAGE) == 'registry_not_single_expected_worker'
    value = sample()
    value['remote']['identity']['Memory'] *= 2
    assert matrix.guard_reason(value, profile, 'matrix-fixture-p0', IMAGE) == 'worker_identity_or_running_failure'


def test_java_flags_use_last_heap_and_verify_apc_omission():
    matrix.assert_java_flags(sample(), matrix.PROFILES['p0'])
    with pytest.raises(RuntimeError, match='flags differ'):
        matrix.assert_java_flags(sample(), matrix.PROFILES['p4'])
    value = sample()
    value['remote']['probe']['jdtls'][0]['flags'] = ['-Xms1G', '-Xms64m', '-Xmx384m']
    matrix.assert_java_flags(value, matrix.PROFILES['p4'])


def test_ssh_pins_identity_and_disables_agent_and_proxy(tmp_path):
    args = matrix.validate_args(args_fixture(tmp_path))
    command = matrix.ssh_command(args)
    for option in ('ForwardAgent=no', 'ProxyJump=none', 'ProxyCommand=none',
                   'StrictHostKeyChecking=yes', 'ControlMaster=no', 'ControlPath=none'):
        assert option in command
    assert 'UserKnownHostsFile=' + str(args.known_hosts) in command
    assert command[-2:] == ['experiment-mac', '/usr/bin/python3 -']


@pytest.mark.parametrize('missing', ['Error: No such object', 'error: no such object'])
@pytest.mark.parametrize('bad_image', [None, 'id', 'entrypoint'])
def test_remote_start_uses_frozen_id_and_checks_owner_without_reading_env(tmp_path, monkeypatch, capsys, missing, bad_image):
    root = tmp_path / 'private-root'
    root.mkdir(mode=0o700)
    env = root / 'worker.env'
    env.write_text('NEVER_READ_THIS=test-only\n')
    env.chmod(0o600)
    name = 'sduoj-ide-matrix-20261025-unit-p4'
    calls, started = [], [False]
    def invoke(command, **kwargs):
        assert command[0] == '/usr/local/bin/docker'
        calls.append(command[1:])
        args = command[1:]
        if args == ['inspect', name] and not started[0]:
            return subprocess.CompletedProcess(command, 1, '', missing)
        if args[:2] == ['image', 'inspect']:
            assert args[2] == IMAGE
            value = [{'Id': 'sha256:' + 'b' * 64 if bad_image == 'id' else IMAGE,
                'Config': {'Entrypoint': ['unexpected'] if bad_image == 'entrypoint'
                    else ['python3', '/opt/sduoj-ide/scripts/entrypoint.py']}}]
        elif args[:2] == ['network', 'inspect']:
            value = [{'Labels': {'owner': str(root)}}]
        elif args[0] == 'run':
            started[0] = True
            return subprocess.CompletedProcess(command, 0, 'container-id\n', '')
        else:
            value = [{'Id': 'container-id', 'Image': IMAGE, 'Config': {'Labels': {'owner': str(root)}},
                'HostConfig': {'NanoCpus': 4_000_000_000, 'Memory': 8 * matrix.GiB, 'PidsLimit': 1024},
                'State': {'Status': 'running', 'Running': True, 'OOMKilled': False}}]
        return subprocess.CompletedProcess(command, 0, json.dumps(value), '')
    monkeypatch.setattr(subprocess, 'run', invoke)
    original_read_text = Path.read_text
    def reject_env_read(self, *args, **kwargs):
        if self == env:
            raise AssertionError('Orchestrator must not read worker.env')
        return original_read_text(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', reject_env_read)
    payload = dict(operation='start', remote_root=str(root), image_id=IMAGE,
        image_tag='sduoj-ide-unified:test', name=name, network='sduoj-ide-mbp-20261025',
        cpus=4, memory_gib=8, run_id='unit', data_id='ide-worker-matrix-dev-20261025-unit-p4.yml',
        worker_id='matrix-unit-p4', service='ide-worker-matrix-dev-20261025-unit-p4')
    if bad_image:
        with pytest.raises(RuntimeError, match='frozen_image_ID_mismatch' if bad_image == 'id' else 'unexpected_image_entrypoint'):
            exec(compile(matrix.REMOTE, '<remote-test>', 'exec'), {'PAYLOAD': payload})
        assert not any(args[0] == 'run' for args in calls)
        return
    exec(compile(matrix.REMOTE, '<remote-test>', 'exec'), {'PAYLOAD': payload})
    output = json.loads(capsys.readouterr().out)
    assert output['identity']['image'] == IMAGE
    run = next(args for args in calls if args[0] == 'run')
    assert run[-7:] == [IMAGE, '-u', 'SDUOJ_IDE_JAVA_PROCESSORS', 'python3',
                       '/opt/sduoj-ide/scripts/entrypoint.py', '--role', 'all']
    assert run[run.index('--env-file') + 1] == str(env)
    assert '--privileged' in run and '--read-only' in run and '--pull' in run
    assert '127.0.0.1:19086:9086' in run
    assert all(args[2] == IMAGE for args in calls if args[:2] == ['image', 'inspect'])


def test_nacos_existing_data_id_is_never_overwritten(monkeypatch):
    monkeypatch.delenv('NACOS_USERNAME', raising=False)
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
    calls = []
    def open_url(*args, **kwargs):
        calls.append(args[0])
        return Response()
    monkeypatch.setattr(matrix.urllib.request, 'urlopen', open_url)
    with pytest.raises(RuntimeError, match='already exists'):
        matrix.Nacos('http://127.0.0.1:8848').publish(
            'ide-worker-matrix-dev-20261025-unit-p0.yml', template())
    assert len(calls) == 1 and isinstance(calls[0], str)


def test_nacos_readback_allows_bounded_404_visibility_after_durable_ack(monkeypatch):
    import io
    monkeypatch.delenv('NACOS_USERNAME', raising=False)
    config = template()
    calls = []
    class Response(io.BytesIO):
        pass
    def open_url(request, **_):
        calls.append(request)
        if len(calls) in (1, 3, 4):
            raise matrix.urllib.error.HTTPError('http://localhost', 404, 'not visible', {}, None)
        if len(calls) == 2:
            return Response(b'true')
        return Response(json.dumps(config).encode())
    sleeps = []
    monkeypatch.setattr(matrix.urllib.request, 'urlopen', open_url)
    monkeypatch.setattr(matrix.time, 'sleep', sleeps.append)
    result = matrix.Nacos('http://127.0.0.1:8848').publish(
        'ide-worker-matrix-dev-20261025-unit-p0.yml', config)
    assert len(result) == 64
    assert sleeps == [.05, .1]
    assert len(calls) == 5


def test_raw_summary_keeps_failed_samples_and_does_not_mutate_raw():
    raw = {'stages': [{'activeUsers': 100, 'complete': False, 'results': [
        {'phase': 'ramp', 'seconds': 9, 'outcome': 'degraded'},
        {'phase': 'steady', 'seconds': .5, 'outcome': 'valid'},
        {'phase': 'steady', 'seconds': 3, 'outcome': 'null_result'}]}],
        'cleanup': {'attempted': 500, 'closed': 500}}
    before = copy.deepcopy(raw)
    result = matrix.summarize_raw(raw, {'profile': {'name': 'p0'}, 'loadExitcode': -2,
                                     'stopReason': 'worker_memory_guard'})
    assert raw == before
    assert result['stages'][0]['metrics']['validRate'] == .5
    assert result['stages'][0]['metrics']['p95'] == 3
    assert result['stages'][0]['metrics']['validP95'] == .5
    assert result['stages'][0]['complete'] is False


def test_artifacts_are_exclusive_and_source_mutations_stop_the_matrix(tmp_path):
    path = tmp_path / 'artifact.json'
    matrix.write_new(path, {'original': True})
    with pytest.raises(FileExistsError):
        matrix.write_new(path, {'original': False})
    assert json.loads(path.read_text()) == {'original': True}
    source = tmp_path / 'source.py'
    source.write_text('version = 1\n')
    args = SimpleNamespace(frozen_source_hashes={str(source): matrix.sha256(source)})
    matrix.assert_frozen_sources(args)
    source.write_text('version = 2\n')
    with pytest.raises(RuntimeError, match='source changed'):
        matrix.assert_frozen_sources(args)


def test_failed_remote_start_still_attempts_only_owned_candidate_stop(tmp_path, monkeypatch):
    args = matrix.validate_args(args_fixture(tmp_path))
    args.output_dir.mkdir(mode=0o700)
    operations = []
    class Remote:
        def call(self, operation, **values):
            operations.append((operation, values))
            if operation == 'start':
                raise RuntimeError('response lost after Docker create')
            return {'stopped': True}
    class Nacos:
        def publish(self, *_):
            return 'config-sha'
    result = matrix.run_profile(args, matrix.PROFILES['p0'], 'unit', Remote(), Nacos())
    assert not result['completed']
    assert [op for op, _ in operations] == ['start', 'stop']
    assert operations[1][1]['name'] == 'sduoj-ide-matrix-20261025-unit-p0'
    assert operations[1][1]['require_idle'] is False
    assert (args.output_dir / 'p0/result.json').is_file()


def contained_memory_guard():
    value = sample()
    return {'stopReason': 'worker_memory_guard', 'executed': True, 'completed': False,
        'qualified': False, 'imageId': IMAGE, 'allSamplesMemoryEventsClear': True,
        'cleanupDependenciesHealthy': True, 'cleanup': {'attempted': 500, 'closed': 500},
        'cleanupHealth': value['remote'], 'stopped': {'identity': {
            'image': IMAGE, 'status': 'exited', 'oomKilled': False}}}


def test_memory_guard_continuation_is_opt_in_and_requires_changed_next_profile():
    value = contained_memory_guard()
    p0, p1 = matrix.PROFILES['p0'], matrix.PROFILES['p1']
    assert matrix.may_continue_memory_guard(True, value, p0, p1)
    assert not matrix.may_continue_memory_guard(False, value, p0, p1)
    assert not matrix.may_continue_memory_guard(True, value, p0, p0)
    assert not matrix.may_continue_memory_guard(True, value, p0, None)


@pytest.mark.parametrize('failure', ['dependency', 'oom', 'cleanup', 'busy', 'stop',
                                    'identity', 'probe', 'host', 'incomplete-evidence'])
def test_memory_guard_never_conceals_infrastructure_or_unclean_failure(failure):
    value = contained_memory_guard()
    if failure == 'dependency':
        value['cleanupDependenciesHealthy'] = False
    elif failure == 'oom':
        value['cleanupHealth']['probe']['cgroup']['memory.events'] = 'oom 1\noom_kill 0\nmax 0\n'
    elif failure == 'cleanup':
        value['cleanup']['closed'] = 499
    elif failure == 'busy':
        value['cleanupHealth']['health'] = health(documents=1)
    elif failure == 'stop':
        value['stopped']['identity']['status'] = 'running'
    elif failure == 'identity':
        value['stopped']['identity']['image'] = 'sha256:' + 'b' * 64
    elif failure == 'probe':
        value['cleanupProbeCategory'] = 'TimeoutExpired'
    elif failure == 'host':
        value['stopReason'] = 'VM_available_below1GiB'
    else:
        value['allSamplesMemoryEventsClear'] = False
    assert not matrix.may_continue_memory_guard(True, value, matrix.PROFILES['p0'], matrix.PROFILES['p1'])


def test_completed_execution_exit_zero_does_not_claim_slo_qualification(tmp_path, monkeypatch):
    args = matrix.validate_args(args_fixture(tmp_path))
    monkeypatch.setattr(matrix, 'parser', lambda: SimpleNamespace(parse_args=lambda _: args))
    monkeypatch.setattr(matrix, 'validate_args', lambda value: value)
    monkeypatch.setattr(matrix, 'mini_sample', lambda: {'gatewayHealthy': True})
    class Remote:
        def __init__(self, *_):
            pass
        def call(self, *_args, **_kwargs):
            return {'test': 'only'}
    class Nacos:
        def __init__(self, *_):
            pass
        def ready(self):
            return True
    monkeypatch.setattr(matrix, 'Remote', Remote)
    monkeypatch.setattr(matrix, 'Nacos', Nacos)
    monkeypatch.setattr(matrix, 'run_profile', lambda *_: {'completed': True, 'executed': True,
        'qualified': False, 'stopReason': None})
    assert matrix.main([]) == 0
    result = json.loads((args.output_dir / 'matrix-result.json').read_text())
    assert result['allProfilesExecuted'] is True
    assert result['allProfilesQualified'] is False
