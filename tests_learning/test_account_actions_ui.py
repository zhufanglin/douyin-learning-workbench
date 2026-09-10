import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright,expect
from learning.app import create_app

URL=os.environ.get('LEARNING_UI_URL')
pytestmark=pytest.mark.skipif(not URL,reason='Set LEARNING_UI_URL')


def test_account_preview_explicit_confirm_and_uncertain_ui(tmp_path):
    class Reader:
        def __init__(self): self.calls=[]
        def submit_account_action(self,ledger,action,phase):
            self.calls.append(phase)
            ledger.mark(action['id'],'ready' if phase=='prepare' else 'uncertain','本地流程测试；未访问抖音')
        def open_account_browser(self): return {'note':'测试浏览器已打开，请本人登录'}
        def inspect_account_browser(self): return {'sender':'@tester','note':'已识别测试账号'}
        def preview_snapshot(self,focus=False): return {'status':'idle','image':None,'url':'','sequence':0,'age_ms':None,'busy':False}
        def close(self): pass
    with TestClient(create_app(tmp_path/'a.db')) as api:
        reader=Reader();api.app.state.reader=reader
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,channel='chromium');page=browser.new_page(viewport=dict(width=1366,height=900));writes=[]
            def route(route):
                path=route.request.url.split('/api/learning/')[1]
                if route.request.method=='POST':
                    assert path.startswith('account-actions/')
                    writes.append(path)
                    response=api.post('/api/learning/'+path,json=route.request.post_data_json)
                else: response=api.get('/api/learning/'+path)
                route.fulfill(status=response.status_code,body=response.content,content_type='application/json')
            page.route('**/api/learning/**',route)
            page.goto(URL.split('#')[0]+'#account-actions')
            page.get_by_role('button',name='打开浏览器登录',exact=True).click()
            expect(page.get_by_text('测试浏览器已打开，请本人登录',exact=True)).to_be_visible()
            assert reader.calls==[]
            page.get_by_role('button',name='我已登录，读取本人账号',exact=True).click()
            expect(page.get_by_label('本人账号主页',exact=True)).to_have_value('@tester')
            assert reader.calls==[]
            page.get_by_label('本人账号主页',exact=True).fill('@tester')
            page.get_by_label('测试用户主页',exact=True).fill('https://www.douyin.com/user/recipient')
            page.get_by_label('账号操作类型').select_option('message')
            page.get_by_label('待发送消息').fill('获准发送的测试消息')
            start=page.get_by_role('button',name='核对账号与操作条件',exact=True)
            expect(start).to_be_disabled()
            page.get_by_role('checkbox',name='我有权使用上述账号',exact=False).check()
            start.click()
            panel=page.get_by_role('region',name='账号操作预览')
            expect(panel.get_by_text('待你确认',exact=True)).to_be_visible()
            expect(panel.get_by_text('获准发送的测试消息',exact=True)).to_be_visible()
            send=panel.get_by_role('button',name='确认发送这条消息',exact=True)
            expect(send).to_be_disabled()
            assert reader.calls==['prepare']
            panel.get_by_role('checkbox',name='我已核对以上账号',exact=False).check()
            expect(send).to_be_enabled()
            evidence=Path(os.environ.get('LEARNING_EVIDENCE_DIR',str(tmp_path)));evidence.mkdir(parents=True,exist_ok=True)
            panel.scroll_into_view_if_needed();page.screenshot(path=str(evidence/'account-confirm.png'),animations='disabled')
            send.click()
            expect(panel.get_by_text('结果不确定',exact=True)).to_be_visible()
            expect(send).to_have_count(0)
            page.reload()
            expect(panel.get_by_text('结果不确定',exact=True)).to_be_visible()
            assert reader.calls==['prepare','execute']
            panel.get_by_role('button',name='只核对结果，不重复执行',exact=True).click()
            expect(panel.get_by_text('结果不确定',exact=True)).to_be_visible()
            assert reader.calls==['prepare','execute','verify']
            assert len([w for w in writes if w.endswith('/confirm')])==1
            page.set_viewport_size(dict(width=390,height=844))
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
            browser.close()
