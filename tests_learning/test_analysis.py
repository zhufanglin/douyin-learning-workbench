from fastapi.testclient import TestClient
from learning.app import create_app

def test_analysis_isolation_override_and_stale(tmp_path):
 with TestClient(create_app(tmp_path/'db')) as c:
  profiles=[]
  for word in ['询价','预约']:
   r=c.post('/api/learning/business-profiles',json={'name':word,'goal':word,'keywords':[word],'demand_terms':[word],'ad_terms':['欢迎下单'],'exclude_terms':['已买']})
   assert r.status_code==200
   profiles.append(r.json())
  s=c.app.state.store;t=s.create_task('来源','import')
  comments=[{'id':str(i),'user_id':'u','video_id':'123','content':text} for i,text in enumerate(['想询价','想预约','欢迎下单','已经已买','不想询价','普通留言'])]
  s.finish(t['id'],{'comments':comments},'success','ok')
  p,q=profiles
  first=c.post('/api/learning/analysis/'+p['id']).json()
  assert [x['automatic'] for x in first['items']]==['possible','pending','advertising','irrelevant','pending','pending']
  assert first['items'][0]['evidence']==['询价']
  item=first['items'][0]
  r=c.put('/api/learning/analysis/'+p['id']+'/decision',json={'source':'import','comment_id':'0','revision':item['revision'],'status':'clear','reason':'已核对原话'})
  assert r.status_code==200
  assert c.post('/api/learning/analysis/'+p['id']).json()['items'][0]['manual']['status']=='clear'
  other=c.post('/api/learning/analysis/'+q['id']).json()
  assert other['items'][0]['manual'] is None
  assert other['items'][1]['automatic']=='possible'
  c.put('/api/learning/business-profiles/'+p['id'],json={k:v for k,v in dict(p,demand_terms=['别的词']).items() if k!='id'})
  assert c.get('/api/learning/analysis/'+p['id']).json()['items'][0]['stale']
  assert c.put('/api/learning/analysis/'+p['id']+'/decision',json={'source':'import','comment_id':'0','revision':item['revision'],'status':'clear','reason':'旧结果'}).status_code==409
  assert c.post('/api/learning/analysis/'+p['id']).json()['items'][0]['manual'] is None
  with s.connect() as db:db.execute("DELETE FROM entities WHERE kind='comments' AND id='0'")
  assert all(x['comment_id']!='0' for x in c.get('/api/learning/analysis/'+p['id']).json()['items'])

def test_conservative_conflicts_and_empty_rules():
 from learning.analysis import assess
 profile={'demand_terms':['询价'],'ad_terms':['下单'],'exclude_terms':['已买']}
 assert assess('询价后欢迎下单',profile)[0]=='pending'
 assert assess('',profile)[0]=='pending'
 assert assess('询价',{})[0]=='pending'
 assert assess('询价',profile)[0]=='possible'
