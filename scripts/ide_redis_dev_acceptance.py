#!/usr/bin/env python3
"""Bounded correctness checks for the opt-in local Gateway/Redis worker chain.

No load generation. Credentials are read from existing private dev files and
never copied to the report. Only a loopback Gateway is accepted.
"""
import argparse
import json
import math
from pathlib import Path
import time
import uuid
from urllib.parse import urlparse

import requests


TEMPLATES = {'c': '19', 'cpp': '32', 'python': '38', 'java': '51'}
CASES = {
    'c': {
        'complete': '#include <stdio.h>\nint main(){ pri|; }', 'label': 'printf',
        'semantic': 'int add(int left, int right){return left+right;}\nint main(){return add(1,2);}',
        'definition': (2, 20), 'signature': (2, 23),
        'debug': '#include <stdio.h>\nint main() {\n int value=41;\n value += 1;\n int input=0;\n scanf("%d", &input);\n printf("ECHO:%d\\n", value+input);\n return 0;\n}\n',
        'breakpoints': [4, 7], 'bad': 'int main( { !!!',
        'loop': 'int main(){volatile unsigned long n=0; while(1){n++;}}',
    },
    'cpp': {
        'complete': '#include <string>\nint main(){std::string text; text.sub|;}', 'label': 'substr',
        'semantic': 'int add(int left, int right){return left+right;}\nint main(){return add(1,2);}',
        'definition': (2, 20), 'signature': (2, 23),
        'debug': '#include <iostream>\nint main() {\n int value=41;\n value += 1;\n int input=0;\n std::cin >> input;\n std::cout << "ECHO:" << value+input << std::endl;\n return 0;\n}\n',
        'breakpoints': [4, 7], 'bad': 'int main( { !!!',
        'loop': 'int main(){volatile unsigned long n=0; while(true){n++;}}',
    },
    'python': {
        'complete': 'pri|', 'label': 'print',
        'semantic': 'def add(left, right):\n return left+right\nvalue=add(1,2)\n',
        'definition': (3, 8), 'signature': (3, 12),
        'debug': 'value=41\nvalue += 1\nnumber=int(input())\nprint("ECHO:"+str(value+number))\n',
        'breakpoints': [2, 4], 'bad': 'def broken(:\n !!!',
        'loop': 'n=0\nwhile True:\n n+=1\n',
    },
    'java': {
        'complete': 'public class Main { public static void main(String[] args){ String text=""; text.sub|; } }',
        'label': 'substring',
        'semantic': 'public class Main {\n static int add(int left,int right){return left+right;}\n public static void main(String[] args){ int value=add(1,2); }\n}',
        'definition': (3, 51), 'signature': (3, 55),
        'debug': 'import java.util.Scanner;\npublic class Main {\n public static void main(String[] args) {\n  int value=41;\n  value += 1;\n  Scanner scanner=new Scanner(System.in);\n  int number=scanner.nextInt();\n  System.out.println("ECHO:"+(value+number));\n }\n}\n',
        'breakpoints': [5, 8], 'bad': 'public class Main { !!!',
        'loop': 'public class Main {public static void main(String[] args){long n=0;while(true){n++;}}}',
    },
}


MAX_DEBUG_LIFETIME_SECONDS = 1800
TIMEOUT_CLEANUP_MARGIN_SECONDS = 10


def run_timeout_observation_seconds(session):
    """Client measurement budget; never sends or changes a service deadline."""
    limit = session.get('runLimitSeconds')
    if (type(limit) not in (int, float) or not math.isfinite(limit)
            or not 0 < limit <= MAX_DEBUG_LIFETIME_SECONDS):
        raise ValueError('Expected a bounded advertised runLimitSeconds')
    return limit + TIMEOUT_CLEANUP_MARGIN_SECONDS


class Client:
    def __init__(self, base, credentials, report, problem_code="SDUOJ-1000"):
        self.problem_code = problem_code
        self.base, self.report, self.last = base, report, 0.
        self.http = requests.Session()
        self.http.trust_env = False
        self.http.headers['User-Agent'] = 'SDUOJ-local-IDE-acceptance'
        value = json.loads(Path(credentials).read_text()) if isinstance(credentials, str) else credentials
        response = self.http.post(base + '/api/user/login', json={k: value[k] for k in ('username', 'password')}, timeout=15)
        assert response.status_code == 200 and response.json()['code'] == 0, 'Real login failed'

    def call(self, path, body=None, expected=200, pace=True):
        if pace:
            time.sleep(max(0., .36 - (time.monotonic() - self.last)))
        self.last = time.monotonic()
        began = time.monotonic()
        response = self.http.request('GET' if body is None else 'POST', self.base + '/api/ps/ide' + path,
                                     json=body, timeout=30)
        value = response.json()
        self.report.append({'path': path, 'status': response.status_code,
                            'seconds': round(time.monotonic() - began, 4), 'response': value})
        assert response.status_code == expected, (path, response.status_code, value)
        if expected != 200:
            return value
        assert value.get('code') == 0, value
        return value.get('data')

    def create_lsp(self, language, code):
        return self.call('/session', dict(protocolVersion=1, clientSessionKey=uuid.uuid4().hex,
            language=language, judgeTemplateId=TEMPLATES[language], problemCode=self.problem_code,
            context={'type': 0, 'problemCode': self.problem_code}, code=code))

    def create_debug(self, language, code, breakpoints):
        return self.call('/debug/session', dict(commandId=uuid.uuid4().hex, language=language,
            judgeTemplateId=TEMPLATES[language], problemCode=self.problem_code,
            context={'type': 0, 'problemCode': self.problem_code}, code=code, input='',
            breakpoints=breakpoints, replaceExisting=True))

    def poll(self, session):
        value = self.call('/debug/session/' + session['sessionId'] + '/events', {'cursor': 0, 'waitSeconds': 1})
        assert value['cursor'] == value['snapshot']['cursor'], 'Snapshot cannot acknowledge undelivered events'
        if value['events']:
            assert value['cursor'] == value['events'][-1]['cursor'], 'Event acknowledgement must match persisted log'
        return value

    def wait(self, session, condition=None, seconds=65):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            value = self.poll(session)
            snapshot = value['snapshot']
            if condition and condition(snapshot):
                return snapshot, value
            if not condition and snapshot['state'] == 'stopped' and not snapshot['busy']:
                return snapshot, value
            if snapshot['state'] in ('failed', 'terminated', 'lost'):
                raise AssertionError(('Unexpected debugger terminal', snapshot, value))
            time.sleep(.25)
        raise TimeoutError('Debug state deadline')

    def dispatch(self, session, operation, arguments):
        command_id = uuid.uuid4().hex
        body = dict(commandId=command_id, sessionEpoch=session['sessionEpoch'],
                    expectedStateVersion=session['stateVersion'], stopId=session.get('stopId'),
                    operation=operation, arguments=arguments)
        self.call('/debug/session/' + session['sessionId'] + '/command', body)
        return command_id, body

    def command(self, session, operation, arguments, replay=False):
        command_id, body = self.dispatch(session, operation, arguments)
        snapshot, events = self.wait(session, lambda s: any(c['commandId'] == command_id and
            c['status'] in ('completed', 'failed', 'unknown') for c in s.get('commands', [])))
        receipt = next(c for c in snapshot['commands'] if c['commandId'] == command_id)
        assert receipt['status'] == 'completed', receipt
        if replay:
            duplicate = self.call('/debug/session/' + session['sessionId'] + '/command', body)
            assert duplicate['stateVersion'] == snapshot['stateVersion'] and duplicate['stopId'] == snapshot['stopId'], 'Duplicate command executed twice'
        return snapshot, receipt.get('result', {}), events

    def stop(self, session):
        return self.call('/debug/session/' + session['sessionId'] + '/stop', {'sessionEpoch': session['sessionEpoch']})


def lsp_checks(client, language, result, other):
    case = CASES[language]
    marked = case['complete']
    before = marked[:marked.index('|')]
    line, column = before.count('\n') + 1, len(before.rsplit('\n', 1)[-1]) + 1
    session = client.create_lsp(language, marked.replace('|', ''))
    assert session and session['toolchain']['templateId'] == TEMPLATES[language], session
    sid = session['sessionId']
    try:
        for attempt in range(35):
            value = client.call('/session/' + sid + '/completion', {'revision': 1, 'line': line, 'column': column})
            if value and any(case['label'] in item.get('label', '') for item in value.get('items', [])):
                break
            time.sleep(1)
        else:
            raise AssertionError(('No expected completion', language, value))
        result['completion'] = {'attempts': attempt + 1, 'expected': case['label'], 'response': value}
        other.call('/session/' + sid + '/state', {}, expected=410)
        result['otherUserDenied'] = True
        revision = 2
        synced = client.call('/session/' + sid + '/sync', {'baseRevision': 1, 'revision': revision, 'code': case['semantic']})
        assert synced['revision'] == revision, synced
        # A stale base is explicit; source and committed revision are recoverable.
        conflict = client.call('/session/' + sid + '/sync', {'baseRevision': 1, 'revision': 3, 'code': 'stale'}, expected=409)
        result['revisionConflict'] = conflict
        for operation, coordinate in [('definition', case['definition']), ('signatureHelp', case['signature'])]:
            last = None
            for _ in range(5):
                last = client.call('/session/' + sid + '/' + operation,
                                   dict(revision=revision, line=coordinate[0], column=coordinate[1]))
                field = 'locations' if operation == 'definition' else 'signatures'
                if last and last.get(field):
                    break
                time.sleep(.7)
            assert last and last.get(field), (language, operation, last)
            result[operation] = last
        client.call('/session/' + sid + '/sync', {'baseRevision': 2, 'revision': 3, 'code': case['bad']})
        for _ in range(6):
            diagnostics = client.call('/session/' + sid + '/diagnostics', {'revision': 3})
            if diagnostics and any(row['severity'] == 'error' for row in diagnostics.get('diagnostics', [])):
                break
            time.sleep(.7)
        assert diagnostics and any(row['severity'] == 'error' for row in diagnostics.get('diagnostics', [])), (language, diagnostics)
        result['diagnostics'] = diagnostics
        combined = client.call('/session/' + sid + '/completion', dict(baseRevision=3, revision=4,
            code=marked.replace('|', ''), line=line, column=column))
        assert combined and combined['revision'] == 4, combined
        state = client.call('/session/' + sid + '/state', {})
        assert state['revision'] == 4, state
        result['combinedSyncCommitted'] = True
        result['passed'] = True
    finally:
        client.call('/session/' + sid + '/close', {})


def debug_checks(client, language, result, other):
    case = CASES[language]
    session = client.create_debug(language, case['debug'], case['breakpoints'])
    assert session, 'Debug create was rate limited'
    try:
        session, _ = client.wait(session)
        other.call('/debug/session/' + session['sessionId'] + '/events', {'cursor': 0, 'waitSeconds': 0}, expected=410)
        result['otherUserDenied'] = True
        session, stack, _ = client.command(session, 'stackTrace', {'threadId': session['threadId']})
        if stack['stackFrames'][0]['line'] != case['breakpoints'][0]:
            session, _, _ = client.command(session, 'continue', {'threadId': session['threadId']})
            session, stack, _ = client.command(session, 'stackTrace', {'threadId': session['threadId']})
        assert stack['stackFrames'][0]['line'] == case['breakpoints'][0], stack
        frame = stack['stackFrames'][0]['id']
        session, watch, _ = client.command(session, 'watch', {'frameId': frame, 'expressions': ['value']})
        assert watch['watches'][0]['available'] and watch['watches'][0]['value'] == '41', watch
        result['watch'] = watch
        session, _, _ = client.command(session, 'next', {'threadId': session['threadId']}, replay=True)
        result['stepReplayDidNotExecuteTwice'] = True
        client.dispatch(session, 'continue', {'threadId': session['threadId']})
        session, _ = client.wait(session, lambda s: s['state'] == 'running')
        # The program is now waiting for interactive input, in the sandbox.
        session, _, _ = client.command(session, 'stdin', {'text': '5\n'})
        session, _ = client.wait(session)
        client.dispatch(session, 'continue', {'threadId': session['threadId']})
        session, events = client.wait(session, lambda s: s['state'] in ('terminated', 'failed'), seconds=20)
        output = ''.join(event.get('data', {}).get('output', '') for event in events['events'] if event['type'] == 'output')
        assert 'ECHO:47' in output, (language, output, session)
        result['output'] = output
    finally:
        client.stop(session)
    failed = client.create_debug(language, case['bad'], [])
    try:
        failed, events = client.wait(failed, lambda s: s['state'] in ('terminated', 'failed'), seconds=50)
        assert any(e['type'] == 'compileError' for e in events['events']), events
        result['compileErrorVisible'] = True
    finally:
        client.stop(failed)
    looping = client.create_debug(language, case['loop'], [])
    try:
        looping, _ = client.wait(looping)
        client.dispatch(looping, 'continue', {'threadId': looping['threadId']})
        observation_seconds = run_timeout_observation_seconds(looping)
        looping, events = client.wait(looping, lambda s: s['state'] in ('terminated', 'failed'), seconds=observation_seconds)
        assert looping['reason'] == 'DEBUG_RUN_TIMEOUT', events
        result['runTimeoutVisible'] = True
        result['runLimitSeconds'] = looping['runLimitSeconds']
        result['timeoutObservationBudgetSeconds'] = observation_seconds
    finally:
        client.stop(looping)
    result['passed'] = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:8080')
    parser.add_argument('--problem-code', default='SDUOJ-1000')
    parser.add_argument('--users', default='sduoj-deploy/data/dev/ai-integration/ide-language-users.json')
    parser.add_argument('--other-user', default='sduoj-deploy/data/dev/ai-integration/ide-meta-user.json')
    parser.add_argument('--output', required=True)
    parser.add_argument('--scope', choices=['lsp', 'debug', 'all'], default='all')
    parser.add_argument('--languages', default='c,cpp,python,java')
    args = parser.parse_args()
    assert urlparse(args.base).hostname in ('localhost', '127.0.0.1'), 'Local correctness only'
    report = {'passed': False, 'base': args.base, 'scope': args.scope, 'cases': {}, 'http': []}
    users = json.loads(Path(args.users).read_text())
    other = Client(args.base, args.other_user, report['http'], args.problem_code)
    try:
        for language in args.languages.split(','):
            result = report['cases'][language] = {}
            client = Client(args.base, users[TEMPLATES[language]], report['http'], args.problem_code)
            try:
                if args.scope in ('lsp', 'all'):
                    lsp_checks(client, language, result.setdefault('lsp', {}), other)
                if args.scope in ('debug', 'all'):
                    debug_checks(client, language, result.setdefault('debug', {}), other)
            except Exception as error:
                result['error'] = str(error)
            Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False))
            print(json.dumps({'language': language, 'result': {k: v.get('passed', False) for k, v in result.items() if isinstance(v, dict)}, 'error': result.get('error')}, ensure_ascii=False), flush=True)
        report['passed'] = all(not value.get('error') for value in report['cases'].values())
    finally:
        Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
