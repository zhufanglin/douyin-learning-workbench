"""Saved business criteria and immutable task snapshots, with no platform actions."""
import json
from uuid import uuid4
from pydantic import BaseModel,ConfigDict,Field,field_validator
from fastapi import HTTPException

class DemandField(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    name:str=Field(min_length=1,max_length=40)
    terms:list[str]=Field(default_factory=list,max_length=50)
    @field_validator('terms')
    @classmethod
    def validate_terms(cls,values):
        values=list(dict.fromkeys(v.strip() for v in values if v.strip()))
        if any(len(v)>80 for v in values):raise ValueError('字段短语每条最多80字')
        return values

class BusinessProfile(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    name:str=Field(min_length=1,max_length=80)
    goal:str=Field(min_length=1,max_length=2000)
    keywords:list[str]=Field(min_length=1,max_length=20)
    include:str=Field(default='',max_length=4000)
    exclude:str=Field(default='',max_length=4000)
    demand_terms:list[str]=Field(default_factory=list,max_length=50)
    ad_terms:list[str]=Field(default_factory=list,max_length=50)
    exclude_terms:list[str]=Field(default_factory=list,max_length=50)
    fields:list[DemandField]=Field(default_factory=list,max_length=10)
    @field_validator('fields')
    @classmethod
    def unique_fields(cls,values):
        if len({v.name.casefold() for v in values})!=len(values):raise ValueError('字段名称不能重复')
        return values
    @field_validator('demand_terms','ad_terms','exclude_terms')
    @classmethod
    def valid_terms(cls,values):
        values=list(dict.fromkeys(v.strip() for v in values if v.strip()))
        if any(len(v)>80 for v in values):raise ValueError('匹配词每条最多80字')
        return values
    @field_validator('keywords')
    @classmethod
    def valid_keywords(cls,values):
        values=list(dict.fromkeys(v.strip() for v in values if v.strip()))
        if not values or any(len(v)>80 for v in values):raise ValueError('请填写1至20个关键词，每个最多80字。')
        return values

def install(store):
    with store.connect() as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS business_profiles(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS task_business(task_id TEXT PRIMARY KEY,payload TEXT NOT NULL);''')

def snapshot(db,identity):
    if not identity:return None
    row=db.execute('SELECT payload FROM business_profiles WHERE id=?',(identity,)).fetchone()
    if not row:raise ValueError('业务配置不存在，请重新选择。')
    return json.loads(row['payload'])

def register(app,store):
    @app.get('/api/learning/business-profiles')
    def profiles():
        with store.connect() as db:return {'items':[json.loads(r['payload']) for r in db.execute('SELECT payload FROM business_profiles ORDER BY rowid DESC')]}
    @app.post('/api/learning/business-profiles')
    def create(body:BusinessProfile):
        value=dict(body.model_dump(),id=uuid4().hex)
        with store.connect() as db:db.execute('INSERT INTO business_profiles VALUES(?,?)',(value['id'],json.dumps(value,ensure_ascii=False)))
        return value
    @app.put('/api/learning/business-profiles/{identity}')
    def update(identity:str,body:BusinessProfile):
        value=dict(body.model_dump(),id=identity)
        with store.connect() as db:
            if not db.execute('UPDATE business_profiles SET payload=? WHERE id=?',(json.dumps(value,ensure_ascii=False),identity)).rowcount:raise HTTPException(404,'配置不存在')
        return value
    @app.delete('/api/learning/business-profiles/{identity}')
    def delete(identity:str):
        with store.connect() as db:
            if not db.execute('DELETE FROM business_profiles WHERE id=?',(identity,)).rowcount:raise HTTPException(404,'配置不存在')
        return {'deleted':identity}
