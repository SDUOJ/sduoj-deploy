import copy
import importlib.util
import json
import re
from pathlib import Path
import sys
import subprocess
import shutil
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('dev_network', HERE / 'dev-network.py')
network = importlib.util.module_from_spec(spec)
spec.loader.exec_module(network)


class DevNetworkTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('docker'), 'Docker Compose parser unavailable')
    def test_resolved_literal_dollars_survive_real_compose_parser_without_env_expansion(self):
        value = 'literal$HOME${UNSET_NETWORK_FIXTURE}$$suffix'
        fixture = {'name': network.OWNER, 'services': {'fixture': {
            'image': 'registry.invalid/static@sha256:' + '1' * 64,
            'environment': {'STATIC_LITERAL_FIXTURE': value},
            'command': ['literal', value]}}}
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'compose.json'
            fixture['services']['fixture']['environment']['STATIC_LITERAL_FIXTURE'] = value.replace('$', '$$')
            fixture['services']['fixture']['command'] = ['literal', value.replace('$', '$$')]
            file.write_text(json.dumps(fixture))
            result = subprocess.run(['docker', 'compose', '-p', network.OWNER, '-f',
                                     str(file), 'config', '--format', 'json'],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            service = json.loads(result.stdout)['services']['fixture']
            # config JSON is a round-trippable document: dollars remain escaped.
            self.assertEqual(service['environment']['STATIC_LITERAL_FIXTURE'], value.replace('$', '$$'))
            self.assertEqual(service['command'], ['literal', value.replace('$', '$$')])
            network.require_resolved_literals(json.loads(result.stdout))
            with self.assertRaises(ValueError):
                network.require_resolved_literals({'environment': {'RAW': value}})

    def setUp(self):
        raw = (HERE.parents[1] / 'compose.combined-release.dev.yaml').read_text()
        self.base = json.loads(re.sub(r'\$\{[^}]+\}', 'static-fixture', raw))
        for service in self.base['services'].values():
            service['ports'] = [dict(host_ip=row.split(':')[0], published=row.split(':')[1],
                                     target=int(row.split(':')[2]), protocol='tcp')
                                for row in service.get('ports', [])]

    def test_preserves_images_permissions_dependencies_and_existing_loopback_ports(self):
        before = copy.deepcopy(self.base)
        result = network.candidate(self.base, '192.168.0.10')
        self.assertEqual(self.base, before)
        for name, service in before['services'].items():
            actual = copy.deepcopy(result['services'][name])
            if name in network.JAVA_PORTS or name in network.DEPENDENCY_PORTS:
                count = 1 if name in network.JAVA_PORTS else len(network.DEPENDENCY_PORTS[name])
                actual['ports'] = actual['ports'][:-count]
                if name in network.JAVA_PORTS:
                    actual['command'] = actual['command'][:-2]
            self.assertEqual(actual, service)
        nacos = result['services']['nacos']['ports']
        self.assertEqual([(x['target'], x['published']) for x in nacos[-2:]],
                         [(8848, '38848'), (9848, '39848')])
        for name, port in network.JAVA_PORTS.items():
            self.assertIn('--spring.cloud.nacos.discovery.port=' + str(port),
                          result['services'][name]['command'])

    def test_rejects_production_owner_aliases_and_preexisting_public_bind(self):
        for address in ('127.0.0.1', '0.0.0.0', '169.254.68.46', '10.0.2.2',
                        '10.0.2.15', '8.8.8.8', '224.0.0.1', '::1'):
            with self.assertRaises(ValueError):
                network.candidate(self.base, address)
        for mutate in (lambda c: c.update(name='production'),
                       lambda c: c['services']['rabbit']['labels'].update(owner='other-task'),
                       lambda c: c['services']['nacos']['ports'][0].update(host_ip='0.0.0.0'),
                       lambda c: c['services']['gateway']['command'].append('--spring.cloud.nacos.discovery.ip=old')):
            c = copy.deepcopy(self.base)
            mutate(c)
            with self.assertRaises(ValueError):
                network.candidate(c, '192.168.0.10')


if __name__ == '__main__':
    unittest.main()
