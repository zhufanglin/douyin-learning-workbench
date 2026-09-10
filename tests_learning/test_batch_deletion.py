from fastapi.testclient import TestClient
from learning.app import create_app
from tests_learning.test_deletion import seed


def target(kind,id,source='live'):
    return dict(kind=kind,id=id,source=source)


def test_batch_union_dedup_shared_data_and_order(tmp_path):
    with TestClient(create_app(tmp_path/'b.db')) as api:
        t,_=seed(api.app.state.store)
        t2,_=seed(api.app.state.store)
        selected=[target('tasks',t['id']),target('tasks',t2['id']),target('tasks',t['id'])]
        preview=api.post('/api/learning/deletion/batch-preview',json={'targets':selected})
        assert preview.status_code==200,preview.text
        plan=preview.json()
        assert plan['selected_count']==2
        assert plan['counts']==dict(tasks=2,videos=2,comments=3,users=2,logs=4)
        result=api.post('/api/learning/deletion/batch-commit',json={'targets':list(reversed(selected)),'token':plan['token']})
        assert result.status_code==200,result.text
        assert api.app.state.store.snapshot()['counts']['tasks']==0


def test_batch_atomic_running_missing_stale_and_source_isolation(tmp_path):
    with TestClient(create_app(tmp_path/'b.db')) as api:
        t,_=seed(api.app.state.store)
        imported,_=seed(api.app.state.store,source='import')
        selected=[target('videos','v1'),target('videos','v2')]
        plan=api.post('/api/learning/deletion/batch-preview',json={'targets':selected}).json()
        with api.app.state.store.connect() as db: db.execute("UPDATE tasks SET status='running' WHERE id=?",(t['id'],))
        assert api.post('/api/learning/deletion/batch-commit',json={'targets':selected,'token':plan['token']}).status_code==409
        assert len(api.app.state.store.result(t['id'])['videos'])==2
        api.app.state.store.cancel(t['id'])
        assert api.post('/api/learning/deletion/batch-commit',json={'targets':selected,'token':plan['token']}).status_code==409
        assert api.post('/api/learning/deletion/batch-preview',json={'targets':selected+[target('videos','missing')]}).status_code==404
        plan=api.post('/api/learning/deletion/batch-preview',json={'targets':selected}).json()
        assert api.post('/api/learning/deletion/batch-commit',json={'targets':selected,'token':plan['token']}).status_code==200
        assert not api.app.state.store.result(t['id'])['videos']
        assert len(api.app.state.store.result(imported['id'])['videos'])==2
        assert api.post('/api/learning/deletion/batch-preview',json={'targets':[]}).status_code==422


def test_batch_comments_overlapping_replies_and_logs(tmp_path):
    with TestClient(create_app(tmp_path/'b.db')) as api:
        t,_=seed(api.app.state.store)
        selected=[target('comments','c1'),target('comments','r1')]
        plan=api.post('/api/learning/deletion/batch-preview',json={'targets':selected}).json()
        assert plan['counts']['comments']==2
        assert api.post('/api/learning/deletion/batch-commit',json={'targets':selected,'token':plan['token']}).status_code==200
        logs=api.app.state.store.result(t['id'])['logs']
        selected=[target('logs',str(l['id'])) for l in logs]
        plan=api.post('/api/learning/deletion/batch-preview',json={'targets':selected}).json()
        assert plan['counts']['logs']==len(logs)
        assert api.post('/api/learning/deletion/batch-commit',json={'targets':selected,'token':plan['token']}).status_code==200
        assert not api.app.state.store.result(t['id'])['logs']
        assert len(api.app.state.store.result(t['id'])['comments'])==1
