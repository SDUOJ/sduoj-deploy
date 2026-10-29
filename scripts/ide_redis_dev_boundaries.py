#!/usr/bin/env python3
"""Local API ownership/recovery checks; no load and no fabricated login."""
import argparse
import json
from pathlib import Path
import time
import uuid

import requests

from ide_redis_dev_acceptance import Client


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--base', default='http://127.0.0.1:8080')
    parser.add_argument('--problem-code', default='SDUOJ-1000')
    parser.add_argument('--user', default='sduoj-deploy/data/dev/ai-integration/test-user.json')
    args = parser.parse_args()
    report = {'passed': False, 'http': [], 'checks': {}}
    from urllib.parse import urlparse
    assert urlparse(args.base).hostname in ('127.0.0.1', 'localhost'), 'Local correctness only'
    client = Client(args.base, args.user, report['http'], args.problem_code)
    live = None
    def create_body(**changes):
        value = dict(commandId=uuid.uuid4().hex, language='python', judgeTemplateId='38',
            code='value=41\nvalue+=1\nprint(value)\n', input='', breakpoints=[2],
            problemCode=args.problem_code, context={'type': 0, 'problemCode': args.problem_code}, replaceExisting=True)
        value.update(changes)
        return value
    try:
        anonymous = requests.Session()
        anonymous.trust_env = False
        response = anonymous.get(client.base+'/api/ps/ide/capabilities',
            headers={'SDUOJUserInfo': '{"userId":1}', 'SDUOJUserInfo-UserId': '1'}, timeout=10)
        assert response.status_code == 401, response.status_code
        report['checks']['forgedIdentityDenied'] = True
        response = client.http.get(client.base+'/api/ps/ide/capabilities', headers={'Origin': 'https://untrusted.invalid'}, timeout=10)
        assert response.status_code == 403, response.status_code
        report['checks']['untrustedOriginDenied'] = True
        # The new handler must leave save/history/code/publicCase in PS.
        response = client.http.post(client.base+'/api/ide/history', json={
            'context': {'type': 0, 'problemCode': args.problem_code}, 'judgeTemplateId': '38'}, timeout=15)
        history = response.json()
        report['http'].append({'path': '/api/ide/history', 'status': response.status_code, 'response': history})
        assert response.status_code == 200 and history.get('code') == 0 and isinstance(history.get('data'), list), history
        report['checks']['legacyHistoryRoutePreserved'] = True
        client.call('/debug/session', create_body(code=''), expected=400)
        client.call('/debug/session', create_body(breakpoints=[-1]), expected=400)
        report['checks']['invalidCreateRejectedAndReservationReleased'] = True
        original = create_body()
        live = client.call('/debug/session', original)
        live, _ = client.wait(live)
        restored = client.call('/debug/session', dict(original, commandId=uuid.uuid4().hex,
            restoreOnly=True, resumeSessionId=live['sessionId'], resumeSessionEpoch=live['sessionEpoch']))
        assert restored['sessionId'] == live['sessionId'] and restored['stopId'] == live['stopId'], restored
        report['checks']['restorePreservesStoppedScene'] = True
        old = live
        live = client.call('/debug/session', create_body())
        live, _ = client.wait(live)
        assert old['sessionId'] != live['sessionId']
        terminal = client.call('/debug/session/'+old['sessionId']+'/events', {'cursor': 0, 'waitSeconds': 0})
        assert terminal['snapshot']['state'] == 'terminated', terminal
        report['checks']['replaceReclaimsOldSceneBeforeCreatingNew'] = True
        client.stop(live)
        live = None
        assert client.call('/debug/session/current', {}) is None
        report['checks']['stopReleasesSingleUserOwnership'] = True
        # Bound all attempts, including rejected ones, in Redis. No LSP task is
        # enqueued by state lookups; this is not a capacity test.
        scene = client.create_lsp('python', 'value=42')
        try:
            responses = [client.call('/session/'+scene['sessionId']+'/state', {}, pace=False) for _ in range(7)]
            assert any(value is None for value in responses), responses
            report['checks']['rateLimitReturnsQuietNull'] = True
        finally:
            client.call('/session/'+scene['sessionId']+'/close', {})
        report['passed'] = True
    finally:
        if live:
            client.stop(live)
        Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps({'passed': report['passed'], 'checks': report['checks']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
