from fastapi.testclient import TestClient
from learning.app import create_app

def test_profile_crud_snapshot_and_invalid_selection(tmp_path):
    with TestClient(create_app(tmp_path/'db')) as c:
        body={'name':'产品咨询','goal':'找明确询价的人','keywords':['产品咨询'],'include':'询问价格','exclude':'推广广告'}
        r=c.post('/api/learning/business-profiles',json=body);assert r.status_code==200
        profile=r.json();id=profile['id']
        task=c.post('/api/learning/tasks',json={'keyword':'产品咨询','source':'demo','business_profile_id':id}).json()
        c.put('/api/learning/business-profiles/'+id,json={**body,'goal':'新目标'})
        c.delete('/api/learning/business-profiles/'+id)
        assert c.get('/api/learning/tasks/'+task['id']).json()['business_profile']['goal']==body['goal']
        assert c.get('/api/learning/business-profiles').json()['items']==[]
        before=len(c.app.state.store.snapshot()['tasks'])
        assert c.post('/api/learning/tasks',json={'keyword':'测试','business_profile_id':id}).status_code==400
        assert len(c.app.state.store.snapshot()['tasks'])==before
        assert c.post('/api/learning/business-profiles',json={**body,'goal':' '}).status_code==422
