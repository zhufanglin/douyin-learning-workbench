"""Read-only local browsing index. Task detail remains its immutable snapshot."""
import json
from collections import defaultdict
from datetime import datetime


def catalog(store, keyword='', task_id='', start='', end=''):
    with store.connect() as db:
        db.execute('BEGIN')
        tasks = [dict(r) for r in db.execute("SELECT * FROM tasks WHERE source IN ('live','import') ORDER BY created_at DESC,rowid DESC")]
        tasks = [t for t in tasks if (not keyword or keyword.casefold() in t['keyword'].casefold())
            and (not task_id or t['id'] == task_id)
            and (not start or datetime.fromisoformat(t['created_at']) >= datetime.fromisoformat(start))
            and (not end or datetime.fromisoformat(t['created_at']) < datetime.fromisoformat(end))]
        profiles = {r['task_id']: json.loads(r['payload']) for r in db.execute('SELECT * FROM task_business')}
        for task in tasks:
            task['business_profile'] = profiles.get(task['id'])
        by_id = {t['id']: t for t in tasks}
        memberships = defaultdict(list)
        snapshots = {}
        for task in tasks:
            task.update(videos=[], counts=dict(videos=0, comments=0, users=0))
        for row in db.execute("SELECT te.* FROM task_entities te JOIN tasks t ON t.id=te.task_id WHERE t.source IN ('live','import') ORDER BY t.created_at DESC,t.rowid DESC"):
            if row['task_id'] not in by_id:
                continue
            task = by_id[row['task_id']]
            kind = row['kind']
            if kind in task['counts']:
                task['counts'][kind] += 1
            if kind == 'videos':
                task['videos'].append(json.loads(row['payload']))
            memberships[(kind, row['source'], row['entity_id'])].append(row['task_id'])
            snapshots.setdefault((kind, row['source'], row['entity_id']), json.loads(row['payload']))
        for task in tasks:
            task['videos'].sort(key=lambda v: v.get('search_rank', 1000000))
        result = dict(tasks=tasks)
        for kind in ('videos', 'comments', 'users'):
            if keyword or task_id or start or end:
                result[kind] = [dict(value, task_ids=memberships[key]) for key, value in snapshots.items() if key[0] == kind]
            else:
                result[kind] = [dict(json.loads(r['payload']), task_ids=memberships[(kind, r['source'], r['id'])])
                    for r in db.execute("SELECT * FROM entities WHERE kind=? AND source IN ('live','import') ORDER BY source,id", (kind,))]
        return result
