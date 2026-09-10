"""Read selected local records in one consistent SQLite snapshot."""
import csv
import io
import json
from .store import now


def selected_records(store, targets, task_id=''):
    keys = list(dict.fromkeys((r['kind'], r['source'], r['id']) for r in targets))
    if len({k[0] for k in keys}) != 1:
        raise ValueError('请在同一个数据板块中选择记录。')
    records = []
    with store.connect() as db:
        db.execute('BEGIN')
        for kind, source, identity in keys:
            if source not in ('live','import'):
                raise ValueError('仅导出真实读取或本地导入的数据。')
            if kind == 'tasks':
                row = db.execute('SELECT * FROM tasks WHERE id=? AND source=?', (identity,source)).fetchone()
                if row is None: raise KeyError(identity)
                record = dict(row)
                for entity in ('videos','users','comments'):
                    record[entity] = [json.loads(r['payload']) for r in db.execute('SELECT payload FROM task_entities WHERE task_id=? AND kind=? ORDER BY entity_id', (identity,entity))]
                record['logs'] = [dict(r) for r in db.execute('SELECT * FROM logs WHERE task_id=? ORDER BY id', (identity,))]
            elif kind == 'logs':
                row = db.execute('SELECT l.*, t.source FROM logs l JOIN tasks t ON t.id=l.task_id WHERE l.id=? AND t.source=?', (identity,source)).fetchone()
                if row is None: raise KeyError(identity)
                record = dict(row)
            else:
                if task_id:
                    row = db.execute('SELECT payload FROM task_entities WHERE task_id=? AND kind=? AND source=? AND entity_id=?', (task_id,kind,source,identity)).fetchone()
                else:
                    row = db.execute('SELECT payload FROM entities WHERE kind=? AND source=? AND id=?', (kind,source,identity)).fetchone()
                if row is None: raise KeyError(identity)
                record = dict(json.loads(row['payload']), id=identity, source=source)
                record['task_ids'] = [r['task_id'] for r in db.execute('SELECT task_id FROM task_entities WHERE kind=? AND source=? AND entity_id=? ORDER BY task_id', (kind,source,identity))]
            records.append(record)
    return {'kind':keys[0][0], 'exported_at':now(), 'count':len(records), 'scope':'task_snapshot' if task_id else 'selected_local_records', 'task_id':task_id, 'records':records}


def encode_export(data, format):
    if format == 'json':
        return json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8'), 'application/json'
    fields = list(dict.fromkeys(k for r in data['records'] for k in r))
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=fields)
    def cell(value):
        text = json.dumps(value, ensure_ascii=False) if isinstance(value,(list,dict)) else str(value if value is not None else '')
        return "'"+text if text.lstrip().startswith(('=','+','-','@')) or text.startswith(('\t','\r','\n')) else text
    writer.writerow({key:cell(key) for key in fields})
    writer.writerows({k:cell(v) for k,v in row.items()} for row in data['records'])
    return output.getvalue().encode('utf-8-sig'), 'text/csv'
