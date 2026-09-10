import pytest
from playwright.sync_api import sync_playwright


def test_counts_keep_missing_distinct_from_zero_and_units():
    from learning.video_metadata import parse_count
    assert parse_count('1.2万') == 12000
    assert parse_count('2.3亿') == 230000000
    assert parse_count('1,234') == 1234
    assert parse_count('0') == 0
    for value in ['点赞', '--', '12:34', '-1', '第12条', '1.2.3', None]:
        assert parse_count(value) is None
    from learning.video_metadata import search_card_fields
    assert search_card_fields(['00:10','12','@提及对象','标题文字','@真正作者','2天前'])['author']=='@真正作者'


def test_detail_ignores_recommendations_comment_likes_and_wrong_video():
    from learning.video_metadata import read_video_detail
    from learning.browser import PagePaused
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,channel='chromium')
        page=browser.new_page()
        page.route('**/*',lambda r:r.fulfill(content_type='text/html',body='''<meta charset="utf-8">
          <main data-e2e="video-detail"><div data-e2e="detail-video-info"><h1>测试视频 #露营</h1>
          <a data-e2e="video-author" href="https://www.douyin.com/user/tester">@测试作者</a></div>
          <button aria-label="点赞 1.2万">1.2万</button><button aria-label="评论 0">0</button>
          <button aria-label="收藏 89">89</button><button aria-label="分享 15">15</button>
          <div data-e2e="detail-video-publish-time">发布时间：2026-09-09 12:30</div>
          <div data-e2e="comment-list"><button aria-label="点赞 999999">999999</button></div></main>
          <aside data-e2e="related-video"><button aria-label="播放 999999">999999</button></aside>'''))
        page.goto('https://www.douyin.com/video/123')
        result=read_video_detail(page,'123')
        assert result['metrics']['digg_count']['value']==12000
        assert result['metrics']['comment_count']['value']==0
        assert result['metrics']['collect_count']['value']==89
        assert 'play_count' not in result['metrics']
        assert result['author']=='@测试作者'
        assert result['published_at'].startswith('2026-09-09T12:30')
        page.locator('[data-e2e="detail-video-info"]').evaluate('''e=>e.insertAdjacentHTML('beforeend','<a href="/user/mentioned">@提及对象</a>')''')
        page.locator('[data-e2e="video-detail"]').evaluate('''e=>e.insertAdjacentHTML('beforeend','<aside data-e2e="related-video"><div data-e2e="user-info"><a href="/user/real-author"><div data-click-from="title"><span>真实作者</span><div data-e2e="badge-role-name">公司名称</div></div></a></div></aside>')''')
        assert read_video_detail(page,'123')['author']=='真实作者'
        with pytest.raises(PagePaused): read_video_detail(page,'999')
        page.set_content('<p>安全验证</p>')
        with pytest.raises(PagePaused): read_video_detail(page,'123')
        browser.close()


@pytest.mark.parametrize('stop',['verification','cancel'])
def test_metadata_worker_preserves_results_and_stops_remaining(tmp_path,monkeypatch,stop):
    from learning import browser as module, video_metadata
    from learning.store import Store
    store=Store(tmp_path/'worker.db');task=store.create_task('测试','live')
    reader=module.BrowserReader(tmp_path/'profile');visited=[]
    class Locator:
        def count(self): return 1
        def locator(self,*args): return self
        @property
        def first(self): return self
        def get_attribute(self,*args): return page.url.rsplit('/',1)[-1]
    class Page:
        def goto(self,url,**kw): self.url=url;visited.append(url)
        def locator(self,*args):return Locator()
        def wait_for_timeout(self,*args):pass
    page=Page();reader.page=page;reader.busy=True
    monkeypatch.setattr(reader,'_ensure_browser',lambda:None)
    def check(p):
        if len(visited)==2:
            if stop=='verification':raise module.PagePaused('waiting_verification','验证')
            store.cancel(task['id'])
    monkeypatch.setattr(module,'check_page',check)
    monkeypatch.setattr(video_metadata,'read_video_detail',lambda p,id:dict(id=id,metrics={'digg_count':{'value':42}},metadata_status='read'))
    try:
        reader._run_video_metadata(store,task,[{'id':str(i)} for i in (12345,23456,34567)])
        result=store.result(task['id'])
        assert result['task']['status']==('waiting_verification' if stop=='verification' else 'cancelled')
        assert result['videos'][0]['metrics']['digg_count']['value']==42
        assert result['videos'][1]['metadata_status']=='pending'
        assert len(visited)==2 and not reader.busy
    finally:reader.pool.shutdown(wait=True)


def test_search_saves_card_metrics_without_treating_title_numbers_as_counts():
    from learning.browser import read_search
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,channel='chromium'); page=browser.new_page()
        page.set_content('''<div id="waterfall_item_123">00:09<br>1.2万<br>2026年省下5000元<br>@测试作者<br>2天前</div>
        <div id="waterfall_item_456">00:20<br>2026年故事<br>@另一作者</div>''')
        videos=read_search(page)
        assert videos[0]['metrics']['digg_count']['value']==12000
        assert videos[0]['duration_seconds']==9
        assert videos[0]['published_text']=='2天前'
        assert not videos[1].get('metrics')
        browser.close()


def test_metadata_api_rejects_foreign_ids_imports_and_busy_browser(tmp_path):
    from fastapi.testclient import TestClient
    from learning.app import create_app
    with TestClient(create_app(tmp_path/'data.db')) as api:
        store=api.app.state.store
        parent=store.create_task('测试','live'); store.finish(parent['id'],{'videos':[{'id':'12345','title':'测试'}]},'success','完成')
        imported=store.create_task('导入','import');store.finish(imported['id'],{'videos':[{'id':'12345','title':'测试'}]},'success','完成')
        calls=[]
        class Reader:
            def close(self): pass
            def submit_video_metadata(self,*args): calls.append(args);raise ValueError('浏览器正忙')
        api.app.state.reader=Reader()
        url='/api/learning/tasks/'+parent['id']+'/video-metadata'
        assert api.post(url,json={'video_ids':[]}).status_code==422
        assert api.post(url,json={'video_ids':['99999']}).status_code==400
        assert api.post('/api/learning/tasks/'+imported['id']+'/video-metadata',json={'video_ids':['12345']}).status_code==409
        assert not calls
        assert api.post(url,json={'video_ids':['12345','12345']}).status_code==409
        assert len(calls[0][2])==1
        assert len(store.snapshot()['tasks'])==2


def test_import_metrics_preserve_zero_and_reject_invalid():
    from learning.service import import_records
    v=import_records([{'aweme_id':'12345','title':'测试','digg_count':'1.2万','comment_count':0,'play_count':'未公开'}])['videos'][0]
    assert v['metrics']['digg_count']['value']==12000
    assert v['metrics']['comment_count']['value']==0
    assert 'play_count' not in v['metrics']


def test_verified_four_item_toolbar_missing_and_identity_guard():
    from learning.video_metadata import read_video_detail
    from learning.browser import PagePaused
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,channel='chromium');page=browser.new_page()
        page.route('**/*',lambda r:r.fulfill(content_type='text/html',body='<meta charset="utf-8"><main data-e2e="video-detail"><section data-e2e="detail-video-info" data-e2e-aweme-id="12345"><h1>测试</h1><div id="toolbar">'+''.join(f'<div {"data-e2e=video-share-icon-container" if i==3 else ""}><div data-popupid="tip{i}"><svg></svg></div><span>{text}</span></div>' for i,text in enumerate(['19','抢首评','收藏','2']))+'</div></section></main>'))
        page.goto('https://www.douyin.com/video/12345')
        metrics=read_video_detail(page,'12345')['metrics']
        assert {k:v['value'] for k,v in metrics.items()}=={'digg_count':19,'share_count':2}
        page.locator('#toolbar').evaluate('e=>e.prepend(e.lastElementChild)')
        assert not read_video_detail(page,'12345')['metrics']
        page.locator('[data-e2e=detail-video-info]').evaluate("e=>e.setAttribute('data-e2e-aweme-id','99999')")
        with pytest.raises(PagePaused): read_video_detail(page,'12345')
        browser.close()
