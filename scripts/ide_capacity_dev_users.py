#!/usr/bin/env python3
"""Create distinct local dev-only load identities without email/registration flows."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import secrets
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=500)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.count <= 500 or args.output.exists():
        raise ValueError('Require 1..500 new identities and a new private output file')
    container = 'sduoj-dev-mysql-1'
    info = json.loads(subprocess.check_output(['docker', 'inspect', container], text=True))[0]
    labels = info['Config']['Labels']
    if labels.get('com.docker.compose.project') != 'sduoj-dev' or labels.get('com.docker.compose.service') != 'mysql':
        raise ValueError('Only the existing local dev MySQL is supported')
    command = ['docker', 'exec', '-i', container, 'sh', '-c',
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql --batch --skip-column-names -uroot']
    def sql(statement):
        result = subprocess.run(command, input=statement, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    schemas = sql("SELECT TABLE_SCHEMA FROM information_schema.tables WHERE TABLE_NAME='oj_user';").splitlines()
    if len(schemas) != 1 or not re.fullmatch(r'[A-Za-z0-9_]+', schemas[0]):
        raise ValueError('Cannot identify one local user schema')
    database = schemas[0]
    prefix = 'ic26' + secrets.token_hex(3)
    marker = 'ide-capacity-' + prefix
    rows, users = [], []
    for index in range(args.count):
        username, password, salt = prefix + f'{index:03d}', secrets.token_hex(16), secrets.token_hex(16)
        hashed = hashlib.md5((salt + hashlib.md5(password.encode()).hexdigest()).encode()).hexdigest()
        features = json.dumps({'localDevLoadRun': marker}, separators=(',', ':'))
        rows.append(f"('{username}','{username}','{salt}','{hashed}',NULL,'user','{features}')")
        users.append({'username': username, 'password': password})
    # Fresh random names, INSERT only: never overwrite an existing identity.
    statement = f"START TRANSACTION; INSERT INTO `{database}`.oj_user (u_username,u_nickname,u_salt,u_password,u_email,u_roles,u_features) VALUES " + ','.join(rows) + '; COMMIT;'
    sql(statement)
    count = int(sql(f"SELECT COUNT(*) FROM `{database}`.oj_user WHERE u_username LIKE '{prefix}%';"))
    if count != args.count:
        raise RuntimeError('Dev load identity count mismatch')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.touch(mode=0o600, exist_ok=False)
    args.output.write_text(json.dumps({'marker': marker, 'users': users}, indent=2) + '\n')
    print(json.dumps({'created': count, 'marker': marker, 'privateFile': str(args.output)}))


if __name__ == '__main__':
    main()
