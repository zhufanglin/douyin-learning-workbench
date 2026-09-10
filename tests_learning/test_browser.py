import pytest
from playwright.sync_api import sync_playwright
from learning.browser import PagePaused, read_search, read_comments
from learning.store import Store


@pytest.fixture(scope='module')
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chromium')
        page = browser.new_page()
        yield page
        browser.close()


def test_visible_search_links_are_deduped_and_offsite_links_ignored(page):
    page.set_content('''<a href="https://www.douyin.com/video/123">露营示例</a>
        <a href="https://www.douyin.com/video/123">重复入口</a>
        <a href="https://evil.example/video/888">外站</a>
        <a style="display:none" href="https://www.douyin.com/video/999">隐藏</a>''')
    videos = read_search(page)
    assert len(videos) == 1
    assert videos[0]['id'] == '123'
    assert videos[0]['title'] == '露营示例'


def test_search_excludes_explicit_photo_cards_including_video_shaped_links(page):
    page.set_content('''<div id="waterfall_item_111">图文<br>10万<br><a href="https://www.douyin.com/video/111">图片帖子</a><br>@虚构作者</div>
        <div id="waterfall_item_222">00:09<br>20万<br><a href="https://www.douyin.com/video/222">图文制作教程（这是视频标题）</a><br>@虚构作者</div>
        <div id="waterfall_item_333">图文<br>3万<br>没有链接的图片帖子<br>@虚构作者</div>
        <div id="waterfall_item_444">相关搜索<br><a href="https://www.douyin.com/video/444">推荐词</a></div>
        <div id="waterfall_item_555">1 / 1<br>没有图文标签的图片</div>''')
    results = read_search(page)
    assert [v['id'] for v in results] == ['222']
    assert '图文制作教程' in results[0]['title']
    assert results[0]['duration'] == '00:09'
    assert results[0]['content_type'] == 'video'


def test_verification_pauses_before_reading_and_hidden_prompts_do_not_block(page):
    page.set_content('<main>安全验证：请完成下方验证</main><a href="https://www.douyin.com/video/123">测试</a>')
    with pytest.raises(PagePaused) as error:
        read_search(page)
    assert error.value.status == 'waiting_verification'
    page.set_content('<div hidden>安全验证</div><a href="https://www.douyin.com/video/123">测试</a>')
    assert len(read_search(page)) == 1


def test_login_dialog_and_unknown_layout_are_not_reported_success(page):
    page.set_content('<div role="dialog">请登录后查看</div>')
    with pytest.raises(PagePaused) as error:
        read_search(page)
    assert error.value.status == 'waiting_login'
    page.set_content('<main>尚未识别的页面结构</main>')
    with pytest.raises(PagePaused) as error:
        read_search(page)
    assert error.value.status == 'pending_layout'


def test_comments_only_collect_explicit_visible_comment_rows(page):
    page.set_content('''<div data-e2e="comment-item"><a href="https://www.douyin.com/user/abc">小林</a>
        <span data-e2e="comment-content">想了解帐篷</span></div>
        <div data-e2e="comment-item"><a href="https://www.douyin.com/user/abc">小林</a>
        <span data-e2e="comment-content">想了解帐篷</span></div>
        <div><a href="https://www.douyin.com/user/other">推荐作者，不是评论者</a></div>''')
    result = read_comments(page, '123')
    assert len(result['comments']) == 1
    assert result['users'][0]['id'] == 'abc'
    assert result['comments'][0]['content'] == '想了解帐篷'


def test_cancelled_task_does_not_accept_late_results(tmp_path):
    store = Store(tmp_path / 'tasks.db')
    task = store.create_task('test', 'live')
    store.cancel(task['id'])
    store.finish(task['id'], {'users': [{'id': 'late'}]}, 'success', 'finished')
    assert store.result(task['id'])['users'] == []
    assert store.get_task(task['id'])['status'] == 'cancelled'


def test_pause_diagnostic_saves_and_serves_actual_browser_image(page, tmp_path):
    from fastapi.testclient import TestClient
    from learning.app import create_app
    from learning import browser as browser_module
    app = create_app(tmp_path / 'test.db')
    store = app.state.store
    task = store.create_task('test', 'live')
    page.set_content('<title>读取诊断</title><main>页面尚未加载完成</main>')
    assert hasattr(browser_module, 'save_diagnostic'), 'Pause diagnostic capture is missing'
    browser_module.save_diagnostic(page, store, task['id'])
    with TestClient(app) as client:
        result = client.get('/api/learning/tasks/' + task['id']).json()
        response = client.get(result['screenshot_url'])
        assert response.status_code == 200
        assert response.content.startswith(b'\x89PNG\r\n\x1a\n')
        assert response.headers['cache-control'] == 'no-store'
        assert client.get('/api/learning/tasks/unknown/screenshot').status_code == 404


def test_screenshot_timeout_preserves_visible_text(page, tmp_path, monkeypatch):
    import json
    from playwright.sync_api import TimeoutError
    from learning.browser import save_diagnostic
    store = Store(tmp_path / 'tasks.db')
    task = store.create_task('test', 'live')
    page.set_content('<title>诊断</title><main>页面加载失败</main>')
    def timeout(**kwargs):
        raise TimeoutError('Screenshot timeout')
    monkeypatch.setattr(page, 'screenshot', timeout)
    save_diagnostic(page, store, task['id'])
    info = json.loads((tmp_path / 'diagnostics' / f"{task['id']}.json").read_text(encoding='utf-8'))
    assert info['visible_text'] == '页面加载失败'
    assert info['screenshot_error'] == 'TimeoutError'


def test_current_video_accepts_search_modal_and_rejects_ambiguous_ids():
    from learning.browser import current_video_id
    assert current_video_id('https://www.douyin.com/search/test?modal_id=123') == '123'
    assert current_video_id('https://www.douyin.com/video/123') == '123'
    assert current_video_id('https://www.douyin.com/video/123?modal_id=456') == '456'
    assert current_video_id('https://www.douyin.com/search/test?modal_id=123&modal_id=456') is None
    assert current_video_id('https://www.douyin.com/search/test?modal_id=abc') is None
    assert current_video_id('https://evil.example/search/test?modal_id=123') is None


def test_explicit_video_request_validates_before_opening(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from learning.app import create_app
    from learning.browser import BrowserReader
    calls = []
    monkeypatch.setattr(BrowserReader, 'submit', lambda self, store, task, **kwargs: calls.append(kwargs))
    with TestClient(create_app(tmp_path / 'test.db')) as client:
        assert client.post('/api/learning/browser/open-video', json={'url': 'https://evil.example/video/123'}).status_code == 422
        response = client.post('/api/learning/browser/open-video', json={'url': 'https://www.douyin.com/search/test?modal_id=123'})
        assert response.status_code == 200
        assert response.json()['source'] == 'live'
        assert calls == [{'direct_url': 'https://www.douyin.com/video/123'}]


def test_current_modal_task_saves_comments_without_navigation(page, tmp_path, monkeypatch):
    from learning.browser import BrowserReader
    url = 'https://www.douyin.com/search/fixture?modal_id=123'
    page.route('**/search/fixture*', lambda route: route.fulfill(body='''<div data-e2e="comment-list"><div data-e2e="comment-item">
        <a href="https://www.douyin.com/user/test">测试用户</a>
        <span data-e2e="comment-content">本地测试评论</span></div><p>没有更多评论了</p></div>''', content_type='text/html; charset=utf-8'))
    page.goto(url)
    reader = BrowserReader(tmp_path / 'profile')
    reader.page = page
    monkeypatch.setattr(reader, '_ensure_browser', lambda: None)
    store = Store(tmp_path / 'tasks.db')
    task = store.create_task('current', 'live')
    try:
        reader._run(store, task, current=True)
        result = store.result(task['id'])
        assert result['task']['status'] == 'success'
        assert result['videos'][0]['id'] == '123'
        assert result['comments'][0]['content'] == '本地测试评论'
        assert page.url == url
    finally:
        reader.pool.shutdown()
        page.unroute('**/search/fixture*')


def test_observed_comment_layout_uses_named_link_and_only_body_text(page):
    # Structure observed on 2026-09-09; all people, IDs and words replaced with fixtures.
    page.set_content('''<div data-e2e="comment-item">
        <div class="comment-item-avatar"><a href="https://www.douyin.com/user/fixture"><img alt=""></a></div>
        <div><div class="comment-item-info-wrap"><a href="https://www.douyin.com/user/fixture">测试昵称</a></div>
        <div data-e2e="video-comment-more"><div class="fBKZfpyn">...</div></div>
        <div class="FduGc_lz"><span class="Sh1Da424"><span>这是测试正文</span></span></div>
        <div>2小时前</div><div class="comment-item-stats-container">分享 回复</div></div></div>''')
    result = read_comments(page, '123')
    assert result['comments'][0]['content'] == '这是测试正文'
    assert result['users'][0]['nickname'] == '测试昵称'


def test_collect_search_caps_100_and_keeps_search_order(page):
    from learning.browser import collect_search
    page.set_content(''.join(f'<a href="https://www.douyin.com/video/{1000-i}">视频{i}</a>' for i in range(110)))
    data = {'videos': [], 'comments': [], 'users': []}
    collect_search(page, data, 100, lambda: None, lambda: False)
    assert len(data['videos']) == 100
    assert data['videos'][0]['id'] == '1000'
    assert data['videos'][-1]['search_rank'] == 100
    assert data['comments'] == []


def test_collect_search_keeps_partial_results_when_verification_appears(page):
    from learning.browser import collect_search
    page.set_content('<a href="https://www.douyin.com/video/123">测试</a>')
    data = {'videos': [], 'comments': [], 'users': []}
    with pytest.raises(PagePaused) as error:
        collect_search(page, data, 100, lambda: page.set_content('<div>安全验证</div>'), lambda: False)
    assert error.value.status == 'waiting_verification'
    assert len(data['videos']) == 1


def test_observed_search_cards_provide_real_ids_without_links(page):
    page.set_content('''<div id="waterfall_item_123">00:30<br>10万<br>测试露营标题<br>@测试作者<br>今天</div>
        <div id="waterfall_item_123">重复卡片</div><div id="waterfall_item_bad">未知编号</div>''')
    result = read_search(page)
    assert len(result) == 1
    assert result[0]['id'] == '123'
    assert result[0]['title'] == '测试露营标题'
    assert result[0]['author'] == '@测试作者'


def test_search_task_does_not_open_videos_or_read_comments(page, tmp_path, monkeypatch):
    from learning import browser as module
    page.route('**/search/search-only-fixture', lambda route: route.fulfill(body='''
        <meta charset="utf-8"><button onclick="history.replaceState({},'', '?type=video')">视频</button><div id="waterfall_item_456">00:10<br>Fixture A</div><div id="waterfall_item_123">00:20<br>Fixture B</div>''', content_type='text/html'))
    reader = module.BrowserReader(tmp_path / 'profile')
    reader.page = page
    monkeypatch.setattr(reader, '_ensure_browser', lambda: None)
    def unexpected(*args):
        raise AssertionError('Search must not read comments')
    monkeypatch.setattr(module, 'read_comments', unexpected)
    store = Store(tmp_path / 'test.db')
    task = store.create_task('search-only-fixture', 'live')
    try:
        reader._run(store, task, current=False, limit=2)
        result = store.result(task['id'])
        assert result['task']['status'] == 'success'
        assert [v['id'] for v in result['videos']] == ['456', '123']
        assert result['comments'] == []
        assert page.url.endswith('/search/search-only-fixture?type=video')
    finally:
        reader.pool.shutdown()
        page.unroute('**/search/search-only-fixture')


def test_comment_scrolling_loads_later_rows_and_ignores_end_words_inside_comments(page, monkeypatch):
    from learning import browser as module
    html = '''<div data-e2e="comment-list" style="height:250px;overflow:auto"></div><script>
      const list=document.querySelector('[data-e2e="comment-list"]'); let count=0;
      function add(){for(let i=0;i<20&&count<105;i++,count++)list.insertAdjacentHTML('beforeend',
        `<div data-e2e="comment-item" style="height:50px"><a href="https://www.douyin.com/user/u">用户</a>
        <span data-e2e="comment-content">评论${count}<span>没有更多了</span></span></div>`);
        if(count===105&&!document.querySelector('footer'))list.insertAdjacentHTML('beforeend','<footer>没有更多评论了</footer>');}
      add(); list.addEventListener('scroll',()=>{if(list.scrollTop+list.clientHeight>=list.scrollHeight-60)add()});
      </script>'''
    page.route('**/video/123', lambda route: route.fulfill(body=html, content_type='text/html; charset=utf-8'))
    page.goto('https://www.douyin.com/video/123')
    assert not module.comments_ended(page)
    wait = page.wait_for_timeout
    monkeypatch.setattr(page, 'wait_for_timeout', lambda ms: wait(50))
    data = {'comments': [], 'users': [], 'pagination': {'target': 100, 'exhausted': False}}
    try:
        module.collect_comments(page, '123', data, lambda: None, lambda: False)
        assert len(data['comments']) == 100
        assert not data['pagination']['exhausted']
        data['pagination']['target'] = 200
        module.collect_comments(page, '123', data, lambda: None, lambda: False)
        assert len(data['comments']) == 105
        assert data['pagination']['exhausted']
    finally:
        page.unroute('**/video/123')


def test_observed_real_end_phrase_only_counts_outside_comment_content(page):
    from learning.browser import comments_ended
    page.set_content('<div data-e2e="comment-list"><div data-e2e="comment-item"><span>暂时没有更多评论</span></div></div>')
    assert not comments_ended(page)
    page.set_content('<div data-e2e="comment-list"><div>暂时没有更多评论</div></div>')
    assert comments_ended(page)
