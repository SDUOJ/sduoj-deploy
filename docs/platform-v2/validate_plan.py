#!/usr/bin/env python3
"""Validate planning contracts only; never import application code or execute SQL."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote

import yaml


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f'duplicate YAML key: {key}')
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def validate(data: dict, docs: Path) -> list[str]:
    errors: list[str] = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    require(isinstance(data, dict), 'plan must be a mapping')
    if not isinstance(data, dict):
        return errors
    require(data.get('schema_version') == 2, 'schema_version must be 2')
    meta = data.get('meta', {})
    tasks = data.get('tasks', [])
    require(isinstance(tasks, list) and len(tasks) == 48, 'preserve the 48 supplied task IDs')
    if not isinstance(tasks, list) or not all(isinstance(t, dict) for t in tasks):
        return errors + ['tasks must contain mappings']
    ids = [t.get('id') for t in tasks]
    require(len(set(ids)) == len(ids), 'duplicate task ID')
    expected = {'S1': 5, 'S2': 10, 'S3': 5, 'S4': 10, 'S5': 10, 'S6': 8}
    canonical_ids = {f'{stage}-{number:02d}' for stage, count in expected.items()
                     for number in range(1, count + 1)}
    require(set(ids) == canonical_ids, 'original task ID set changed')
    require(meta.get('expected_tasks_per_stage') == expected, 'stage count manifest changed')
    stages = {x['id'] for x in meta.get('delivery_stages', [])}
    executors = {x['id'] for x in meta.get('executors', [])}
    statuses = {x['id'] for x in meta.get('statuses', [])}
    execution_states = set(meta.get('execution_statuses', []))
    gates = {x['id'] for x in meta.get('approval_gates', [])}
    repos = set(meta.get('repositories', []))
    require(gates == {'AUTH', 'SCHEMA', 'SANDBOX', 'SECRETS'}, 'approval gate registry must be explicit')
    for gate in meta.get('approval_gates', []):
        require(gate.get('status') == 'proposal_required', f'{gate.get("id")}: documentation is not approval')
    by_id = {t['id']: t for t in tasks}
    for task in tasks:
        key = task['id']
        require(task.get('stage') in stages and key.startswith(task.get('stage', '') + '-'), f'{key}: invalid stage')
        require(task.get('executor') in executors, f'{key}: invalid executor')
        require(task.get('status') in statuses, f'{key}: invalid maturity status')
        require(task.get('execution_status') in execution_states, f'{key}: invalid execution status')
        require(task.get('priority') in {'P0', 'P1', 'P2', 'P3'}, f'{key}: invalid priority')
        require(bool(task.get('repositories')) and set(task.get('repositories', [])) <= repos, f'{key}: invalid repository')
        require(set(task.get('approval_gates', [])) <= gates, f'{key}: invalid approval gate')
        deps = task.get('depends_on')
        require(isinstance(deps, list), f'{key}: missing dependency list')
        if isinstance(deps, list):
            require(set(deps) <= canonical_ids and key not in deps, f'{key}: invalid dependency')
        acceptance = task.get('acceptance')
        require(isinstance(acceptance, list) and len(acceptance) >= 3 and
                all(isinstance(x, str) and x.strip() for x in acceptance), f'{key}: need positive/negative/evidence acceptance')
        require(isinstance(task.get('rollback'), str) and bool(task['rollback'].strip()), f'{key}: missing rollback')
        verification = task.get('verification', {})
        require(set(verification.get('required', [])) >= {'positive', 'negative', 'failure_recovery'}, f'{key}: missing verification dimensions')
        if task.get('execution_status') == 'done':
            require(bool(verification.get('evidence')), f'{key}: cannot claim done without evidence')
        require(bool(task.get('doc_refs')), f'{key}: missing document references')
        for ref in task.get('doc_refs', []):
            require((docs / ref).is_file(), f'{key}: missing doc {ref}')

    # A topological audit of task dependencies; release gates are not start dependencies.
    visiting, visited = set(), set()

    def visit(key):
        if key in visiting:
            errors.append(f'dependency cycle at {key}')
            return
        if key in visited:
            return
        visiting.add(key)
        for dep in by_id[key].get('depends_on', []):
            if dep in by_id:
                visit(dep)
        visiting.remove(key)
        visited.add(key)

    for key in by_id:
        visit(key)
    blockers = data.get('blockers', [])
    require(len({b.get('id') for b in blockers}) == len(blockers), 'duplicate blocker ID')
    for blocker in blockers:
        require(bool(blocker.get('until_tasks')) and set(blocker['until_tasks']) <= canonical_ids,
                f'{blocker.get("id")}: invalid release evidence tasks')
        require(bool(blocker.get('blocks_release_of')) and set(blocker['blocks_release_of']) <= canonical_ids,
                f'{blocker.get("id")}: invalid release scope')
        require(bool(blocker.get('capability_scope')), f'{blocker.get("id")}: ambiguous capability scope')

    require('AUTH' in by_id['S1-02'].get('approval_gates', []), 'native association fix needs AUTH proposal')
    require('SANDBOX' in by_id['S3-03'].get('approval_gates', []), 'runtime changes need SANDBOX proposal')
    require('S2-07' not in by_id['S2-06'].get('depends_on', []), 'Codex abstraction must not await DSH')
    trace = meta.get('requirements_trace', {})
    require(trace.get('state') == 'original_text_unavailable', 'do not invent validation of the unavailable 35 requirements')

    sql_text = ''
    for doc in sorted(docs.glob('*.md')):
        content = doc.read_text(encoding='utf-8')
        for target in re.findall(r'\]\(([^)]+)\)', content):
            target = target.strip().strip('<>')
            if target.startswith(('https://', 'http://', '#', 'mailto:')):
                continue
            path_part = unquote(target.split('#', 1)[0])
            resolved = (doc.parent / path_part).resolve()
            require(resolved.is_relative_to(docs.resolve()), f'{doc.name}: link leaves plan directory')
            require(resolved.exists(), f'{doc.name}: broken link {path_part}')
        for ref in re.findall(r'\bS[1-6]-\d{2}\b', content):
            require(ref in canonical_ids, f'{doc.name}: unknown task reference {ref}')
        for block in re.findall(r'```json\s*\n(.*?)```', content, re.S):
            try:
                json.loads(block)
            except json.JSONDecodeError:
                errors.append(f'{doc.name}: invalid JSON example')
        for block in re.findall(r'```sql\s*\n(.*?)```', content, re.S):
            if re.search(r'\b(?:CREATE\s+TABLE|ALTER\s+TABLE)\b', block, re.I):
                require(doc.name == '06-数据库变更汇总.md', f'{doc.name}: duplicated DDL authority')
            require(not re.search(r'\b(?:DROP\s+TABLE|TRUNCATE\s+TABLE)\b', block, re.I), f'{doc.name}: destructive SQL in proposal')
            if doc.name == '06-数据库变更汇总.md':
                sql_text += block + '\n'
        # Report only filename, never print any potential secret.
        require(not re.search(r'\bsk-[A-Za-z0-9_-]{12,}\b', content), f'{doc.name}: possible credential string')
        require(not re.search(r'\b10\.102\.\d+\.\d+\b', content), f'{doc.name}: production address should stay in restricted operational records')
    create = re.findall(r'CREATE\s+TABLE\s+(\w+)', sql_text, re.I)
    require(len(create) == 17 and len(set(create)) == 17, 'DDL must contain 17 distinct new tables')
    inventory = meta.get('sql_inventory', {})
    require(set(create) == set(inventory.get('create_tables', [])), 'DDL/table inventory mismatch')
    altered = {name: len(re.findall(r'ADD\s+COLUMN', body, re.I))
               for name, body in re.findall(r'ALTER\s+TABLE\s+(\w+)(.*?);', sql_text, re.I | re.S)}
    require(altered == inventory.get('alter_columns'), 'ALTER column inventory mismatch')
    require(len(altered) == 4 and sum(altered.values()) == 11, 'expect 4 existing tables / 11 added columns')
    require('default_owner_id' in sql_text and 'UNIQUE KEY uq_port_default (default_owner_id)' in sql_text,
            'missing nullable active-default uniqueness')
    require(not re.search(r'UNIQUE[^\n]+\(owner_id,\s*is_default,\s*status\)', sql_text), 'default index blocks multiple non-default ports')
    require(not re.search(r'\btrial_token\s+VARCHAR', sql_text, re.I), 'raw trial token cannot be persisted')
    require('show_code TINYINT NOT NULL DEFAULT 0' in sql_text and 'visible TINYINT NOT NULL DEFAULT 0' in sql_text,
            'student publication/code must default closed')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--docs', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    plan = args.plan or args.docs / 'task-list.yaml'
    try:
        data = yaml.load(plan.read_text(encoding='utf-8'), Loader=UniqueKeyLoader)
        errors = validate(data, args.docs)
    except (OSError, ValueError, yaml.YAMLError, KeyError, TypeError) as exc:
        # Errors intentionally omit document contents and credential-like values.
        print(f'FAIL: invalid plan structure ({type(exc).__name__})', file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print('FAIL: ' + error, file=sys.stderr)
        return 1
    print(json.dumps({'result': 'PASS', 'tasks': len(data['tasks']), 'stages': 6,
                      'blockers': len(data['blockers']), 'new_tables': 17,
                      'altered_tables': 4, 'added_columns': 11,
                      'scope': 'static planning contracts; no SQL or production execution'}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
