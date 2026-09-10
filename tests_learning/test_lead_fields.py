from fastapi.testclient import TestClient
from learning.app import create_app

def test_configurable_fields_preserve_original_and_isolate(tmp_path):
 with TestClient(create_app(tmp_path/'db')) as api:
  body={'name':'产品','goal':'咨询','keywords':['产品'],'fields':[{'name':'规格','terms':['XL','小号']},{'name':'预算','terms':['100元']}]}
  p=api.post('/api/learning/business-profiles',json=body)
  assert p.status_code==200
  pid=p.json()['id']
  s=api.app.state.store;t=s.create_task('来源','import')
  s.finish(t['id'],{'comments':[{'id':'1','user_id':'u','video_id':'123','content':'想要xl，预算100元'}, {'id':'2','user_id':'u','video_id':'123','content':'多少钱？'}]},'success','ok')
  rows=api.post('/api/learning/analysis/'+pid).json()['items']
  assert rows[0]['fields']=={'规格':['xl'],'预算':['100元']}
  assert rows[1]['fields']=={'规格':[],'预算':[]}
  q=api.post('/api/learning/business-profiles',json={**body,'name':'服务','fields':[{'name':'服务','terms':['安装']}]}).json()
  assert api.post('/api/learning/analysis/'+q['id']).json()['items'][0]['fields']=={'服务':[]}
  assert api.get('/api/learning/analysis/'+pid).json()['items'][0]['fields']==rows[0]['fields']
  assert api.post('/api/learning/business-profiles',json={**body,'fields':[{'name':'规格','terms':[]},{'name':'规格','terms':[]}]}).status_code==422
  assert api.post('/api/learning/business-profiles',json={**body,'fields':[{'name':'','terms':['x']}]}).status_code==422

def test_field_numeric_boundaries_and_legacy_manual(tmp_path):
 import json
 from learning.analysis import extract_fields
 assert extract_fields('预算1100元，不要XXL',{'fields':[{'name':'预算','terms':['100元']},{'name':'规格','terms':['XL']}]})=={'预算':[],'规格':[]}
 with TestClient(create_app(tmp_path/'db')) as api:
  p=api.post('/api/learning/business-profiles',json={'name':'通用','goal':'需求','keywords':['需求']}).json()
  s=api.app.state.store;t=s.create_task('来源','import')
  s.finish(t['id'],{'comments':[{'id':'1','user_id':'u','content':'原话'}]},'success','ok')
  item=api.post('/api/learning/analysis/'+p['id']).json()['items'][0]
  api.put('/api/learning/analysis/'+p['id']+'/decision',json={'source':'import','comment_id':'1','revision':item['revision'],'status':'possible','reason':'人工依据'})
  with s.connect() as db:
   row=db.execute('SELECT payload FROM lead_analysis').fetchone()
   legacy=json.loads(row['payload']);legacy.pop('fields')
   db.execute('UPDATE lead_analysis SET payload=?',(json.dumps(legacy),))
  migrated=api.post('/api/learning/analysis/'+p['id']).json()['items'][0]
  assert migrated['fields']=={}
  assert migrated['manual']['reason']=='人工依据'
