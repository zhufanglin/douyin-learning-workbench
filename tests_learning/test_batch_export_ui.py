import os
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect
from learning.app import create_app

URL=os.environ.get('LEARNING_UI_URL')
pytestmark=pytest.mark.skipif(not URL,reason='Set LEARNING_UI_URL')

def test_selected_export_and_download_feedback_without_row_delete(tmp_path):
    with TestClient(create_app(tmp_path/'d.db')) as api:
        store=api.app.state.store
        task=store.create_task('导出与下载测试','live')
        store.finish(task['id'], {'videos':[dict(id='12345',title='测试视频一'),dict(id='23456',title='测试视频二')]},'success','完成')
        class Reader:
            def close(self): pass
            def preview_snapshot(self, **kwargs): return {'status':'idle'}
            def submit_downloads(self,manager,identity):
                manager.update_item(identity,0,status='unavailable',note='页面没有下载入口')
                manager.finish(identity,'completed','处理完毕')
        api.app.state.reader=Reader()
        writes=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,channel='chromium'); page=browser.new_page(viewport=dict(width=1366,height=900))
            def route(r):
                path='/api/learning/'+r.request.url.split('/api/learning/')[1]
                if r.request.method=='POST':
                    writes.append((path,r.request.post_data_json))
                    response=api.post(path,json=r.request.post_data_json)
                else: response=api.get(path)
                r.fulfill(status=response.status_code,body=response.content,headers={'Content-Type':response.headers.get('content-type','application/json')})
            page.route('**/api/learning/**',route)
            page.goto(URL.split('#')[0]+'#videos')
            page.locator('.library-group summary').first.click()
            expect(page.get_by_role('button',name='删除测试视频一',exact=True)).to_have_count(0)
            expect(page.get_by_role('checkbox')).to_have_count(0)
            page.get_by_role('button',name='选择',exact=True).click()
            page.get_by_role('checkbox',name='选择测试视频一',exact=True).check()
            with page.expect_download() as info:
                page.get_by_role('button',name='导出 JSON',exact=True).click()
            file=tmp_path/'selected.json'; info.value.save_as(file)
            data=json.loads(file.read_text(encoding='utf-8'))
            assert [r['id'] for r in data['records']]==['12345']
            page.get_by_role('button',name='批量下载视频',exact=True).click()
            expect(page.get_by_text('不可下载 · 页面没有下载入口',exact=True)).to_be_visible()
            expect(page.get_by_role('link',name='保存视频 ZIP',exact=False)).to_have_count(0)
            assert len([w for w in writes if w[0]=='/api/learning/downloads'])==1
            assert not any('deletion' in w[0] for w in writes)
            page.reload()
            expect(page.get_by_text('不可下载 · 页面没有下载入口',exact=True)).to_be_visible()
            page.locator('.library-group summary').first.click()
            page.get_by_role('button',name='选择',exact=True).click()
            page.get_by_role('checkbox',name='全选当前页',exact=True).check()
            evidence=Path(os.environ.get('LEARNING_EVIDENCE_DIR',str(tmp_path))); evidence.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(evidence/'batch-actions.png'),animations='disabled')
            page.set_viewport_size(dict(width=390,height=844))
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            page.screenshot(path=str(evidence/'batch-actions-mobile.png'),animations='disabled')
            browser.close()
