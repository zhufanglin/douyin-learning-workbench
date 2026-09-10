import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect
from learning.app import create_app

URL=os.environ.get('LEARNING_UI_URL')
pytestmark=pytest.mark.skipif(not URL,reason='Set LEARNING_UI_URL')


def test_metric_order_unknown_last_details_and_batch_selection(tmp_path):
    with TestClient(create_app(tmp_path/'ui.db')) as api:
        store=api.app.state.store;t=store.create_task('视频指标 · 本地测试','live')
        videos=[]
        for i,n in enumerate([900,12000,None,0]):
            metrics={k:dict(value=n,observed_at='2026-09-10T00:00:00Z') for k in ['digg_count','comment_count','collect_count','share_count','play_count','danmaku_count']} if n is not None else {}
            videos.append(dict(id=str(10000+i),title='本地测试视频 '+str(i),author='虚构作者',search_rank=i+1,metrics=metrics,duration_seconds=i+10))
        store.finish(t['id'],{'videos':videos},'success','隔离样例，未访问平台')
        writes=[];errors=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,channel='chromium');page=browser.new_page(viewport=dict(width=1440,height=1000))
            def route(r):
                path='/api/learning/'+r.request.url.split('/api/learning/')[1]
                if r.request.method!='GET': writes.append(path);r.fulfill(status=409,json={'detail':'禁止测试写入'});return
                result=api.get(path);r.fulfill(status=result.status_code,body=result.content,content_type='application/json')
            page.route('**/api/learning/**',route);page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(URL+'#videos?task='+t['id'])
            rows=page.locator('[aria-label="视频列表"] .record-title')
            expect(rows).to_have_count(4)
            for metric in ['digg_count','comment_count','collect_count','share_count','play_count','danmaku_count']:
                page.get_by_label('视频排序方式',exact=True).select_option(metric)
                expect(rows).to_have_text(['本地测试视频 1','本地测试视频 0','本地测试视频 3','本地测试视频 2'])
                page.get_by_label('视频排序方向',exact=True).select_option('asc')
                expect(rows).to_have_text(['本地测试视频 3','本地测试视频 0','本地测试视频 1','本地测试视频 2'])
            page.get_by_label('视频排序方式',exact=True).select_option('duration_seconds')
            expect(rows.first).to_have_text('本地测试视频 3')
            page.get_by_label('视频排序方式',exact=True).select_option('search_rank')
            expect(rows.first).to_have_text('本地测试视频 0')
            page.locator('[aria-label="视频列表"] button').filter(has_text='本地测试视频 3').click()
            info=page.get_by_label('视频信息',exact=True)
            expect(info).to_contain_text('13 秒')
            expect(info.locator('.video-stats b').first).to_have_text('0')
            page.get_by_role('button',name='返回已存视频',exact=True).click()
            page.locator('.library-group summary').click()
            page.get_by_role('button',name='选择',exact=True).click()
            selected=page.get_by_role('checkbox',name='选择本地测试视频 0',exact=True);selected.check()
            page.get_by_label('视频排序方式',exact=True).select_option('digg_count')
            expect(selected).to_be_checked()
            expect(page.get_by_role('button',name='补充视频信息',exact=True)).to_be_enabled()
            folder=Path(os.environ.get('LEARNING_EVIDENCE_DIR',str(tmp_path)));folder.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(folder/'video-metrics-desktop.png'))
            page.set_viewport_size(dict(width=390,height=844))
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            page.locator('.video-sort-bar').scroll_into_view_if_needed()
            page.screenshot(path=str(folder/'video-metrics-mobile.png'))
            assert not writes and not errors
            browser.close()
