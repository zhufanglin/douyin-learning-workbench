import pytest
from fastapi.testclient import TestClient
from learning.app import create_app
from learning.store import Store
from learning import browser as module


def test_batch_claim_is_durable_and_duplicate_requests_do_not_advance(tmp_path):
    store = Store(tmp_path / 'test.db')
    task = store.create_task('comments', 'live')
    data = {'videos': [{'id': '123'}], 'comments': [{'id': str(i), 'comment_rank': i + 1} for i in range(100)],
            'pagination': {'video_id': '123', 'revision': 0, 'target': 100, 'exhausted': False}}
    store.finish(task['id'], data, 'success', 'batch')
    store.begin_comment_batch(task['id'], 0)
    with pytest.raises(ValueError):
        store.begin_comment_batch(task['id'], 0)
    restored = Store(store.path)
    restored.recover()
    result = restored.result(task['id'])
    assert result['pagination']['target'] == 200
    assert result['pagination']['revision'] == 1
    assert [c['comment_rank'] for c in result['comments']] == list(range(1, 101))
    restored.begin_comment_batch(task['id'], 1)
    assert restored.result(task['id'])['pagination']['target'] == 200


def test_pagination_api_rejects_stale_revision_and_exhausted(tmp_path, monkeypatch):
    app = create_app(tmp_path / 'test.db')
    store = app.state.store
    task = store.create_task('comments', 'live')
    store.finish(task['id'], {'videos': [{'id': '123'}], 'pagination': {
        'video_id': '123', 'revision': 0, 'target': 100, 'exhausted': False}}, 'partial', 'paused')
    calls = []
    monkeypatch.setattr(module.BrowserReader, 'submit', lambda self, store, task, **kw: calls.append(kw))
    with TestClient(app) as client:
        path = f"/api/learning/tasks/{task['id']}/comments/next"
        assert client.post(path, json={'revision': 0}).status_code == 200
        assert client.post(path, json={'revision': 0}).status_code == 409
        assert len(calls) == 1
        data = store.result(task['id'])
        data['pagination']['exhausted'] = True
        store.finish(task['id'], data, 'success', 'end')
        assert client.post(path, json={'revision': 1}).status_code == 409


def test_collector_100_100_5_and_never_confuses_stall_with_end(monkeypatch):
    class Page:
        url = 'https://www.douyin.com/video/123'
        def wait_for_timeout(self, ms): pass
    monkeypatch.setattr(module, 'check_page', lambda p: None)
    monkeypatch.setattr(module, 'scroll_comments', lambda p: None)
    end = [False]
    monkeypatch.setattr(module, 'comments_ended', lambda p: end[0])
    monkeypatch.setattr(module, 'read_comments', lambda *a, **kw: {
        'comments': [{'id': str(i), 'user_id': 'u', 'video_id': '123'} for i in range(205)],
        'users': [{'id': 'u'}]})
    data = {'comments': [], 'users': [], 'pagination': {'target': 100, 'exhausted': False}}
    for target in (100, 200):
        data['pagination']['target'] = target
        module.collect_comments(Page(), '123', data, lambda: None, lambda: False)
        assert len(data['comments']) == target
    data['pagination']['target'] = 300
    with pytest.raises(module.PagePaused) as error:
        module.collect_comments(Page(), '123', data, lambda: None, lambda: False)
    assert error.value.status == 'partial'
    assert not data['pagination']['exhausted']
    assert len(data['comments']) == 205
    assert len(data['users']) == 1
    end[0] = True
    module.collect_comments(Page(), '123', data, lambda: None, lambda: False)
    assert data['pagination']['exhausted']
    assert len({c['id'] for c in data['comments']}) == 205
    Page.url = 'https://www.douyin.com/video/456'
    with pytest.raises(module.PagePaused) as error:
        module.collect_comments(Page(), '123', data, lambda: None, lambda: False)
    assert error.value.status == 'needs_review'


def test_resume_can_scroll_through_saved_rows_before_finding_new_comments(monkeypatch):
    class Page:
        url = 'https://www.douyin.com/video/123'
        def wait_for_timeout(self, ms): pass
    monkeypatch.setattr(module, 'check_page', lambda p: None)
    monkeypatch.setattr(module, 'scroll_comments', lambda p: None)
    monkeypatch.setattr(module, 'comments_ended', lambda p: False)
    window = [0]
    def read(*args, **kw):
        window[0] += 20
        return {'comments': [{'id': str(i), 'user_id': 'u'} for i in range(window[0])], 'users': [{'id': 'u'}]}
    monkeypatch.setattr(module, 'read_comments', read)
    data = {'comments': [{'id': str(i), 'user_id': 'u'} for i in range(200)], 'users': [{'id': 'u'}],
            'pagination': {'target': 300, 'exhausted': False}}
    module.collect_comments(Page(), '123', data, lambda: None, lambda: False)
    assert len(data['comments']) == 300
    assert window[0] == 300
