"""Small durable task ledger. SQLite uniqueness also covers concurrent clicks."""
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from . import REPLY_READER_VERSION


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS comment_pagination (
                    task_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS deleted_tasks (id TEXT PRIMARY KEY, deleted_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, keyword TEXT NOT NULL, source TEXT NOT NULL,
                    status TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS entities (
                    kind TEXT NOT NULL, source TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(kind,source,id));
                CREATE TABLE IF NOT EXISTS task_entities (
                    task_id TEXT NOT NULL, kind TEXT NOT NULL, source TEXT NOT NULL, entity_id TEXT NOT NULL,
                    payload TEXT,
                    PRIMARY KEY(task_id,kind,source,entity_id));
                CREATE TABLE IF NOT EXISTS actions (
                    id TEXT PRIMARY KEY, source TEXT NOT NULL, user_id TEXT NOT NULL,
                    kind TEXT NOT NULL, message TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, level TEXT NOT NULL,
                    message TEXT NOT NULL, created_at TEXT NOT NULL);
            ''')
            # Migrate earlier local prototype DBs without dropping their saved results.
            columns = {r['name'] for r in db.execute('PRAGMA table_info(task_entities)')}
            if 'payload' not in columns:
                db.execute('ALTER TABLE task_entities ADD COLUMN payload TEXT')
            db.execute('''UPDATE task_entities SET payload=(SELECT payload FROM entities e
                WHERE e.kind=task_entities.kind AND e.source=task_entities.source
                AND e.id=task_entities.entity_id) WHERE payload IS NULL''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def recover(self):
        with self.connect() as db:
            tasks = db.execute("SELECT id FROM tasks WHERE status IN ('queued','running')").fetchall()
            for task in tasks:
                db.execute("UPDATE tasks SET status='needs_review',note=? WHERE id=?",
                           ('上次执行中断，请核对已有结果后创建新任务；未自动重试。', task['id']))
                self._log(db, task['id'], 'warning', '启动恢复：中断任务标记为需核对。')
            db.execute("UPDATE actions SET status='uncertain' WHERE status='running'")

    def _log(self, db, task_id, level, message):
        if db.execute('SELECT 1 FROM deleted_tasks WHERE id=?', (task_id,)).fetchone():
            return
        db.execute('INSERT INTO logs(task_id,level,message,created_at) VALUES(?,?,?,?)',
                   (task_id, level, message, now()))

    def log(self, task_id, level, message):
        with self.connect() as db:
            self._log(db, task_id, level, message)

    def create_task(self, keyword, source):
        task = dict(id=uuid4().hex, keyword=keyword, source=source, status='running',
                    note='正在执行', created_at=now())
        with self.connect() as db:
            db.execute('INSERT INTO tasks VALUES(:id,:keyword,:source,:status,:note,:created_at)', task)
            self._log(db, task['id'], 'info', f'创建任务：{keyword}；来源：{source}')
        return task

    def get_task(self, task_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        return dict(row)

    def finish(self, task_id, data, status, note):
        # Check state and commit all entities in one write transaction. Cancellation wins.
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            task = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
            if task is None:
                if db.execute('SELECT 1 FROM deleted_tasks WHERE id=?', (task_id,)).fetchone():
                    return {'id': task_id, 'status': 'deleted'}
                raise KeyError(task_id)
            if task['status'] != 'running':
                return dict(task)
            if data.get('pagination'):
                saved = db.execute('SELECT payload FROM comment_pagination WHERE task_id=?', (task_id,)).fetchone()
                latest = json.loads(saved['payload']) if saved else None
                if latest and latest['revision'] != data['pagination']['revision']:
                    return dict(task)
            source = task['source']
            for kind in ('videos', 'comments', 'users'):
                for item in data.get(kind, []):
                    payload = dict(item, source=source)
                    db.execute('INSERT OR REPLACE INTO entities VALUES(?,?,?,?)',
                               (kind, source, item['id'], json.dumps(payload, ensure_ascii=False)))
                    db.execute('INSERT OR REPLACE INTO task_entities(task_id,kind,source,entity_id,payload) VALUES(?,?,?,?,?)',
                               (task_id, kind, source, item['id'], json.dumps(payload, ensure_ascii=False)))
            db.execute('UPDATE tasks SET status=?,note=? WHERE id=?', (status, note, task_id))
            if 'pagination' in data:
                db.execute('INSERT OR REPLACE INTO comment_pagination VALUES(?,?)',
                           (task_id, json.dumps(data['pagination'], ensure_ascii=False)))
            self._log(db, task_id, 'info' if status in ('success', 'simulated', 'running') else 'warning', note)
        return self.get_task(task_id)

    def begin_reply_batch(self, task_id, parent_id, revision):
        return self.begin_comment_batch(task_id, revision, reply_id=parent_id)

    def begin_comment_batch(self, task_id, revision, reply_id=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            task = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
            if task is None:
                raise KeyError(task_id)
            row = db.execute('SELECT payload FROM comment_pagination WHERE task_id=?', (task_id,)).fetchone()
            paging = json.loads(row['payload']) if row else None
            if not paging or task['source'] != 'live':
                raise ValueError('旧任务或本地导入不支持继续采集，请重新选择视频。')
            if task['status'] == 'running' or paging['revision'] != revision:
                raise ValueError('本批已提交或页面状态已更新，请等待结果刷新。')
            comments = [json.loads(r['payload']) for r in db.execute("SELECT payload FROM task_entities WHERE task_id=? AND kind='comments'", (task_id,))]
            if reply_id:
                parent = next((c for c in comments if c['id'] == reply_id), None)
                if parent is None:
                    raise KeyError(reply_id)
                if parent.get('parent_comment_id') or parent.get('video_id') != paging['video_id']:
                    raise ValueError('只能读取本视频主评论下的回复。')
                progress = paging.setdefault('replies', {}).setdefault(reply_id, {'target': 100, 'exhausted': False})
                if progress['exhausted']:
                    raise ValueError('该评论的页面回复已读取完毕。')
                if progress.get('end_state') == 'unsupported' and progress.get('page_end') and progress.get('reader_version', 1) >= REPLY_READER_VERSION:
                    raise ValueError('已到回复页尾，剩余内容未支持；不能重复读取同一批次。')
                count = sum(c.get('parent_comment_id') == reply_id for c in comments)
                progress['target'] = (count // 100 + 1) * 100
                progress['end_state'] = 'reading'
                progress['reader_version'] = REPLY_READER_VERSION
            else:
                if paging['exhausted']:
                    raise ValueError('页面已明确提示主评论没有更多内容。')
                count = sum(not c.get('parent_comment_id') for c in comments)
                paging['target'] = (count // 100 + 1) * 100
            paging.update(revision=revision + 1, active_reply=reply_id)
            db.execute('UPDATE comment_pagination SET payload=? WHERE task_id=?', (json.dumps(paging), task_id))
            db.execute("UPDATE tasks SET status='running',note='正在继续读取评论…' WHERE id=?", (task_id,))
            self._log(db, task_id, 'info', '用户请求读取指定评论的回复。' if reply_id else f"用户请求继续读取主评论，累计目标 {paging['target']} 条。")
        return self.get_task(task_id)

    def cancel(self, task_id):
        self.get_task(task_id)
        with self.connect() as db:
            count = db.execute("UPDATE tasks SET status='cancelled',note='用户已取消；不再写入后续结果。' WHERE id=? AND status='running'", (task_id,)).rowcount
            if count:
                self._log(db, task_id, 'warning', '任务已取消。')
        return self.get_task(task_id)

    def result(self, task_id):
        result = {'task': self.get_task(task_id)}
        with self.connect() as db:
            for kind in ('videos', 'comments', 'users'):
                rows = db.execute('''SELECT payload FROM task_entities
                    WHERE task_id=? AND kind=? ORDER BY entity_id''', (task_id, kind)).fetchall()
                result[kind] = [json.loads(row['payload']) for row in rows]
                if kind == 'videos':
                    result[kind].sort(key=lambda item: item.get('search_rank', 1000000))
                if kind == 'comments':
                    result[kind].sort(key=lambda item: (bool(item.get('parent_comment_id')), item.get('reply_rank' if item.get('parent_comment_id') else 'comment_rank', 1000000)))
            paging = db.execute('SELECT payload FROM comment_pagination WHERE task_id=?', (task_id,)).fetchone()
            result['pagination'] = json.loads(paging['payload']) if paging else None
            result['logs'] = [dict(r) for r in db.execute('SELECT * FROM logs WHERE task_id=? ORDER BY id', (task_id,))]
        return result

    def snapshot(self, include_demo=True):
        with self.connect() as db:
            # Filter before LIMIT so internal test history cannot hide real work.
            visible = "(? OR source IN ('live','import'))"
            params = (include_demo,)
            return {
                'tasks': [dict(r) for r in db.execute(f'SELECT * FROM tasks WHERE {visible} ORDER BY created_at DESC,rowid DESC LIMIT 100', params)],
                'users': [json.loads(r[0]) for r in db.execute(f"SELECT payload FROM entities WHERE kind='users' AND {visible} ORDER BY source,id LIMIT 500", params)],
                'actions': [dict(r) for r in db.execute(f'SELECT * FROM actions WHERE {visible} ORDER BY created_at DESC,rowid DESC LIMIT 100', params)],
                'logs': [dict(r) for r in db.execute("SELECT l.*, t.source FROM logs l LEFT JOIN tasks t ON t.id=l.task_id WHERE (? OR t.source IN ('live','import')) ORDER BY l.id DESC LIMIT 100", params)],
                'counts': {
                    'tasks': db.execute(f'SELECT count(*) FROM tasks WHERE {visible}', params).fetchone()[0],
                    **{kind: db.execute(f'SELECT count(*) FROM entities WHERE kind=? AND {visible}', (kind, include_demo)).fetchone()[0] for kind in ('videos', 'users', 'comments')},
                    'actions': db.execute(f'SELECT count(*) FROM actions WHERE {visible}', params).fetchone()[0],
                },
            }

    def simulate_action(self, user_id, kind, message):
        message = message.strip() if kind == 'message' else ''
        key = hashlib.sha256(json.dumps(['demo', user_id, kind, message], ensure_ascii=False).encode()).hexdigest()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute("SELECT 1 FROM entities WHERE kind='users' AND source='demo' AND id=?", (user_id,)).fetchone():
                raise KeyError(user_id)
            existing = db.execute('SELECT * FROM actions WHERE id=?', (key,)).fetchone()
            if existing:
                return dict(existing, duplicate=True)
            action = dict(id=key, source='demo', user_id=user_id, kind=kind, message=message,
                          status='simulated', created_at=now())
            db.execute('INSERT INTO actions VALUES(:id,:source,:user_id,:kind,:message,:status,:created_at)', action)
            self._log(db, '', 'info', f'模拟{kind}已记录；未访问真实账号。对象：{user_id}')
        return dict(action, duplicate=False)
