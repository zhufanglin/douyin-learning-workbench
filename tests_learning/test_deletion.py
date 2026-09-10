import pytest
from fastapi.testclient import TestClient
from learning.app import create_app


def seed(store, source='live', keyword='待删除任务'):
    t = store.create_task(keyword, source)
    data = dict(videos=[dict(id='v1'), dict(id='v2')], users=[dict(id='u1'), dict(id='u2')], comments=[dict(id='c1', video_id='v1', user_id='u1'), dict(id='r1', video_id='v1', user_id='u2', parent_comment_id='c1'), dict(id='c2', video_id='v2', user_id='u2')])
    store.finish(t['id'], data, 'success', '测试数据')
    return t, data


def remove(api, kind, id, source='live'):
    target = dict(kind=kind, id=id, source=source)
    preview = api.post('/api/learning/deletion/preview', json=target)
    assert preview.status_code == 200, preview.text
    result = api.post('/api/learning/deletion/commit', json=dict(**target, token=preview.json()['token']))
    assert result.status_code == 200, result.text
    return result.json()


def test_delete_task_keeps_shared_data_and_blocks_late_writes(tmp_path):
    with TestClient(create_app(tmp_path/'d.db')) as api:
        store = api.app.state.store
        t, data = seed(store)
        second, _ = seed(store, keyword='另一个任务')
        result = remove(api, 'tasks', t['id'])
        assert result['counts'] == dict(tasks=1, videos=0, users=0, comments=0, logs=2)
        assert api.get('/api/learning/tasks/'+t['id']).status_code == 404
        store.finish(t['id'], data, 'success', '迟到的数据')
        store.log(t['id'], 'warning', '迟到的日志')
        assert store.snapshot()['counts']['tasks'] == 1
        assert len(store.result(second['id'])['comments']) == 3
        with store.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM logs WHERE task_id=?',(t['id'],)).fetchone()[0] == 0
        remove(api, 'tasks', second['id'])
        assert all(store.snapshot()['counts'][k] == 0 for k in ['tasks','videos','users','comments'])


@pytest.mark.parametrize('kind,id,comments,videos,users', [('videos','v1',{'c2'},{'v2'},{'u2'}), ('users','u1',{'c2'},{'v1','v2'},{'u2'}), ('comments','c1',{'c2'},{'v1','v2'},{'u2'}), ('comments','r1',{'c1','c2'},{'v1','v2'},{'u1','u2'})])
def test_entity_cascade_is_source_scoped_and_clears_resume(tmp_path, kind, id, comments, videos, users):
    with TestClient(create_app(tmp_path/'d.db')) as api:
        store = api.app.state.store
        t, _ = seed(store)
        imported, _ = seed(store, source='import')
        with store.connect() as db:
            db.execute('INSERT INTO comment_pagination VALUES(?,?)', (t['id'], '{"revision": 3}'))
        remove(api, kind, id)
        result = store.result(t['id'])
        assert {c['id'] for c in result['comments']} == comments
        assert {v['id'] for v in result['videos']} == videos
        assert {u['id'] for u in result['users']} == users
        assert result['pagination'] is None
        assert len(store.result(imported['id'])['comments']) == 3
        assert api.post('/api/learning/tasks/'+t['id']+'/comments/next',json={'revision':3}).status_code == 409
        catalog = api.get('/api/learning/catalog').json()
        assert {c['id'] for c in catalog['comments'] if c['source']=='live'} == comments


def test_preview_change_and_running_task_protection(tmp_path):
    with TestClient(create_app(tmp_path/'d.db')) as api:
        store = api.app.state.store
        t, _ = seed(store)
        target = dict(kind='videos', id='v1', source='live')
        preview = api.post('/api/learning/deletion/preview',json=target).json()
        with store.connect() as db:
            db.execute("UPDATE tasks SET status='running' WHERE id=?", (t['id'],))
        assert api.post('/api/learning/deletion/commit',json=dict(**target,token=preview['token'])).status_code == 409
        assert api.post('/api/learning/deletion/preview',json=target).status_code == 409
        store.cancel(t['id'])
        assert api.post('/api/learning/deletion/commit',json=dict(**target,token=preview['token'])).status_code == 409
        assert len(store.result(t['id'])['videos']) == 2
        remove(api, 'videos', 'v1')
        assert api.post('/api/learning/deletion/preview',json=target).status_code == 404
        assert api.post('/api/learning/deletion/preview',json=dict(kind='oops',id='v2',source='live')).status_code == 422
        assert api.post('/api/learning/deletion/preview',json=target,headers={'origin':'https://external.test'}).status_code == 403


def test_delete_log_keeps_results(tmp_path):
    with TestClient(create_app(tmp_path/'d.db')) as api:
        t, _ = seed(api.app.state.store)
        logs = api.app.state.store.result(t['id'])['logs']
        remove(api,'logs',str(logs[-1]['id']))
        assert len(api.app.state.store.result(t['id'])['logs'])==len(logs)-1
        assert len(api.app.state.store.result(t['id'])['videos'])==2
