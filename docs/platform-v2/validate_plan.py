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


def validate_catalog(catalog: dict, docs: Path) -> list[str]:
    """Check the design inventory; this never loads SDKs or installs components."""
    errors: list[str] = []

    def require(condition, message):
        if not condition:
            errors.append('catalog: ' + message)

    if not isinstance(catalog, dict):
        return ['catalog: expected mapping']
    expected = {'content.review', 'management.assistant', 'document.extract',
                'document.translate', 'question.assistant', 'authoring.programming',
                'authoring.objective', 'authoring.subjective', 'grading.subjective',
                'plagiarism.explain', 'ide.tutor', 'course.assistant',
                'interview.assistant', 'exam.assistant'}
    require(catalog.get('schema_version') == 1 and catalog.get('kind') == 'design_catalog',
            'must remain an explicit design catalog')
    require(catalog.get('engine') == 'openhands-sdk' and
            catalog.get('execution_owner') == 'auto_task.worker' and
            catalog.get('task_type') == 'agent.run', 'wrong engine or execution owner')
    require(catalog.get('default_enabled') is False, 'new components must default closed')
    policy = catalog.get('runtime_policy', {})
    required_policy = {
        'global_setting_id': 'agent_components', 'setting_store': 'AiSetting',
        'unknown_component': 'deny', 'unknown_version': 'deny', 'unknown_action': 'deny',
        'missing_config': 'disabled', 'dynamic_code_install': False,
        'raw_provider_key_in_agent': False, 'legacy_ingress_gating_required': True,
        'sdk_process': 'worker_owned_separate_python_runtime', 'ipc': 'bounded_schema_json',
        'generation_tuple': ['global', 'component', 'action'],
        'dependency_generations': 'freeze_transitive_dependencies_and_allowed_cross_component_targets',
        'approval_lifecycle': 'durable_candidate_independent_of_active_worker_lease',
        'host_config_autoload': False,
        'tools_projection': 'current_action_and_profile_allowlist_with_server_gate',
    }
    for key, value in required_policy.items():
        require(key in policy and type(policy[key]) is type(value) and policy[key] == value,
                f'unsafe or absent runtime policy: {key}')
    components = catalog.get('components', [])
    if not isinstance(components, list) or not all(isinstance(c, dict) for c in components):
        return errors + ['catalog: components must contain mappings']
    ids = [c.get('id') for c in components]
    require(len(set(ids)) == len(ids) and set(ids) == expected, '14 component IDs must be unique and complete')
    if len(set(ids)) != len(ids) or set(ids) != expected:
        return errors
    by_id = {c['id']: c for c in components}
    profiles = {'business_tools', 'sandbox_tools'}
    aliases = {}
    for component in components:
        key = component['id']
        require(component.get('version') == 1 and component.get('default_enabled') is False,
                f'{key}: invalid version or open default')
        require(component.get('implementation_status') == 'not_implemented',
                f'{key}: this inventory is not implementation evidence')
        require(component.get('requires_endpoint') is True, f'{key}: model endpoint must be explicit')
        require(component.get('execution_profile') in profiles, f'{key}: unknown execution profile')
        actions = component.get('actions', [])
        require(bool(actions) and len(set(actions)) == len(actions), f'{key}: missing or duplicate actions')
        require(bool(component.get('tools')) and bool(component.get('resource_kinds')),
                f'{key}: missing tool/resource bounds')
        for action, profile in component.get('action_profiles', {}).items():
            require(action in actions and profile in profiles, f'{key}: invalid action/profile')
        for action, capabilities in component.get('action_capabilities', {}).items():
            require(action in actions and bool(capabilities), f'{key}: invalid per-action capabilities')
        deps = component.get('dependencies', [])
        require(isinstance(deps, list) and set(deps) <= expected and key not in deps and
                len(set(deps)) == len(deps), f'{key}: invalid dependencies')
        if key not in {'content.review', 'management.assistant'}:
            require('content.review' in deps, f'{key}: missing content review gate')
        require(component.get('source_authorization') == 'fresh_original_resource_permission',
                f'{key}: missing original resource authorization')
        require(component.get('visibility') in {'internal_service', 'business_entry'},
                f'{key}: invalid visibility')
        for ref in component.get('doc_refs', []):
            require((docs / ref).is_file(), f'{key}: broken document reference')
        for binding in component.get('legacy_bindings', []):
            alias, selector = binding.get('task_type'), binding.get('selector')
            require(alias not in {'summary_report', 'ide.execute', 'exam.plan', 'course.index'},
                    f'{key}: mixed/deterministic task cannot be an entire AI binding')
            require(selector in {'explicit_registered_action', 'server_resolved_question_kind',
                                 'optional_ai_segment_only'}, f'{key}: unbounded legacy selector')
            if alias in {'plagiarism.scan', 'code_similarity'}:
                require(key == 'plagiarism.explain' and selector == 'optional_ai_segment_only',
                        'deterministic scanning must remain independent')
            aliases.setdefault(alias, []).append((key, selector))
    for alias, bindings in aliases.items():
        require(len(bindings) == 1 or (alias == 'authoring.generate' and len(bindings) == 3 and
                all(selector == 'server_resolved_question_kind' for _, selector in bindings)),
                'ambiguous legacy task binding')
    require(set(aliases) == {'management.turn', 'question.extract', 'question.solve', 'question.verify',
                            'question.chat', 'authoring.generate', 'subjective.grade', 'subjective_review',
                            'plagiarism.scan', 'code_similarity', 'ide.tutor', 'course.ask', 'interview.advance'},
            'missing reviewed legacy AI entry point')
    visiting, visited = set(), set()

    def visit(key):
        if key in visiting:
            errors.append(f'catalog: dependency cycle at {key}')
            return
        if key in visited:
            return
        visiting.add(key)
        for dep in by_id[key].get('dependencies', []):
            if dep in by_id:
                visit(dep)
        visiting.remove(key)
        visited.add(key)

    for key in by_id:
        visit(key)
    extract = by_id['document.extract']
    require('vision_ocr' in extract['actions'] and
            'vision' in extract.get('action_capabilities', {}).get('vision_ocr', []) and
            'course.index_visual_pdf_ctx.ask' in extract.get('legacy_hooks', []),
            'course indexing visual OCR must not bypass endpoint/capability gates')
    require(by_id['question.assistant'].get('action_profiles', {}).get('verify_execute') == 'sandbox_tools',
            'question verification execution requires the sandbox action')
    require(all(by_id['authoring.programming'].get('action_profiles', {}).get(action) == 'sandbox_tools'
                for action in ('solution', 'tests', 'validator', 'checker')),
            'programming execution actions require the sandbox profile')
    require(by_id['content.review'].get('visibility') == 'internal_service' and
            {'document', 'grading', 'plagiarism', 'ide', 'course', 'interview'} <=
            set(by_id['content.review'].get('resource_kinds', [])), 'incomplete internal moderation coverage')
    required_operations = {'formal_submission', 'ide_run_and_cloud_save', 'plagiarism_scan',
                           'document_parse_and_course_index', 'exam_accounts_materials_invigilation',
                           'task_history_cancel_and_reconciliation', 'manual_question_management'}
    require({n.get('id') for n in catalog.get('non_agent_operations', [])} == required_operations,
            'deterministic/manual operations must remain available under original permissions')
    return errors


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
    if set(ids) != canonical_ids or len(set(ids)) != len(ids):
        return errors
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
        for capability, capability_deps in task.get('capability_dependencies', {}).items():
            require(bool(capability) and bool(capability_deps) and
                    set(capability_deps) <= canonical_ids and key not in capability_deps,
                    f'{key}: invalid optional capability dependencies')
        acceptance = task.get('acceptance')
        require(isinstance(acceptance, list) and len(acceptance) >= 3 and
                all(isinstance(x, str) and x.strip() for x in acceptance), f'{key}: need positive/negative/evidence acceptance')
        require(isinstance(task.get('rollback'), str) and bool(task['rollback'].strip()), f'{key}: missing rollback')
        verification = task.get('verification', {})
        require(set(verification.get('required', [])) >= {'positive', 'negative', 'failure_recovery'}, f'{key}: missing verification dimensions')
        if task.get('execution_status') == 'done':
            evidence = verification.get('evidence', [])
            require(isinstance(evidence, list) and bool(evidence), f'{key}: cannot claim done without evidence')
            covered = set()
            for item in evidence if isinstance(evidence, list) else []:
                valid = (isinstance(item, dict) and item.get('kind') in verification.get('required', []) and
                         isinstance(item.get('artifact'), str) and bool(item['artifact'].strip()) and
                         isinstance(item.get('sha256'), str) and bool(re.fullmatch(r'[0-9a-f]{64}', item['sha256'])) and
                         isinstance(item.get('source_commit'), str) and bool(re.fullmatch(r'[0-9a-f]{40}', item['source_commit'])) and
                         isinstance(item.get('tested_at'), str) and
                         bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', item['tested_at'])) and
                         item.get('result') == 'pass')
                require(valid, f'{key}: invalid evidence record')
                if valid:
                    covered.add(item['kind'])
            require(set(verification.get('required', [])) <= covered, f'{key}: incomplete evidence dimensions')
            require(all(by_id[d].get('execution_status') in {'done', 'not_applicable'} for d in deps if d in by_id),
                    f'{key}: unfinished prerequisite')
            approvals = verification.get('approval_refs', {})
            require(isinstance(approvals, dict) and all(isinstance(approvals.get(g), str) and approvals[g].strip()
                    for g in task.get('approval_gates', [])), f'{key}: missing recorded approval references')
        if task.get('execution_status') == 'not_applicable':
            require(bool(task.get('not_applicable_reason')), f'{key}: missing non-applicability reason')
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
    require('S2-07' not in by_id['S2-06'].get('depends_on', []), 'SDK foundation must not await feature UI')
    require({'AUTH', 'SANDBOX', 'SECRETS'} <= set(by_id['S2-06'].get('approval_gates', [])),
            'SDK integration needs concrete execution and credential proposals')
    require('AUTH' in by_id['S2-07'].get('approval_gates', []), 'feature governance needs AUTH proposal')
    require('S2-06' not in by_id['S2-07'].get('depends_on', []),
            'static governance can be developed before SDK execution')
    for key in ('S4-04', 'S4-05', 'S4-07'):
        require('S2-07' not in by_id[key].get('depends_on', []) and
                'S2-07' in by_id[key].get('capability_dependencies', {}).get('ai_actions', []),
                f'{key}: optional AI gating must not block manual/deterministic development')
    architecture = meta.get('architecture_decision', {})
    require(architecture.get('engine') == 'openhands-sdk' and
            architecture.get('execution_owner') == 'auto_task.worker' and
            architecture.get('platform_owner') == 'sduoj-autolab' and
            architecture.get('scope') == 'design_only_not_runtime_implementation',
            'missing current AutoLab/OpenHands architecture decision')
    require(architecture.get('document') == '10-OpenHands与Agent组件.md' and
            architecture.get('component_catalog') == 'agent-components.yaml', 'wrong architecture references')
    catalog = yaml.load((docs / 'agent-components.yaml').read_text(encoding='utf-8'), Loader=UniqueKeyLoader)
    errors.extend(validate_catalog(catalog, docs))
    packages = data.get('implementation_packages', [])
    require(len(packages) == 6 and {p.get('id') for p in packages} ==
            {f'OH-{n:02}' for n in range(1, 7)}, 'need six implementation packages, not additional stage tasks')
    for package in packages:
        require(bool(package.get('task_refs')) and set(package['task_refs']) <= canonical_ids,
                'invalid OpenHands package task reference')
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
    require(inventory.get('inventory_scope') == 'reviewed_draft_not_required_initial_migrations' and
            set(inventory.get('deferred_agent_tables', [])) ==
            {'auto_agent_node', 'auto_agent_session', 'auto_agent_execution', 'auto_agent_tool_audit'},
            'deferred agent tables must not become mandatory initial migrations')
    require(set(create) == set(inventory.get('create_tables', [])), 'DDL/table inventory mismatch')
    altered = {}
    for name, body in re.findall(r'ALTER\s+TABLE\s+(\w+)(.*?);', sql_text, re.I | re.S):
        altered[name] = altered.get(name, 0) + len(re.findall(r'ADD\s+COLUMN', body, re.I))
    require(altered == inventory.get('alter_columns'), 'ALTER column inventory mismatch')
    require(len(altered) == 4 and sum(altered.values()) == 11, 'expect 4 existing tables / 11 added columns')
    ddl_doc = '06-数据库变更汇总.md'
    owners = dict(re.findall(r'###\s+(\w+)（[^\n]*?\b(S[1-6]-\d{2})）', (docs / ddl_doc).read_text(encoding='utf-8')))
    require(set(owners) == set(create), 'new table task ownership missing')
    alter_owners = inventory.get('alter_task_owners', {})
    require(set(alter_owners) == set(altered), 'ALTER task ownership missing')
    for table, task_id in list(owners.items()) + list(alter_owners.items()):
        task = by_id.get(task_id, {})
        require('SCHEMA' in task.get('approval_gates', []), f'{table}: owning task needs SCHEMA')
        require('sduoj-deploy' in task.get('repositories', []) and ddl_doc in task.get('doc_refs', []),
                f'{table}: owning task needs migration repository and DDL reference')
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
                      'components': 14, 'implementation_packages': 6,
                      'blockers': len(data['blockers']), 'draft_new_tables': 17,
                      'altered_tables': 4, 'added_columns': 11,
                      'scope': 'static planning contracts; no SQL or production execution'}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
