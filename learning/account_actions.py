"""Durable single-recipient action intents; an uncertain send is never retried."""
import hashlib
import json
import secrets
import time
from .store import now


class AccountActions:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS account_actions (
                id TEXT PRIMARY KEY, sender TEXT NOT NULL, target TEXT NOT NULL,
                kind TEXT NOT NULL, message TEXT NOT NULL, status TEXT NOT NULL,
                note TEXT NOT NULL, confirm_token TEXT NOT NULL DEFAULT '',
                expires_at REAL NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
            db.execute("UPDATE account_actions SET status='uncertain',confirm_token='',note='上次执行中断，结果不确定；只能核对，不能重复执行。' WHERE status IN ('executing','verifying')")
            db.execute("UPDATE account_actions SET status='blocked',confirm_token='',note='服务已重启，请重新核对账号与目标。' WHERE status IN ('checking','ready')")

    def get(self, id):
        with self.store.connect() as db:
            row = db.execute('SELECT * FROM account_actions WHERE id=?',(id,)).fetchone()
            if row is None: raise KeyError(id)
            return dict(row)

    def list(self):
        with self.store.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM account_actions ORDER BY updated_at DESC,rowid DESC LIMIT 100')]

    def prepare(self, payload):
        id = hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM account_actions WHERE id=?',(id,)).fetchone()
            if old and (old['status'] in ('checking','executing','verifying','uncertain','success','already_done') or old['status']=='ready' and old['expires_at']>time.time()):
                return dict(old, dispatch=False)
            if old:
                db.execute("UPDATE account_actions SET status='checking',confirm_token='',note='正在核对账号与目标；尚未执行关注或发送。',updated_at=? WHERE id=?",(now(),id))
            else:
                db.execute('INSERT INTO account_actions (id,sender,target,kind,message,status,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)', (id,payload['sender'],payload['target'],payload['kind'],payload['message'],'checking','正在核对账号与目标；尚未执行关注或发送。',now(),now()))
        return dict(self.get(id), dispatch=True)

    def mark(self, id, status, note):
        token = secrets.token_urlsafe(32) if status=='ready' else ''
        with self.store.connect() as db:
            db.execute('UPDATE account_actions SET status=?,note=?,confirm_token=?,expires_at=?,updated_at=? WHERE id=?', (status,note,token,time.time()+300 if token else 0,now(),id))
        return self.get(id)

    def confirm(self, id, token):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM account_actions WHERE id=?',(id,)).fetchone()
            if row is None: raise KeyError(id)
            if row['status']!='ready' or not token or not secrets.compare_digest(row['confirm_token'],token) or row['expires_at']<=time.time():
                raise ValueError('确认已失效或操作已提交，请重新核对；结果不确定时不能重复执行。')
            db.execute("UPDATE account_actions SET status='executing',confirm_token='',note='已确认单次执行，正在再次核对账号与目标。',updated_at=? WHERE id=?",(now(),id))
        return self.get(id)

    def verify(self,id):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM account_actions WHERE id=?',(id,)).fetchone()
            if row is None: raise KeyError(id)
            if row['status']!='uncertain': raise ValueError('只对结果不确定的操作进行只读核对。')
            db.execute("UPDATE account_actions SET status='verifying',note='只核对页面，不点击关注或发送。',updated_at=? WHERE id=?",(now(),id))
        return self.get(id)
