import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from learning.app import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'test.db')) as c:
        yield c


def search(c, keyword='露营'):
    response = c.post('/api/learning/tasks', json={'keyword': keyword, 'source': 'demo'})
    assert response.status_code == 200, response.text
    return response.json()


def test_search_filters_fixed_fixtures_and_deduplicates_across_tasks(client):
    task = search(client)
    assert task['status'] == 'simulated'
    data = client.get(f"/api/learning/tasks/{task['id']}").json()
    assert len(data['videos']) == 2
    assert len(data['comments']) == 3
    assert len(data['users']) == 2
    search(client)
    assert len(client.get('/api/learning/state').json()['users']) == 2
    empty = search(client, '不存在的测试词xyz')
    assert client.get(f"/api/learning/tasks/{empty['id']}").json()['videos'] == []


def test_workspace_excludes_demo_before_limits_without_deleting_saved_data(client):
    store = client.app.state.store
    live = store.create_task('真实任务', 'live')
    data = dict(videos=[dict(id='v')], comments=[dict(id='c')], users=[dict(id='u')])
    store.finish(live['id'], data, 'success', '真实读取记录')
    imported = store.create_task('导入任务', 'import')
    store.finish(imported['id'], data, 'success', '导入记录')
    demo = search(client)
    client.post('/api/learning/actions', json={'source': 'demo', 'user_id': 'demo-user-1', 'kind': 'follow'})
    # A long demo history must not crowd out the real tasks or their logs.
    for i in range(105):
        store.create_task(f'内部样例{i}', 'demo')
    workspace = client.get('/api/learning/state?include_demo=false').json()
    assert {t['id'] for t in workspace['tasks']} == {live['id'], imported['id']}
    assert {u['source'] for u in workspace['users']} == {'live', 'import'}
    assert workspace['actions'] == []
    assert {log['task_id'] for log in workspace['logs']} == {live['id'], imported['id']}
    assert workspace['counts'] == dict(tasks=2, videos=2, users=2, comments=2, actions=0)
    assert client.get('/api/learning/tasks/' + demo['id']).json()['task']['source'] == 'demo'
    assert len(client.get('/api/learning/state').json()['actions']) == 1


def test_actions_are_idempotent_under_concurrent_requests(client):
    search(client)
    body = {'source': 'demo', 'user_id': 'demo-user-1', 'kind': 'follow', 'message': ''}
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.post('/api/learning/actions', json=body), range(4)))
    assert all(r.status_code == 200 for r in responses)
    assert len({r.json()['id'] for r in responses}) == 1
    assert all(r.json()['status'] == 'simulated' for r in responses)
    assert len(client.get('/api/learning/state').json()['actions']) == 1


def test_messages_normalize_whitespace_but_different_content_is_distinct(client):
    search(client)
    body = {'source': 'demo', 'user_id': 'demo-user-1', 'kind': 'message', 'message': '  你好  '}
    first = client.post('/api/learning/actions', json=body).json()
    body['message'] = '你好'
    assert client.post('/api/learning/actions', json=body).json()['id'] == first['id']
    body['message'] = '第二条本地测试'
    assert client.post('/api/learning/actions', json=body).json()['id'] != first['id']


def test_real_actions_rejected_and_no_fabricated_success(client):
    for source in ['live', 'import']:
        r = client.post('/api/learning/actions', json={'source': source, 'user_id': '123', 'kind': 'message', 'message': 'test'})
        assert r.status_code == 409
        assert r.json()['detail']['status'] == 'pending_integration'
    assert client.get('/api/learning/state').json()['actions'] == []
    assert client.post('/api/crawler/start', json={}).status_code == 404


def test_import_media_crawler_records_dedupes_and_preserves_source(client):
    search(client)
    record = {'comment_id': 'c1', 'aweme_id': 'v1', 'user_id': 'demo-user-1', 'nickname': '导入用户', 'content': '测试'}
    r = client.post('/api/learning/import', json={'records': [record, record]})
    assert r.status_code == 200, r.text
    result = client.get('/api/learning/tasks/' + r.json()['id']).json()
    assert len(result['comments']) == 1
    assert len(result['users']) == 1
    assert result['users'][0]['source'] == 'import'
    assert len(client.get('/api/learning/state').json()['users']) == 3
    exported = client.get('/api/learning/export/' + r.json()['id'])
    assert exported.status_code == 200
    assert exported.json()['task']['source'] == 'import'


def test_invalid_import_is_atomic_and_cannot_be_labeled_demo(client):
    r = client.post('/api/learning/import', json={'records': [
        {'comment_id': 'c1', 'aweme_id': 'v1', 'user_id': 'u1', 'content': 'ok'},
        {'nickname': '无稳定ID'}]})
    assert r.status_code == 422
    assert client.get('/api/learning/state').json()['users'] == []
    record = {'comment_id': 'c1', 'aweme_id': 'v1', 'user_id': 'u1', 'source': 'demo', 'content': 'ok'}
    task = client.post('/api/learning/import', json={'records': [record]}).json()
    assert client.get('/api/learning/tasks/' + task['id']).json()['users'][0]['source'] == 'import'


def test_persistence_and_interrupted_task_recovery(tmp_path):
    db = tmp_path / 'persist.db'
    with TestClient(create_app(db)) as c:
        task = search(c)
        c.post('/api/learning/actions', json={'source': 'demo', 'user_id': 'demo-user-1', 'kind': 'follow'})
    # Simulate a process stopping after the running state was persisted.
    with sqlite3.connect(db) as con:
        con.execute('UPDATE tasks SET status=? WHERE id=?', ('running', task['id']))
    with TestClient(create_app(db)) as c:
        assert c.get('/api/learning/tasks/' + task['id']).json()['task']['status'] == 'needs_review'
        assert len(c.get('/api/learning/state').json()['users']) == 2
        assert len(c.get('/api/learning/state').json()['actions']) == 1


def test_validation_and_local_origin_boundary(client):
    assert client.post('/api/learning/tasks', json={'keyword': '  ', 'source': 'demo'}).status_code == 422
    assert client.post('/api/learning/tasks', json={'keyword': 'a' * 81, 'source': 'demo'}).status_code == 422
    assert client.post('/api/learning/tasks', json={'keyword': 'x', 'source': 'demo'}, headers={'Origin': 'https://example.com'}).status_code == 403
    assert client.post('/api/learning/actions', json={'source': 'demo', 'user_id': 'missing', 'kind': 'follow'}).status_code == 404
    assert client.get('/api/learning/tasks/missing').status_code == 404


def test_current_page_requires_an_existing_tool_browser(client):
    response = client.post('/api/learning/browser/read-current')
    assert response.status_code == 409
    assert client.get('/api/learning/state').json()['tasks'] == []


def test_later_import_does_not_rewrite_prior_task_export(client):
    record = {'aweme_id': 'v1', 'comment_id': 'c1', 'user_id': 'u1', 'nickname': '原昵称', 'content': '第一次看到的内容'}
    first = client.post('/api/learning/import', json={'records': [record]}).json()['id']
    record.update(nickname='新昵称', content='后来更新的内容')
    second = client.post('/api/learning/import', json={'records': [record]}).json()['id']
    old = client.get('/api/learning/export/' + first).json()
    new = client.get('/api/learning/export/' + second).json()
    assert old['comments'][0]['content'] == '第一次看到的内容'
    assert old['users'][0]['nickname'] == '原昵称'
    assert new['comments'][0]['content'] == '后来更新的内容'
    assert len(client.get('/api/learning/state').json()['users']) == 1
