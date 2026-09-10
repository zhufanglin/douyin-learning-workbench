from fastapi.testclient import TestClient
from learning.app import create_app
from learning.store import Store


def test_select_video_only_returns_its_comments_and_users(tmp_path):
    with TestClient(create_app(tmp_path / 'test.db')) as c:
        parent = c.post('/api/learning/tasks', json={'keyword': '露营', 'source': 'demo'}).json()
        response = c.post(f"/api/learning/tasks/{parent['id']}/videos/demo-video-2/comments")
        assert response.status_code == 200
        detail = c.get('/api/learning/tasks/' + response.json()['id']).json()
        assert detail['task']['status'] == 'simulated'
        assert len(detail['comments']) == 1
        assert detail['comments'][0]['video_id'] == 'demo-video-2'
        assert len(detail['users']) == 1
        assert c.post(f"/api/learning/tasks/{parent['id']}/videos/not-in-search/comments").status_code == 404
        assert len(c.get('/api/learning/tasks/' + parent['id']).json()['videos']) == 2


def test_video_order_is_search_order_not_id_order(tmp_path):
    store = Store(tmp_path / 'test.db')
    task = store.create_task('test', 'live')
    store.finish(task['id'], {'videos': [{'id': '900', 'search_rank': 1}, {'id': '100', 'search_rank': 2}]}, 'success', 'test')
    assert [v['id'] for v in store.result(task['id'])['videos']] == ['900', '100']


def test_limit_cannot_exceed_100(tmp_path):
    with TestClient(create_app(tmp_path / 'test.db')) as c:
        assert c.post('/api/learning/tasks', json={'keyword': 'test', 'limit': 101}).status_code == 422
        assert c.post('/api/learning/tasks', json={'keyword': '露营', 'limit': 100}).status_code == 200
