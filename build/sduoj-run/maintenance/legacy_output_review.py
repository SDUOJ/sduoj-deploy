"""Read-only legacy survey and individually reviewed, content-bound clearances.

Import does not grant authorization. Operators must review each file's provenance and
external consumers; automation may only test clearances for its own disposable fixtures.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re

TABLE = 'oj_legacy_output_clearance'
NAME = re.compile(r'(?:auto-([0-9]+)|([a-f0-9]+))-([0-9]+)\.out')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def scope(stores):
    # Configured database roles + inventory, without credentials or business values.
    return digest([{'roles': sorted(s.schemas.items()), 'tables': sorted(s.tables)} for s in stores])


def identity(meta):
    return {key: meta[key] for key in ['f_id','u_id','f_size','f_name','f_md5','f_features','f_is_deleted']} | {
        'createdAt': meta['f_gmt_create'].isoformat(timespec='milliseconds')}


def proof(stores, fid, task, index):
    source = next(s for s in stores if 'problem' in s.schemas)
    table = source.table('problem','oj_run_legacy_output')
    # Persisted before report deletion in the same expiry transaction.
    return bool(source.query(f'SELECT 1 FROM {table} WHERE f_id=%s AND task_id=%s AND case_index=%s', (fid,task,index)))


def content_sha(retention, root, item):
    with retention.parent_fd(root,item['f_id']) as (fd,name):
        retention.verify_physical(fd,name,item)
        filefd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
        with os.fdopen(filefd,'rb') as stream:
            return hashlib.sha256(stream.read(65537)).hexdigest()


def survey(retention,stores,filesys,root,now,days,limit,after=0):
    metadata=filesys.table('filesys','oj_file')
    allocations=filesys.table('filesys','oj_shared_task_output')
    # Existing allocations are handled by the ordinary collector, not reclassified as legacy.
    # Include retained ledger IDs even when CAS dedup returned an ordinary, non-generated name.
    source=next(s for s in stores if 'problem' in s.schemas)
    ledger=source.table('problem','oj_run_legacy_output')
    ids=[r['f_id'] for r in source.query(f'SELECT DISTINCT f_id FROM {ledger} WHERE f_id>%s ORDER BY f_id LIMIT %s',(after,limit))]
    extra=' OR f_id IN ('+','.join(['%s']*len(ids))+')' if ids else ''
    rows=filesys.query(f"SELECT * FROM {metadata} WHERE f_is_deleted=0 AND f_id>%s AND "
                       f"(f_name REGEXP '^(auto-[0-9]+|[a-f0-9]+)-[0-9]+[.]out$'{extra}) "
                       'ORDER BY f_id LIMIT %s',(after,*ids,limit))
    result=[]
    for meta in rows:
        fid=meta['f_id'];row={'fileId':str(fid),'identity':identity(meta),'holds':[],'sha256':None,'taskId':None,'index':None}
        try:
            known=filesys.query(f'SELECT origin FROM {allocations} WHERE f_id=%s',(fid,))
            if known:
                row['holds'].append('already-registered:'+known[0]['origin']);result.append(row);continue
            match=NAME.fullmatch(meta['f_name'])
            if not match:
                row['holds'].append('deduplicated-ordinary-name');result.append(row);continue
            task=int(match[1],10) if match[1] is not None else int(match[2],16)
            index=int(match[3]);row.update(taskId=str(task),index=index)
            if not 0<=index<=19 or task<=0 or fid<=0 or not 0<=meta['f_size']<=65536:
                row['holds'].append('invalid-generated-shape');result.append(row);continue
            if not proof(stores,fid,task,index):row['holds'].append('missing-report-ledger')
            if meta['f_gmt_create']>now-dt.timedelta(days=days):row['holds'].append('recent')
            claims=filesys.table('filesys','oj_file_asset_claim')
            if filesys.query(f'SELECT 1 FROM {claims} WHERE f_id=%s',(fid,)):row['holds'].append('ordinary-asset-claim')
            for s in stores:
                if s.source_exists(task):row['holds'].append('source-retained')
                reference=s.refs(fid)
                if reference:row['holds'].append(reference)
            item={'f_id':fid,'byte_size':meta['f_size'],'md5':meta['f_md5']}
            row['sha256']=content_sha(retention,root,item)
            # Missing pre-upgrade reuse/download history always requires individual review.
            row['requiresExclusiveOwnershipReview']=True
            row['requiresExternalConsumerReview']=True
        except Exception as error:
            row['holds'].append('survey-error:'+type(error).__name__)
        result.append(row)
    payload={'version':1,'databaseScope':scope(stores),'generatedAt':now.isoformat(timespec='milliseconds'),
             'minimumAgeDays':days,'nextCursor':result[-1]['fileId'] if len(rows)==limit else '0','items':result}
    return {'snapshot':payload,'snapshotSha256':digest(payload)}


def write_report(path,report):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    lines=['# 疑似历史共享任务输出调查','',f"快照 SHA256：`{report['snapshotSha256']}`。只读调查，未登记清理许可、未删除文件。",'',
           '旧版本没有完整复用／外部下载凭据。文件名和无数据库引用均不能代替来源与外部消费者审核。', '',
           '| 文件ID | 文件名推测任务ID / index | 当前保护原因 | 是否可进入人工审核 |','|---|---|---|---|']
    for item in report['snapshot']['items']:
        holds=item['holds'];lines.append(f"| {item['fileId']} | {item['taskId']} / {item['index']} | {', '.join(holds) or '未发现已知保护；仍需审核独占来源和外部消费者'} | {'否' if holds else '是'} |")
    lines+=['',f"下一批游标：`{report['snapshot']['nextCursor']}`。完整身份、内容摘要及数据库范围见同名JSON。",'',
            '审核文件另存为JSON，包含本快照、snapshotSha256与逐文件approvals。每项须包含fileId、reviewedBy、reason、verifiedExclusiveTaskOutput=true、verifiedNoExternalConsumers=true。工具不会自动生成真实业务文件的批准项。']
    path.write_text('\n'.join(lines)+'\n')


def install(retention,stores,filesys,root,review,now,days,reason):
    snapshot=review['snapshot'];snapshot_hash=review['snapshotSha256']
    if snapshot.get('version')!=1 or digest(snapshot)!=snapshot_hash or snapshot['databaseScope']!=scope(stores):
        raise ValueError('Legacy review snapshot or database scope differs')
    if snapshot['minimumAgeDays']!=days:
        raise ValueError('Legacy review policy differs')
    by_id={r['fileId']:r for r in snapshot['items']};seen=set();verified=[]
    approvals=review.get('approvals',[])
    if not 1<=len(approvals)<=100:raise ValueError('Legacy approvals must contain 1..100 items')
    metadata=filesys.table('filesys','oj_file');claims=filesys.table('filesys','oj_file_asset_claim')
    clearances=filesys.table('filesys',TABLE);allocations=filesys.table('filesys','oj_shared_task_output')
    for approval in approvals:
        fid_text=approval['fileId'];fid=int(fid_text)
        if fid_text in seen:raise ValueError('Duplicate legacy approval')
        seen.add(fid_text);item=by_id[fid_text]
        if item['holds'] or not item['sha256']:raise ValueError('Protected survey entry cannot be approved')
        reviewer=approval.get('reviewedBy','');why=approval.get('reason','')
        if not isinstance(reviewer,str) or not 1<=len(reviewer)<=100 or not isinstance(why,str) or not 1<=len(why)<=200:
            raise ValueError('Legacy reviewer and explanation are required')
        if approval.get('verifiedExclusiveTaskOutput') is not True or approval.get('verifiedNoExternalConsumers') is not True:
            raise ValueError('Exclusive origin and external consumers were not reviewed')
        task=int(item['taskId']);index=item['index']
        rows=filesys.query(f'SELECT * FROM {metadata} WHERE f_id=%s',(fid,))
        if len(rows)!=1 or identity(rows[0])!=item['identity']:raise ValueError('Legacy metadata changed after review')
        meta=rows[0]
        if not proof(stores,fid,task,index) or meta['f_gmt_create']>now-dt.timedelta(days=days):raise ValueError('Legacy provenance or age changed')
        if filesys.query(f'SELECT 1 FROM {claims} WHERE f_id=%s',(fid,)):raise ValueError('Legacy ordinary claim exists')
        for s in stores:
            if s.source_exists(task) or s.refs(fid):raise ValueError('Legacy source or reference exists')
        candidate={'f_id':fid,'byte_size':meta['f_size'],'md5':meta['f_md5']}
        if content_sha(retention,root,candidate)!=item['sha256']:raise ValueError('Legacy content changed after review')
        if filesys.query(f'SELECT 1 FROM {allocations} WHERE f_id=%s OR source_file_id=%s',(fid,fid)):
            raise ValueError('Legacy allocation already registered; use ordinary collector for recovery')
        verified.append((approval,item,meta))
    # Validate the complete selected set before registering any clearance. No file writes/deletes.
    for approval,item,meta in verified:
        fid=meta['f_id'];task=int(item['taskId']);index=item['index']
        review_hash=digest({'snapshotSha256':snapshot_hash,'approval':approval})
        filesys.update(f'INSERT INTO {clearances}(f_id,task_id,case_index,expected_name,expected_features,byte_size,md5,sha256,user_id,snapshot_sha256,review_sha256,reviewed_by,review_reason,reviewed_at) '
                       'VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE f_id=f_id',
                       (fid,task,index,meta['f_name'],meta['f_features'],meta['f_size'],meta['f_md5'],item['sha256'],meta['u_id'],snapshot_hash,review_hash,approval['reviewedBy'],approval['reason'],now))
        stored=filesys.query(f'SELECT review_sha256 FROM {clearances} WHERE f_id=%s',(fid,))
        if stored[0]['review_sha256']!=review_hash:raise ValueError('Conflicting existing legacy review')
        filesys.update(f'INSERT INTO {allocations}(source_file_id,f_id,task_id,case_index,expected_name,byte_size,md5,user_id,origin,created_at) '
                       "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'LEGACY',%s)",
                       (fid,fid,task,index,meta['f_name'],meta['f_size'],meta['f_md5'],meta['u_id'],meta['f_gmt_create']))
    return [str(meta['f_id']) for _,_,meta in verified]


def clearance(filesys,candidate):
    schema=filesys.schemas['filesys']
    if (schema,TABLE) not in filesys.tables:return None
    rows=filesys.query(f'SELECT * FROM {filesys.table("filesys",TABLE)} WHERE f_id=%s',(candidate['f_id'],))
    if len(rows)!=1:return None
    row=rows[0]
    pairs={'task_id':'task_id','case_index':'case_index','expected_name':'expected_name','byte_size':'byte_size','md5':'md5','user_id':'user_id'}
    if any(row[a]!=candidate[b] for a,b in pairs.items()):return None
    if not row['reviewed_by'] or not row['review_reason'] or any(not re.fullmatch('[0-9a-f]{64}',row[key]) for key in ['sha256','snapshot_sha256','review_sha256']):return None
    return row
