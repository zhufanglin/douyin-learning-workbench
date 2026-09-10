"""Preview and atomically delete local records, keeping shared snapshots intact."""
import hashlib
import json
from .store import now


def delete_records(store, kind, source, record_id, token=None):
    return delete_batch(store, [dict(kind=kind, source=source, id=record_id)], token)


def delete_batch(store, records_to_delete, token=None):
    keys = sorted({(r['kind'], r['source'], r['id']) for r in records_to_delete})
    if not keys or len({k[0] for k in keys}) != 1:
        raise ValueError('一次请选择同一板块的记录。')
    kind = keys[0][0]
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE' if token is not None else 'BEGIN')
        if kind == 'logs':
            rows = []
            for record_id in sorted({k[2] for k in keys}):
                row = db.execute("SELECT l.*,t.status FROM logs l JOIN tasks t ON t.id=l.task_id WHERE l.id=? AND t.source IN ('live','import')", (record_id,)).fetchone()
                if row is None:
                    raise KeyError(record_id)
                if row['status'] in ('running','queued'):
                    raise ValueError('相关任务正在执行，请先暂停后删除日志。')
                rows.append(dict(row))
            fingerprint = hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()
            summary = dict(token=fingerprint, counts=dict(logs=len(rows)), affected_tasks=len({r['task_id'] for r in rows}), selected_count=len(rows))
            if token is None:
                return summary
            if token != fingerprint:
                raise ValueError('日志状态已变化，请重新核对。')
            db.executemany('DELETE FROM logs WHERE id=?', [(r['id'],) for r in rows])
            return dict(summary,status='deleted',deleted_task_ids=[])
        tasks = [dict(r) for r in db.execute('SELECT rowid AS seq,* FROM tasks ORDER BY created_at, rowid')]
        snapshots = [dict(r) for r in db.execute('SELECT * FROM task_entities ORDER BY task_id,kind,source,entity_id')]
        entities = [dict(r) for r in db.execute('SELECT * FROM entities ORDER BY kind,source,id')]
        task_map = {t['id']:t for t in tasks}
        entity_key = lambda r: (r['kind'], r['source'], r.get('entity_id', r.get('id')))
        deleted_tasks = {k[2] for k in keys} if kind == 'tasks' else set()
        existing_keys = {entity_key(e) for e in entities}
        for key in keys:
            if kind == 'tasks':
                if key[2] not in task_map or task_map[key[2]]['source'] != key[1]:
                    raise KeyError(key[2])
            elif key not in existing_keys:
                raise KeyError(key[2])
        targets = set(keys) if kind != 'tasks' else set()
        selected_ids = {(k[1],k[2]) for k in keys}
        # Include historical payloads, since parent/user relationships are task-specific.
        records = [(entity_key(r), json.loads(r['payload'])) for r in snapshots + entities]
        if kind == 'videos':
            targets.update(k for k,p in records if k[0]=='comments' and (k[1],p.get('video_id')) in selected_ids)
        if kind == 'users':
            targets.update(k for k,p in records if k[0]=='comments' and (k[1],p.get('user_id')) in selected_ids)
        if kind in ('comments','users','videos'):
            while True:
                children = {k for k,p in records if k[0]=='comments' and (k[0],k[1],p.get('parent_comment_id')) in targets}
                if children <= targets:
                    break
                targets.update(children)
        removed = [r for r in snapshots if r['task_id'] in deleted_tasks or entity_key(r) in targets]
        remaining = [r for r in snapshots if r['task_id'] not in deleted_tasks and entity_key(r) not in targets]
        removed_comment_users = {(r['source'],json.loads(r['payload']).get('user_id')) for r in removed if r['kind']=='comments'}
        remaining_comment_users = {(r['source'],json.loads(r['payload']).get('user_id')) for r in remaining if r['kind']=='comments'}
        orphan_users = {('users',s,u) for s,u in removed_comment_users - remaining_comment_users if u}
        targets.update(orphan_users)
        removed = [r for r in snapshots if r['task_id'] in deleted_tasks or entity_key(r) in targets]
        remaining = [r for r in snapshots if r['task_id'] not in deleted_tasks and entity_key(r) not in targets]
        affected = deleted_tasks | {r['task_id'] for r in removed}
        if any(task_map[t]['status'] in ('running','queued') for t in affected):
            raise ValueError('相关任务正在执行，请先暂停并等待状态更新后再删除。')
        changed_keys = targets | {entity_key(r) for r in removed}
        latest = {}
        for r in sorted(remaining, key=lambda r:(task_map[r['task_id']]['created_at'],task_map[r['task_id']]['seq'])):
            if entity_key(r) in changed_keys:
                latest[entity_key(r)] = r['payload']
        gone = changed_keys - latest.keys()
        counts = dict(tasks=len(deleted_tasks), **{k:sum(1 for e in entities if e['kind']==k and entity_key(e) in gone) for k in ('videos','users','comments')})
        removed_logs = [dict(r) for t in sorted(deleted_tasks) for r in db.execute('SELECT * FROM logs WHERE task_id=? ORDER BY id', (t,))]
        counts['logs'] = len(removed_logs)
        fingerprint = hashlib.sha256(json.dumps([keys,tasks,snapshots,entities,removed_logs],sort_keys=True).encode()).hexdigest()
        summary = dict(counts=counts, affected_tasks=len(affected), token=fingerprint, selected_count=len(keys))
        if token is None:
            return summary
        if token != fingerprint:
            raise ValueError('数据已变化，请重新核对删除范围后确认。')
        for r in removed:
            db.execute('DELETE FROM task_entities WHERE task_id=? AND kind=? AND source=? AND entity_id=?', (r['task_id'],r['kind'],r['source'],r['entity_id']))
        for k in changed_keys:
            if k in latest:
                db.execute('INSERT OR REPLACE INTO entities VALUES(?,?,?,?)', (*k,latest[k]))
            else:
                db.execute('DELETE FROM entities WHERE kind=? AND source=? AND id=?', k)
        for task_id in affected:
            # Resuming an old browser batch could reinsert removed records.
            db.execute('DELETE FROM comment_pagination WHERE task_id=?', (task_id,))
            if task_id in deleted_tasks:
                db.execute('INSERT OR IGNORE INTO deleted_tasks VALUES(?,?)', (task_id,now()))
                db.execute('DELETE FROM logs WHERE task_id=?', (task_id,))
                db.execute('DELETE FROM task_business WHERE task_id=?', (task_id,))
                db.execute('DELETE FROM tasks WHERE id=?', (task_id,))
            else:
                note = '用户删除了部分本地记录；当前数量以列表为准。旧批次不可继续，如需重新读取请新建任务。'
                db.execute('UPDATE tasks SET note=? WHERE id=?', (note, task_id))
                store._log(db,task_id,'info',note)
        return dict(summary, status='deleted', deleted_task_ids=sorted(deleted_tasks))
