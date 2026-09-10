import pytest
from learning.store import Store


@pytest.mark.parametrize('ending', ['complete', 'unsupported', 'blocked'])
def test_reply_end_distinguishes_unsupported_rows_from_loading_stall(tmp_path, monkeypatch, ending):
    from playwright.sync_api import sync_playwright
    from learning.browser import PagePaused, read_comments
    from learning.replies import collect_replies
    extra = '''<div data-e2e="comment-item"><a href="https://www.douyin.com/user/emoji">表情作者</a>
      <span data-e2e="comment-content"><img alt="" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"></span></div>
      <div data-e2e="comment-item"><a href="https://www.douyin.com/user/photo">图片作者</a><img alt="评论图片"></div>''' if ending == 'unsupported' else ''
    more = '<button onclick="window.clicks++">展开更多</button><span>加载中</span>' if ending == 'blocked' else ''
    html = f'''<div data-e2e="comment-list"><section><div data-e2e="comment-item"><a href="https://www.douyin.com/user/main">主作者</a>
      <span data-e2e="comment-content">主评论</span></div><div class="replyContainer"><div data-e2e="comment-item">
      <a href="https://www.douyin.com/user/reply">回复作者</a><span data-e2e="comment-content">我看到页面显示加载中</span></div>{extra}</div>
      {more}<button>收起</button></section></div><script>window.clicks=0</script>'''
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chromium')
        page = browser.new_page()
        page.route('**/video/123', lambda route: route.fulfill(body=html, content_type='text/html;charset=utf8'))
        page.goto('https://www.douyin.com/video/123')
        wait = page.wait_for_timeout
        monkeypatch.setattr(page, 'wait_for_timeout', lambda ms: wait(20))
        data = read_comments(page, '123')
        parent = data['comments'][0]['id']
        data['pagination'] = dict(active_reply=parent, replies={parent: dict(target=100, exhausted=False)})
        if ending == 'complete':
            collect_replies(page, '123', data, lambda: None, lambda: False)
        else:
            with pytest.raises(PagePaused) as error:
                collect_replies(page, '123', data, lambda: None, lambda: False)
            assert error.value.status == 'partial'
        state = data['pagination']['replies'][parent]
        assert state['end_state'] == ending
        assert state['exhausted'] == (ending == 'complete')
        assert state['page_end'] == (ending != 'blocked')
        assert state['unsupported_count'] == (2 if ending == 'unsupported' else 0)
        assert len(data['comments']) == 2  # Unsupported rows are counted, never fabricated as comments.
        assert page.evaluate('window.clicks') <= 1
        browser.close()


def test_terminal_unsupported_reply_cannot_be_resubmitted(tmp_path):
    store = Store(tmp_path / 'db')
    task = store.create_task('test', 'live')
    data = dict(comments=[dict(id='parent', video_id='123')],
        pagination=dict(video_id='123', revision=0, target=100, exhausted=False,
            replies={'parent': dict(target=100, exhausted=False, page_end=True, end_state='unsupported', unsupported_count=2, reader_version=4)}))
    store.finish(task['id'], data, 'partial', '已到页尾，存在未支持内容')
    with pytest.raises(ValueError, match='未支持'):
        store.begin_reply_batch(task['id'], 'parent', 0)
    assert store.result(task['id'])['pagination']['revision'] == 0
    assert store.get_task(task['id'])['status'] == 'partial'


def test_emoji_reply_upgrade_preserves_existing_ids_and_deduplicates(tmp_path, monkeypatch):
    from playwright.sync_api import sync_playwright
    from learning.browser import read_comments, dom_comment_id
    from learning.replies import collect_replies
    html = '''<div data-e2e="comment-list"><section><div data-e2e="comment-item">
      <a href="https://www.douyin.com/user/main">主作者</a><span data-e2e="comment-content">主评论</span></div>
      <div class="replyContainer">
        <div data-e2e="comment-item"><a href="https://www.douyin.com/user/old">文字作者</a><span data-e2e="comment-content">旧文字</span></div>
        <div data-e2e="comment-item"><a href="https://www.douyin.com/user/emoji">表情作者</a><span data-e2e="comment-content"><img alt="[看]"><img alt="[流泪]"><img alt="[隐藏]" hidden></span></div>
        <div data-e2e="comment-item"><a href="https://www.douyin.com/user/emoji">表情作者</a><span data-e2e="comment-content">[看][流泪]</span></div>
      </div><button>收起</button></section></div>'''
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chromium')
        page = browser.new_page()
        page.route('**/video/123', lambda route: route.fulfill(body=html, content_type='text/html;charset=utf8'))
        page.goto('https://www.douyin.com/video/123')
        wait = page.wait_for_timeout
        monkeypatch.setattr(page, 'wait_for_timeout', lambda ms: wait(20))
        data = read_comments(page, '123')
        parent = data['comments'][0]['id']
        old_id = dom_comment_id('123', 'old', '旧文字', parent)
        data['comments'].append(dict(id=old_id, video_id='123', user_id='old', content='旧文字', kind='reply', parent_comment_id=parent, reply_rank=1))
        data['pagination'] = dict(video_id='123', revision=0, active_reply=parent, replies={parent: dict(target=100, exhausted=False)})
        collect_replies(page, '123', data, lambda: None, lambda: False)
        assert len(data['comments']) == 4
        assert data['comments'][1]['id'] == old_id
        emoji = next(c for c in data['comments'] if c.get('content_type') == 'emoji')
        assert emoji['content'] == '[看][流泪]'
        assert emoji['emoji_labels'] == ['[看]', '[流泪]']
        assert emoji['user_id'] == 'emoji' and emoji['parent_comment_id'] == parent
        assert len({c['id'] for c in data['comments']}) == 4  # Literal text and emoji are distinct.
        collect_replies(page, '123', data, lambda: None, lambda: False)
        assert len(data['comments']) == 4
        assert data['pagination']['replies'][parent]['reader_version'] == 4
        assert data['pagination']['replies'][parent]['exhausted']
        assert data['pagination']['replies'][parent]['unsupported_count'] == 0
        store = Store(tmp_path / 'db')
        task = store.create_task('emoji', 'live')
        store.finish(task['id'], data, 'success', 'fixture')
        assert next(c for c in store.result(task['id'])['comments'] if c['id'] == emoji['id'])['emoji_labels'] == ['[看]', '[流泪]']
        browser.close()


def test_old_unsupported_reply_can_upgrade_once_with_revision_guard(tmp_path):
    store = Store(tmp_path / 'db')
    task = store.create_task('test', 'live')
    data = dict(comments=[dict(id='parent', video_id='123')],
        pagination=dict(video_id='123', revision=0, target=100, exhausted=False,
            replies={'parent': dict(target=100, exhausted=False, page_end=True, end_state='unsupported', unsupported_count=2)}))
    store.finish(task['id'], data, 'partial', 'old reader')
    store.begin_reply_batch(task['id'], 'parent', 0)
    with pytest.raises(ValueError):
        store.begin_reply_batch(task['id'], 'parent', 0)
    result = store.result(task['id'])
    result['pagination']['replies']['parent'].update(end_state='unsupported', page_end=True)
    store.finish(task['id'], result, 'partial', 'still unsupported after upgrade')
    with pytest.raises(ValueError, match='未支持'):
        store.begin_reply_batch(task['id'], 'parent', 1)
    assert store.result(task['id'])['pagination']['revision'] == 1


@pytest.mark.parametrize('kind', ['timeout', 'verification'])
def test_reply_interruption_marks_reviewable_state_without_losing_data(tmp_path, monkeypatch, kind):
    from types import SimpleNamespace
    from learning import browser as module
    store = Store(tmp_path / 'db')
    task = store.create_task('test', 'live')
    data = dict(comments=[dict(id='parent', video_id='123')], pagination=dict(video_id='123', target=100, exhausted=False, revision=0))
    store.finish(task['id'], data, 'success', 'existing data')
    task = store.begin_reply_batch(task['id'], 'parent', 0)
    reader = module.BrowserReader(tmp_path / 'browser')
    reader.page = SimpleNamespace(is_closed=lambda: False)
    monkeypatch.setattr(reader, '_ensure_browser', lambda: None)
    monkeypatch.setattr(module, 'save_diagnostic', lambda *args: None)
    def interrupt(page):
        if kind == 'timeout': raise module.BrowserTimeout('test timeout')
        raise module.PagePaused('waiting_verification', '请本人完成验证')
    monkeypatch.setattr(module, 'check_page', interrupt)
    try:
        reader._run(store, task, current=True)
        result = store.result(task['id'])
        assert result['task']['status'] == ('failed' if kind == 'timeout' else 'waiting_verification')
        assert result['pagination']['replies']['parent']['end_state'] == 'blocked'
        assert not result['pagination']['replies']['parent']['page_end']
        assert len(result['comments']) == 1
    finally:
        reader.pool.shutdown()


def test_reply_batches_100_100_5_resume_from_store_without_mixing_discussions(tmp_path, monkeypatch):
    """Local rendered fixture only: overlapping platform pages and durable continuation."""
    from playwright.sync_api import sync_playwright
    from learning.browser import read_comments
    from learning.replies import collect_replies
    html = '''<div data-e2e="comment-list"><section><div data-e2e="comment-item">
      <a href="https://www.douyin.com/user/main">虚构主作者</a><span data-e2e="comment-content">分页主评论</span>
      <button onclick="window.sent=true">回复</button></div><div id="replies" class="replyContainer"></div>
      <button id="expand" onclick="expandReplies()"><span>展开205条回复</span></button><button id="collapse" hidden>收起</button></section>
      <section><div data-e2e="comment-item"><a href="https://www.douyin.com/user/other">其他作者</a>
      <span data-e2e="comment-content">其他讨论</span></div><button onclick="window.otherClicked=true">展开999条回复</button></section></div>
      <script>window.sent=false;window.otherClicked=false;window.loads=0;let count=0;
      function expandReplies(){window.loads++;let start=Math.max(0,count-5);count=Math.min(205,count+70);
      document.querySelector('#replies').insertAdjacentHTML('beforeend',Array.from({length:count-start},(_,j)=>{
        let i=start+j;return `<div data-e2e="comment-item"><a href="https://www.douyin.com/user/reply${i%3}">虚构回复作者${i%3}</a>
        <span data-e2e="comment-content">分页回复${i+1}</span></div>`}).join(''));
      if(count===205)document.querySelector('#expand').remove();else document.querySelector('#expand').innerHTML='<span>展开更多</span>';
      document.querySelector('#collapse').hidden=false;}</script>'''
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chromium')
        page = browser.new_page()
        page.route('**/video/123', lambda route: route.fulfill(body=html, content_type='text/html;charset=utf8'))
        page.goto('https://www.douyin.com/video/123')
        wait = page.wait_for_timeout
        monkeypatch.setattr(page, 'wait_for_timeout', lambda ms: wait(20))
        initial = read_comments(page, '123')
        parent = initial['comments'][0]['id']
        store = Store(tmp_path / 'persist.db')
        task = store.create_task('回复分页夹具', 'live')
        initial['pagination'] = dict(video_id='123', target=100, exhausted=True, revision=0)
        store.finish(task['id'], initial, 'success', 'local main list end')
        for revision, expected in enumerate((100, 200, 205)):
            store = Store(tmp_path / 'persist.db')
            store.begin_reply_batch(task['id'], parent, revision)
            data = store.result(task['id'])
            collect_replies(page, '123', data, lambda: store.finish(task['id'], data, 'running', 'fixture progress'), lambda: False)
            store.finish(task['id'], data, 'success', 'fixture batch')
            saved = Store(tmp_path / 'persist.db').result(task['id'])
            replies = [c for c in saved['comments'] if c.get('parent_comment_id')]
            assert len(replies) == expected
            assert len({c['id'] for c in replies}) == expected
            assert all(c['parent_comment_id'] == parent for c in replies)
            assert [c['reply_rank'] for c in replies] == list(range(1, expected + 1))
            assert saved['pagination']['target'] == 100 and saved['pagination']['exhausted']
            assert saved['pagination']['replies'][parent]['exhausted'] == (expected == 205)
        assert len(saved['users']) == 5
        assert page.evaluate('window.loads') == 3
        assert not page.evaluate('window.sent || window.otherClicked')
        browser.close()


def test_reply_batch_does_not_change_main_page_and_rejects_duplicate(tmp_path):
    store = Store(tmp_path / 'db')
    task = store.create_task('test', 'live')
    data = dict(videos=[dict(id='123')], comments=[dict(id='parent', video_id='123', user_id='u', content='Main')],
        pagination=dict(video_id='123', revision=0, target=100, exhausted=True))
    store.finish(task['id'], data, 'success', 'end main list')
    store.begin_reply_batch(task['id'], 'parent', 0)
    with pytest.raises(ValueError): store.begin_reply_batch(task['id'], 'parent', 0)
    result = store.result(task['id'])
    assert result['pagination']['target'] == 100
    assert result['pagination']['exhausted'] is True
    assert result['pagination']['active_reply'] == 'parent'
    assert result['pagination']['replies']['parent']['target'] == 100
    result['comments'].append(dict(id='reply', parent_comment_id='parent', kind='reply', video_id='123', user_id='u', content='reply'))
    store.finish(task['id'], result, 'partial', 'saved reply')
    with pytest.raises(ValueError): store.begin_reply_batch(task['id'], 'reply', 1)
    with pytest.raises(KeyError): store.begin_reply_batch(task['id'], 'absent', 1)
    store.begin_reply_batch(task['id'], 'parent', 1)
    assert store.result(task['id'])['pagination']['replies']['parent']['target'] == 100


def test_main_page_count_excludes_replies(tmp_path):
    store = Store(tmp_path / 'db')
    task = store.create_task('test', 'live')
    data = dict(comments=[dict(id=str(i)) for i in range(100)] + [dict(id='r'+str(i), parent_comment_id='0', kind='reply') for i in range(130)],
        pagination=dict(video_id='123', revision=0, target=100, exhausted=False, active_reply='0'))
    store.finish(task['id'], data, 'success', 'batch')
    store.begin_comment_batch(task['id'], 0)
    assert store.result(task['id'])['pagination']['target'] == 200
    assert store.result(task['id'])['pagination']['active_reply'] is None
    store.finish(task['id'], data, 'success', 'old worker completing late')
    assert store.result(task['id'])['pagination']['revision'] == 1
    assert store.get_task(task['id'])['status'] == 'running'


def test_expanding_reply_thread_preserves_parent_and_never_clicks_send(tmp_path):
    from playwright.sync_api import sync_playwright
    from learning.browser import read_comments
    from learning.replies import collect_replies
    html = '''<div data-e2e="comment-list"><section><div data-e2e="comment-item">
      <a href="https://www.douyin.com/user/main"><span>展开99条回复</span></a><span data-e2e="comment-content">主评论</span>
      <button onclick="window.sent=true">回复</button></div>
      <div id="replies" class="replyContainer"></div><button id="expand" onclick="expandReplies()">展开2条回复</button><button id="collapse" hidden>收起</button></section></div>
      <script>window.sent=false;function expandReplies(){
        document.querySelector('#replies').innerHTML=[1,2].map(i=>`<div data-e2e="comment-item"><a href="https://www.douyin.com/user/reply">回复作者</a><span data-e2e="comment-content">回复正文${i}</span></div>`).join('');
        document.querySelector('#expand').remove();document.querySelector('#collapse').hidden=false;}</script>'''
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chromium')
        page = browser.new_page()
        page.route('**/video/123', lambda route: route.fulfill(body=html, content_type='text/html;charset=utf8'))
        page.goto('https://www.douyin.com/video/123')
        data = read_comments(page, '123')
        parent = data['comments'][0]['id']
        data['pagination'] = dict(active_reply=parent, replies={parent: dict(target=100, exhausted=False)})
        collect_replies(page, '123', data, lambda: None, lambda: False)
        assert len(data['comments']) == 3
        assert len(data['users']) == 2
        assert data['pagination']['replies'][parent]['exhausted']
        assert len({c['id'] for c in data['comments']}) == 3
        assert all(c['parent_comment_id'] == parent for c in data['comments'][1:])
        assert len(read_comments(page, '123')['comments']) == 1
        assert not page.evaluate('window.sent')
        # A second visible read does not add duplicate rows.
        collect_replies(page, '123', data, lambda: None, lambda: False)
        assert len(data['comments']) == 3
        browser.close()


def test_reply_route_scopes_to_saved_parent_and_exports_relationship(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from learning.app import create_app
    from learning.browser import BrowserReader
    app = create_app(tmp_path / 'test.db')
    store = app.state.store
    task = store.create_task('test', 'live')
    store.finish(task['id'], dict(comments=[dict(id='parent', video_id='123')],
        pagination=dict(video_id='123', target=100, exhausted=True, revision=0)), 'success', 'main end')
    calls = []
    monkeypatch.setattr(BrowserReader, 'submit', lambda self, store, task, **kw: calls.append(kw))
    with TestClient(app) as client:
        path = f"/api/learning/tasks/{task['id']}/comments/parent/replies"
        assert client.post(path, json={'revision': 0}).status_code == 200
        assert client.post(path, json={'revision': 0}).status_code == 409
        assert calls == [{'direct_url': 'https://www.douyin.com/video/123'}]
        data = store.result(task['id'])
        data['comments'].append(dict(id='reply', parent_comment_id='parent', kind='reply'))
        store.finish(task['id'], data, 'success', 'reply saved')
        exported = client.get(f"/api/learning/export/{task['id']}").json()
        assert exported['comments'][1]['parent_comment_id'] == 'parent'
        assert exported['pagination']['exhausted'] is True
