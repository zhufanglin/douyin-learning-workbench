from fastapi.testclient import TestClient
from learning.app import create_app


def test_catalog_preserves_history_memberships_and_source_identity(tmp_path):
    with TestClient(create_app(tmp_path / 'db')) as client:
        store = client.app.state.store
        def save(source, keyword, video, content):
            task = store.create_task(keyword, source)
            store.finish(task['id'], dict(videos=[dict(id=video, title=keyword)],
                users=[dict(id='u', nickname=keyword)],
                comments=[dict(id='c'+video, video_id=video, user_id='u', content=content)]), 'success', '保存')
            return task['id']
        first = save('live', '旧任务', 'v1', '旧正文')
        second = save('live', '新任务', 'v1', '新正文')
        save('live', '第二视频', 'v2', '另一条')
        save('import', '导入', 'v1', '导入正文')
        save('demo', '隐藏样例', 'v1', '样例')
        for i in range(101):
            store.create_task(str(i), 'live')
        response = client.get('/api/learning/catalog')
        assert response.status_code == 200
        data = response.json()
        assert len(data['tasks']) == 105
        assert len(data['users']) == 2
        assert len(data['comments']) == 3
        assert all(t['source'] != 'demo' for t in data['tasks'])
        old = next(t for t in data['tasks'] if t['id'] == first)
        assert old['counts'] == dict(videos=1, users=1, comments=1)
        assert old['videos'][0]['title'] == '旧任务'
        comment = next(c for c in data['comments'] if c['source'] == 'live' and c['video_id'] == 'v1')
        assert set(comment['task_ids']) == {first, second}
        assert comment['content'] == '新正文'
        historical = client.get('/api/learning/catalog', params={'task_id': first}).json()
        assert historical['comments'][0]['content'] == '旧正文'
        assert len(historical['tasks']) == 1
        assert client.get('/api/learning/catalog?keyword=不存在').json()['comments'] == []
        assert client.get('/api/learning/tasks/' + first).json()['comments'][0]['content'] == '旧正文'
        with store.connect() as db:
            db.execute("UPDATE tasks SET created_at='2026-09-09T00:00:00+00:00' WHERE id=?", (first,))
        boundary = client.get('/api/learning/catalog', params={'task_id': first, 'start': '2026-09-09T00:00:00.000Z', 'end': '2026-09-10T00:00:00.000Z'})
        assert len(boundary.json()['tasks']) == 1
        assert client.get('/api/learning/catalog?start=invalid').status_code == 422
