"""Conservative local term matching; decisions are scoped to criteria and evidence."""
import hashlib
import json
import re
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, Field
from .business import snapshot
from .store import now


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def extract_fields(content, profile):
    result={}
    for field in profile.get('fields',[]):
        found=[]
        for term in field['terms']:
            pattern=(r'(?<![A-Za-z0-9])' if term[0].isascii() and term[0].isalnum() else '')+re.escape(term)+(r'(?![A-Za-z0-9])' if term[-1].isascii() and term[-1].isalnum() else '')
            found.extend(m.group(0) for m in re.finditer(pattern,content,re.IGNORECASE))
        result[field['name']]=list(dict.fromkeys(found))
    return result


def assess(content, profile):
    text=content.casefold()
    hits={key:[word for word in profile.get(key,[]) if word.casefold() in text] for key in ('demand_terms','ad_terms','exclude_terms')}
    found=sum(hits.values(),[])
    if not text.strip():return 'pending',[], '没有可判断的文字'
    if any(word in text for word in ('不想','不要','不需要','不是','别再','并非','not ','no need')):
        return 'pending',found,'含否定表达，需人工核对上下文'
    if sum(bool(v) for v in hits.values())>1:
        return 'pending',found,'同时命中不同类别的词，需人工核对'
    if hits['exclude_terms']:return 'irrelevant',found,'命中排除词，仅为规则初判'
    if hits['ad_terms']:return 'advertising',found,'命中广告词，仅为规则初判'
    if hits['demand_terms']:return 'possible',found,'命中需求词，尚不能确认需求'
    return 'pending',[],'未命中配置词；不等于没有需求'


class Decision(BaseModel):
    source:Literal['live','import']
    comment_id:str=Field(min_length=1,max_length=256)
    revision:str=Field(min_length=64,max_length=64)
    status:Literal['clear','possible','advertising','irrelevant','pending']|None
    reason:str=Field(default='',max_length=1000)


def register(app,store):
    with store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS lead_analysis(profile_id TEXT, source TEXT, comment_id TEXT, payload TEXT NOT NULL, PRIMARY KEY(profile_id,source,comment_id))')

    def context(db,profile_id):
        try:profile=snapshot(db,profile_id)
        except ValueError:raise HTTPException(404,'业务配置不存在，请重新选择')
        comments=[dict(json.loads(r['payload']),source=r['source']) for r in db.execute("SELECT * FROM entities WHERE kind='comments' AND source IN ('live','import') ORDER BY source,id")]
        return profile,comments

    def revision(profile,c):
        return digest({'version':1,'profile':profile,'source':c['source'],'id':c['id'],'user_id':c.get('user_id'),'content':c.get('content'),'video_id':c.get('video_id')})

    def rows(db,profile_id,profile,comments):
        saved={(r['source'],r['comment_id']):json.loads(r['payload']) for r in db.execute('SELECT * FROM lead_analysis WHERE profile_id=?',(profile_id,))}
        items=[]
        for c in comments:
            value=saved.get((c['source'],c['id']))
            if value:items.append(dict(value,stale=value['revision']!=revision(profile,c)))
        return {'profile':profile,'items':items,'total_comments':len(comments)}

    @app.get('/api/learning/analysis/{profile_id}')
    def get_analysis(profile_id:str):
        with store.connect() as db:
            db.execute('BEGIN')
            profile,comments=context(db,profile_id)
            return rows(db,profile_id,profile,comments)

    @app.post('/api/learning/analysis/{profile_id}')
    def analyze(profile_id:str):
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            profile,comments=context(db,profile_id)
            for c in comments:
                rev=revision(profile,c)
                old=db.execute('SELECT payload FROM lead_analysis WHERE profile_id=? AND source=? AND comment_id=?',(profile_id,c['source'],c['id'])).fetchone()
                if old and json.loads(old['payload'])['revision']==rev:
                    value=json.loads(old['payload'])
                    if 'fields' not in value:
                        value['fields']=extract_fields(c.get('content',''),profile)
                        db.execute('UPDATE lead_analysis SET payload=? WHERE profile_id=? AND source=? AND comment_id=?',(json.dumps(value,ensure_ascii=False),profile_id,c['source'],c['id']))
                    continue
                status,evidence,reason=assess(c.get('content',''),profile)
                value=dict(source=c['source'],comment_id=c['id'],revision=rev,automatic=status,evidence=evidence,reason=reason,manual=None,fields=extract_fields(c.get('content',''),profile),analyzed_at=now())
                db.execute('INSERT OR REPLACE INTO lead_analysis VALUES(?,?,?,?)',(profile_id,c['source'],c['id'],json.dumps(value,ensure_ascii=False)))
            # Remove orphan judgments without retaining deleted comment data.
            valid={(c['source'],c['id']) for c in comments}
            for r in db.execute('SELECT source,comment_id FROM lead_analysis WHERE profile_id=?',(profile_id,)).fetchall():
                if (r['source'],r['comment_id']) not in valid:db.execute('DELETE FROM lead_analysis WHERE profile_id=? AND source=? AND comment_id=?',(profile_id,r['source'],r['comment_id']))
            return rows(db,profile_id,profile,comments)

    @app.put('/api/learning/analysis/{profile_id}/decision')
    def decide(profile_id:str,body:Decision):
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            profile,comments=context(db,profile_id)
            c=next((c for c in comments if c['source']==body.source and c['id']==body.comment_id),None)
            row=db.execute('SELECT payload FROM lead_analysis WHERE profile_id=? AND source=? AND comment_id=?',(profile_id,body.source,body.comment_id)).fetchone()
            if not c or not row:raise HTTPException(404,'评论或分析不存在，请刷新')
            value=json.loads(row['payload'])
            if body.revision!=revision(profile,c) or value['revision']!=body.revision:raise HTTPException(409,'配置或原话已变化，请重新分析后再判断')
            if body.status and not body.reason.strip():raise HTTPException(400,'请填写人工判断依据')
            value['manual']=dict(status=body.status,reason=body.reason.strip(),updated_at=now()) if body.status else None
            db.execute('UPDATE lead_analysis SET payload=? WHERE profile_id=? AND source=? AND comment_id=?',(json.dumps(value,ensure_ascii=False),profile_id,body.source,body.comment_id))
            return dict(value,stale=False)
