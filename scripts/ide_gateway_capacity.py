#!/usr/bin/env python3
"""Bounded, authenticated loopback Gateway load; empty/degraded is not success.

One real identity/session per online user. Preserve the browser's separate sync
and completion calls, 300ms spacing, 4KiB source and 2.5s input cycle.
"""
import argparse
import asyncio
from collections import Counter
import json
import math
from pathlib import Path
import time
from urllib.parse import urlparse
import uuid

import httpx

from ide_redis_dev_acceptance import CASES, TEMPLATES
from ide_capacity_lifecycle import Lifecycle


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)] if ordered else None


class RevisionConflict(Exception):
    def __init__(self, revision):
        self.revision = revision
        super().__init__('IDE_REVISION_CONFLICT')


class APIError(RuntimeError):
    pass


class ReplyDataError(RuntimeError):
    def __init__(self, outcome):
        self.outcome = outcome
        super().__init__(outcome)


def response_revision(value, operation):
    if value is None:
        raise ReplyDataError(operation + '_null_result')
    if not isinstance(value, dict):
        raise ReplyDataError(operation + '_invalid_result')
    revision = value.get('revision')
    if type(revision) is not int or revision < 1:
        raise ReplyDataError(operation + '_invalid_revision')
    return revision


def summary(rows):
    times = [row['seconds'] for row in rows]
    valid = [row['seconds'] for row in rows if row['outcome'] == 'valid']
    return {'count': len(rows), 'outcomes': dict(Counter(row['outcome'] for row in rows)),
        'validRate': len(valid) / len(rows) if rows else 0,
        'p50': percentile(times, .5), 'p95': percentile(times, .95), 'p99': percentile(times, .99),
        'validP95': percentile(valid, .95)}


def completion_outcome(result, revision, language):
    if result is None:
        return 'null_result'
    if not isinstance(result, dict):
        return 'invalid_result'
    status = result.get('status')
    if status != 'ready':
        return status if isinstance(status, str) and status else 'missing_status'
    if result.get('revision') != revision:
        return 'stale'
    items = result.get('items', [])
    if not isinstance(items, list):
        return 'invalid_result'
    expected = CASES[language]['label']
    for item in items:
        if isinstance(item, dict) and any(isinstance(item.get(field), str)
                and item[field].startswith(expected) for field in ('label', 'filterText', 'insertText')):
            return 'valid'
    return 'empty'


async def run(args):
    if urlparse(args.base).hostname not in ('127.0.0.1', 'localhost'):
        raise ValueError('Local dev capacity only')
    if not 0 < args.stage_seconds <= 75 or not 0 < args.cycle_seconds or args.ramp_seconds < 0:
        raise ValueError('Invalid bounded load contract')
    if not args.active or any(not 10 <= n <= 500 or n % 10 for n in args.active):
        raise ValueError('Active stages must be multiples of 10 between 10 and 500')
    private = json.loads(args.users.read_text())
    online = args.online or max(args.active)
    if not max(args.active) <= online <= 500:
        raise ValueError('Require active <= online <= 500')
    credentials = private['users'][:online]
    if len(credentials) != online:
        raise ValueError('Require distinct credentials for every active identity')
    if len({user['username'] for user in credentials}) != len(credentials):
        raise ValueError('Load identities must be distinct')
    report = {'scope': 'local-single-worker-baseline', 'passed': False,
        'base': args.base, 'onlineUsers': len(credentials), 'stages': [],
        'contract': {'stageSeconds': args.stage_seconds, 'rampSeconds': args.ramp_seconds,
            'cycleSeconds': args.cycle_seconds, 'browserIntervalMs': 300, 'codeBytes': 4096,
            'languagePattern': ['c'] * 4 + ['cpp'] * 4 + ['java', 'python'],
            'loginProvisioning': 'distinct User-Agent per actor; authenticated IDE limits unchanged',
            'latencyScope': 'sync request start through completion response; includes 300ms spacing; excludes Monaco debounce/render',
            'excludedOperations': ['diagnostics', 'definition', 'signatureHelp', 'debug'],
            'thresholdPurpose': 'local diagnostic reference, not production release admission',
            'path': 'real login -> Gateway -> Redis -> worker -> LSP',
            'targetValidRate': .95, 'targetValidP95Seconds': 1.0}, 'cleanup': {}}
    users, semaphore = [], asyncio.Semaphore(8)
    limits = httpx.Limits(max_connections=512, max_keepalive_connections=128)
    async with httpx.AsyncClient(timeout=httpx.Timeout(8, connect=2), limits=limits, trust_env=False) as http:
        async def call(user, path, body):
            response = await http.post(args.base + path, json=body,
                headers={'Cookie': user.get('cookie', ''), 'User-Agent': user['agent']})
            value = response.json()
            if not isinstance(value, dict):
                raise APIError(f'HTTP_{response.status_code}_INVALID_API_ENVELOPE')
            detail = value.get('detail')
            revision = detail.get('serverRevision') if isinstance(detail, dict) else None
            if response.status_code == 409 and type(revision) is int and revision >= 1:
                raise RevisionConflict(revision)
            if response.status_code != 200 or value.get('code') != 0:
                raise APIError(f"HTTP_{response.status_code}_API_{value.get('code')}")
            return value.get('data'), response

        async def open_user(index, credential):
            language = (['c'] * 4 + ['cpp'] * 4 + ['java', 'python'])[index % 10]
            user = {'index': index, 'language': language, 'revision': 1, 'cycle': 0,
                    'agent': f'SDUOJ-IDE-Capacity/20261025 actor-{index}'}
            marked = CASES[language]['complete']; before = marked[:marked.index('|')]
            source = marked.replace('|', '')
            comment = '#' if language == 'python' else '//'
            source += '\n' + comment + 'x' * max(0, 4096 - len(source.encode()) - len(comment) - 1)
            user.update(source=source, line=before.count('\n') + 1,
                        column=len(before.rsplit('\n', 1)[-1]) + 1)
            async with semaphore:
                # Do not rely on the shared httpx cookie jar for actor isolation.
                response = await http.post(args.base + '/api/user/login', json=credential,
                    headers={'Cookie': '', 'User-Agent': user['agent']})
                value = response.json()
                if response.status_code != 200 or value.get('code') != 0:
                    raise RuntimeError(f"Dev load login HTTP_{response.status_code}_API_{value.get('code')}")
                user['cookie'] = '; '.join(f'{k}={v}' for k, v in response.cookies.items())
                if not user['cookie']:
                    raise RuntimeError('Dev load login returned no session cookie')
                await asyncio.sleep(.3)
                session, _ = await call(user, '/api/ps/ide/session', dict(protocolVersion=1,
                    clientSessionKey=uuid.uuid4().hex, language=language,
                    judgeTemplateId=TEMPLATES[language], problemCode=getattr(args, 'problem_code', 'SDUOJ-1000'),
                    context={'type': 0, 'problemCode': getattr(args, 'problem_code', 'SDUOJ-1000')}, code=source))
                revision = response_revision(session, 'create')
                if not isinstance(session.get('sessionId'), str) or not session['sessionId']:
                    raise ReplyDataError('create_invalid_session')
                user.update(session=session['sessionId'], revision=revision)
                users.append(user)
        def save():
            args.output.write_text(json.dumps(report, indent=2) + '\n')
        lifecycle = Lifecycle(getattr(args, 'lifecycle_output', None))
        try:
            opened = await asyncio.gather(*(open_user(i, credential) for i, credential in enumerate(credentials)), return_exceptions=True)
            failures = [type(value).__name__ + ':' + str(value) for value in opened if isinstance(value, BaseException)]
            report['createdSessions'], report['preflightErrors'] = len(users), failures[:20]
            save()
            if failures:
                raise RuntimeError('Not all distinct load actors could be prepared')
            users.sort(key=lambda user: user['index'])
            for stage_index, active in enumerate(args.active, 1):
                rows, started = [], time.monotonic()
                stage = {'activeUsers': active, 'startedAtUnix': time.time(),
                         'complete': False, 'results': rows}
                report['stages'].append(stage)
                lifecycle.emit('stage_started', stageIndex=stage_index, activeUsers=active,
                    onlineUsers=len(credentials), startedAtUnix=stage['startedAtUnix'],
                    startMonotonic=started,
                    plannedSteadyStartAtUnix=stage['startedAtUnix'] + args.ramp_seconds,
                    plannedSteadyStartMonotonic=started + args.ramp_seconds,
                    plannedStageEndMonotonic=started + args.ramp_seconds + args.stage_seconds)
                async def drive(user, offset):
                    await asyncio.sleep(args.ramp_seconds * offset / active)
                    end = started + args.ramp_seconds + args.stage_seconds
                    while time.monotonic() < end:
                        began = time.monotonic(); outcome = 'client_error'; detail = None; phase = 'sync'
                        user['cycle'] += 1
                        suffix = '\n' + ('#' if user['language'] == 'python' else '//') + str(user['cycle'])
                        code = user['source'][:4096 - len(suffix)] + suffix
                        path = '/api/ps/ide/session/' + user['session']
                        try:
                            if user.pop('uncertain', False):
                                phase = 'state'
                                state, _ = await call(user, path + '/state', {})
                                user['revision'] = response_revision(state, 'state')
                                await asyncio.sleep(.3)
                            phase = 'sync'
                            async def sync():
                                value, _ = await call(user, path + '/sync', {'baseRevision': user['revision'],
                                    'revision': user['revision'] + 1, 'code': code})
                                return value
                            try:
                                synced = await sync()
                            except RevisionConflict as conflict:
                                user['revision'] = conflict.revision
                                await asyncio.sleep(.3)
                                synced = await sync()
                            user['revision'] = response_revision(synced, 'sync')
                            await asyncio.sleep(.3)
                            phase = 'completion'
                            result, _ = await call(user, path + '/completion', {'revision': user['revision'],
                                'line': user['line'], 'column': user['column'], 'triggerKind': 'invoked'})
                            outcome = completion_outcome(result, user['revision'], user['language'])
                            if outcome == 'stale':
                                user['uncertain'] = True
                        except Exception as error:
                            outcome = (error.outcome if isinstance(error, ReplyDataError) else
                                'transport_error' if isinstance(error, httpx.TransportError) else
                                'api_error' if isinstance(error, APIError) else
                                'revision_conflict' if isinstance(error, RevisionConflict) else 'client_error')
                            detail = type(error).__name__ + ':' + str(error)[:100]
                            if phase in ('sync', 'state'):
                                user['uncertain'] = True
                        rows.append({'actor': user['index'], 'language': user['language'], 'outcome': outcome,
                                     'seconds': time.monotonic() - began, 'detail': detail, 'requestPhase': phase,
                                     'phase': 'ramp' if began < started + args.ramp_seconds else 'steady'})
                        await asyncio.sleep(max(0, args.cycle_seconds - (time.monotonic() - began)))
                await asyncio.gather(*(drive(user, index) for index, user in enumerate(users[:active])))
                steady = [row for row in rows if row['phase'] == 'steady']
                by_language = {language: summary([row for row in steady if row['language'] == language]) for language in TEMPLATES}
                stage.update(complete=True, seconds=time.monotonic() - started, overall=summary(steady), byLanguage=by_language,
                    offeredCycles=len(rows), steadyCycles=len(steady),
                    nominalSteadyCycles=active * args.stage_seconds / args.cycle_seconds,
                    nominalSteadyInputHz=active / args.cycle_seconds,
                    measuredSteadyInputHz=len(steady) / args.stage_seconds, results=rows)
                metric = stage['overall']
                stage['passed'] = all(value['validRate'] >= .95 and value['validP95'] is not None
                    and value['validP95'] <= 1.0 for value in [metric, *by_language.values()])
                save()
                lifecycle.emit('stage_completed', stageIndex=stage_index, activeUsers=active,
                    onlineUsers=len(credentials), steadySamples=len(steady),
                    diagnosticPassed=stage['passed'])
                print(json.dumps({'active': active, **metric, 'passed': stage['passed']}), flush=True)
            report['passed'] = all(stage['passed'] for stage in report['stages'])
        finally:
            for stage in report['stages']:
                if not stage['complete']:
                    partial = [row for row in stage['results'] if row['phase'] == 'steady']
                    stage.update(passed=False, diagnosticPartial=summary(partial),
                                 incompleteReason='load interrupted before stage completed')
            async def close_user(user):
                async with semaphore:
                    try:
                        value, _ = await call(user, '/api/ps/ide/session/' + user['session'] + '/close', {})
                        return isinstance(value, dict) and value.get('closed') is True
                    except Exception:
                        return False
            closed = await asyncio.gather(*(close_user(user) for user in users))
            report['cleanup'] = {'attempted': len(users), 'closed': sum(closed)}
            save()
            try:
                lifecycle.emit('cleanup_completed', attemptedSessions=len(users),
                    closedSessions=sum(closed), stagesStarted=len(report['stages']),
                    stagesCompleted=sum(bool(stage['complete']) for stage in report['stages']),
                    allStagesComplete=len(report['stages']) == len(args.active) and
                        all(stage['complete'] for stage in report['stages']))
            finally:
                lifecycle.close()
    return report['passed']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:18087')
    parser.add_argument('--problem-code', default='SDUOJ-1000')
    parser.add_argument('--users', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--lifecycle-output', type=Path,
        help='Optional exclusive JSONL phase evidence; never includes actors, cookies or source')
    parser.add_argument('--active', type=int, nargs='+', default=[20, 50, 100])
    parser.add_argument('--online', type=int, default=0, help='Default: maximum active stage; at most 500')
    parser.add_argument('--stage-seconds', type=float, default=75)
    parser.add_argument('--ramp-seconds', type=float, default=20)
    parser.add_argument('--cycle-seconds', type=float, default=2.5)
    args = parser.parse_args()
    raise SystemExit(0 if asyncio.run(run(args)) else 1)


if __name__ == '__main__':
    main()
