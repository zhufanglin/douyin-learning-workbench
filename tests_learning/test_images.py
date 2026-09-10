"""Synthetic DOM fixtures; these do not claim live Douyin image selector support."""
import json
import pytest
from playwright.sync_api import sync_playwright
from learning.browser import read_comments, collect_comments, PagePaused, dom_comment_id
from learning.replies import collect_replies
from learning.store import Store


@pytest.fixture
def page(monkeypatch):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chromium')
        page = browser.new_page()
        page.route('**/media.example/**', lambda route: route.abort())
        wait = page.wait_for_timeout
        monkeypatch.setattr(page, 'wait_for_timeout', lambda ms: wait(20))
        yield page
        browser.close()


def show(page, html):
    page.route('**/video/123', lambda route: route.fulfill(body=html, content_type='text/html;charset=utf8'))
    page.goto('https://www.douyin.com/video/123')


def test_main_image_placeholders_exclude_avatars_preserve_text_ids_and_mark_partial(page):
    show(page, '''<div data-e2e="comment-list">
      <div data-e2e="comment-item"><a href="https://www.douyin.com/user/u">作者<img src="https://media.example/avatar" alt="头像"></a>
      <span data-e2e="comment-content"><img src="https://media.example/a?token=one" alt="评论图片"></span></div>
      <div data-e2e="comment-item"><a href="https://www.douyin.com/user/u">作者</a>
      <span data-e2e="comment-content"><img src="https://media.example/a?token=two" alt="评论图片"></span></div>
      <div data-e2e="comment-item"><a href="https://www.douyin.com/user/u">作者</a><div class="RDy3JwM0"><img class="duf1cdUE WnXkj1im" src="https://media.example/b"></div></div>
      <div data-e2e="comment-item"><a href="https://www.douyin.com/user/u">作者</a>
      <span data-e2e="comment-content">旧文字<img src="https://media.example/c" alt="评论图片"><img hidden src="https://media.example/hidden"></span></div>
      <div data-e2e="comment-item"><a href="https://www.douyin.com/user/avatar">仅头像<img src="https://media.example/avatar2"></a></div>
      <p>没有更多评论了</p></div>''')
    data = read_comments(page, '123')
    assert len(data['comments']) == 3
    assert len(data['users']) == 1
    mixed = next(c for c in data['comments'] if c['content'] == '旧文字')
    assert mixed['id'] == dom_comment_id('123', 'u', '旧文字')
    assert all(c['content_status'] == 'image_not_read' and c['image_count'] == 1 for c in data['comments'])
    assert all(len(c['image_fingerprints'][0]) == 64 for c in data['comments'])
    assert 'media.example' not in json.dumps(data)
    data['pagination'] = dict(video_id='123', revision=0, target=100, exhausted=False)
    with pytest.raises(PagePaused, match='图片内容未读取'):
        collect_comments(page, '123', data, lambda: None, lambda: False)
    assert data['pagination']['exhausted']
    assert data['pagination']['image_placeholder_count'] == 3


@pytest.mark.parametrize('placement', ['body', 'explicit_image', 'observed_wrapper'])
def test_image_reply_batches_persist_placeholders_without_complete_claim(page, tmp_path, placement):
    rows = []
    for i in range(105):
        img = f'<img alt="评论图片" src="https://media.example/reply-{i}">'
        body = f'<span data-e2e="comment-content">{img}</span>' if placement == 'body' else img
        if placement == 'observed_wrapper':
            body = f'<div class="RDy3JwM0"><img class="duf1cdUE Pin1wnva" src="https://media.example/reply-{i}"></div>'
        rows.append(f'<div data-e2e="comment-item"><a href="https://www.douyin.com/user/u">图片作者</a>{body}</div>')
    show(page, '<div data-e2e="comment-list"><section><div data-e2e="comment-item"><a href="https://www.douyin.com/user/main">主作者</a><span data-e2e="comment-content">主评论</span></div><div class="replyContainer">' + ''.join(rows) + '</div><button>收起</button></section></div>')
    initial = read_comments(page, '123')
    parent = initial['comments'][0]['id']
    initial['pagination'] = dict(video_id='123', revision=0, target=100, exhausted=True)
    store = Store(tmp_path / 'db')
    task = store.create_task('图片夹具', 'live')
    store.finish(task['id'], initial, 'success', 'fixture')
    for revision, count in enumerate([100, 105]):
        store.begin_reply_batch(task['id'], parent, revision)
        data = store.result(task['id'])
        if revision:
            with pytest.raises(PagePaused, match='图片内容未读取'):
                collect_replies(page, '123', data, lambda: None, lambda: False)
        else:
            collect_replies(page, '123', data, lambda: None, lambda: False)
        store.finish(task['id'], data, 'partial' if revision else 'success', 'fixture')
        saved = Store(tmp_path / 'db').result(task['id'])
        replies = [c for c in saved['comments'] if c.get('parent_comment_id')]
        assert len(replies) == len({c['id'] for c in replies}) == count
        assert all(c['content'] == '图片内容未读取' and c['content_status'] == 'image_not_read' for c in replies)
        assert saved['pagination']['replies'][parent]['image_placeholder_count'] == count
        assert saved['pagination']['exhausted']  # Main-list completion is independent.
        assert 'media.example' not in json.dumps(saved)
    state = saved['pagination']['replies'][parent]
    assert state['end_state'] == 'unsupported' and state['page_end'] and not state['exhausted']
    assert state['unsupported_count'] == 0  # All rows represented, image content remains unread.
    with pytest.raises(ValueError):
        store.begin_reply_batch(task['id'], parent, 2)


def test_mixed_reply_adds_image_metadata_without_duplicating_saved_text(page):
    show(page, '''<div data-e2e="comment-list"><section><div data-e2e="comment-item"><a href="https://www.douyin.com/user/main">主作者</a><span data-e2e="comment-content">主评论</span></div>
      <div class="replyContainer"><div data-e2e="comment-item"><a href="https://www.douyin.com/user/u">作者</a>
      <span data-e2e="comment-content">旧回复<img src="https://media.example/mixed" alt="评论图片"></span></div></div><button>收起</button></section></div>''')
    data = read_comments(page, '123')
    parent = data['comments'][0]['id']
    old_id = dom_comment_id('123', 'u', '旧回复', parent)
    data['comments'].append(dict(id=old_id, video_id='123', user_id='u', content='旧回复', parent_comment_id=parent, reply_rank=1))
    data['pagination'] = dict(active_reply=parent, replies={parent: dict(target=100, exhausted=False)})
    with pytest.raises(PagePaused):
        collect_replies(page, '123', data, lambda: None, lambda: False)
    assert len(data['comments']) == 2
    assert data['comments'][1]['id'] == old_id and data['comments'][1]['content'] == '旧回复'
    assert data['comments'][1]['content_status'] == 'image_not_read'


def test_unidentified_main_image_keeps_incomplete_state_at_footer(page):
    show(page, '''<div data-e2e="comment-list">
      <div data-e2e="comment-item"><a href="https://www.douyin.com/user/u">作者</a><span data-e2e="comment-content">正常文字</span></div>
      <div data-e2e="comment-item"><a href="https://www.douyin.com/user/u">作者</a><img alt="评论图片"></div>
      <p>没有更多评论了</p></div>''')
    data = read_comments(page, '123')
    data['pagination'] = dict(video_id='123', revision=0, target=100, exhausted=False)
    with pytest.raises(PagePaused, match='无法保存'):
        collect_comments(page, '123', data, lambda: None, lambda: False)
    assert len(data['comments']) == 1
    assert data['pagination']['unidentified_image_count'] == 1
    assert data['pagination']['exhausted']
