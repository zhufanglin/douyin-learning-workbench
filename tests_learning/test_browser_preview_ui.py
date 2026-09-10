import base64
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright,expect
from learning.app import create_app

URL=os.environ.get('LEARNING_UI_URL')
pytestmark=pytest.mark.skipif(not URL,reason='Set LEARNING_UI_URL')


def test_preview_live_delayed_expanded_collapsed_and_responsive(tmp_path):
    with TestClient(create_app(tmp_path/'ui.db')) as api, sync_playwright() as p:
        task=api.app.state.store.create_task('露营 · 界面测试','live')
        api.app.state.store.finish(task['id'],dict(videos=[dict(id=str(7000000000000000000+i),title=f'山野露营视频 {i+1}',search_rank=i+1) for i in range(12)]),'success','已保存 12 个视频')
        browser=p.chromium.launch(headless=True,channel='chromium')
        sample=browser.new_page(viewport=dict(width=1280,height=900))
        sample.set_content('<body style="margin:0;background:#17191e;color:white;font:24px sans-serif"><header style="padding:30px;background:#252833">本地测试页面 · 浏览器画面</header><main style="padding:40px"><h1>正在读取：露营</h1><p>这是隔离测试画面，不访问真实平台</p><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:24px">'+''.join(f'<div style="height:200px;background:#303746;padding:20px;border-radius:12px">视频 {i+1}</div>' for i in range(6))+'</div></main></body>')
        img='data:image/jpeg;base64,'+base64.b64encode(sample.screenshot(type='jpeg')).decode(); sample.close()
        frame=dict(status='live',image=img,url='https://www.douyin.com/search/fixture',sequence=1,age_ms=100,busy=True)
        reads=[]; writes=[]; errors=[]
        page=browser.new_page(viewport=dict(width=1440,height=900));page.on('pageerror',lambda e:errors.append(str(e)))
        def route(r):
            path=r.request.url.split('/api/learning/')[1]
            if path=='browser/preview': reads.append(path);r.fulfill(json=frame)
            elif r.request.method!='GET': writes.append(path);r.fulfill(status=409,json={'detail':'测试禁止真实操作'})
            else:
                response=api.get('/api/learning/'+path);r.fulfill(status=response.status_code,body=response.content,content_type='application/json')
        page.route('**/api/learning/**',route)
        page.goto(URL.split('#')[0]+'#tasks?task='+task['id'])
        preview=page.get_by_role('complementary',name='执行浏览器')
        expect(preview.get_by_role('img',name='当前执行浏览器画面')).to_be_visible()
        expect(preview.get_by_text('执行中',exact=True)).to_be_visible()
        box=preview.bounding_box();content=page.locator('#task-results').bounding_box()
        assert box['x']>=content['x']+content['width']
        assert page.locator('h1').bounding_box()['y']<90
        evidence=Path(os.environ.get('LEARNING_EVIDENCE_DIR',str(tmp_path)));evidence.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(evidence/'browser-workbench-desktop.png'))
        preview.get_by_role('button',name='放大',exact=True).click()
        expect(page.get_by_role('dialog')).to_be_visible()
        page.keyboard.press('Escape');expect(page.get_by_role('dialog')).to_have_count(0)
        expect(preview.get_by_role('button',name='放大',exact=True)).to_be_focused()
        frame['age_ms']=12000
        expect(preview.get_by_text('画面更新延迟',exact=True)).to_be_visible(timeout=5000)
        preview.get_by_role('button',name='收起浏览器画面',exact=True).click()
        before=len(reads);page.wait_for_timeout(1900);assert len(reads)==before
        expect(preview).to_have_count(0)
        page.get_by_role('button',name='浏览器画面',exact=True).click()
        expect(preview).to_be_visible()
        page.set_viewport_size(dict(width=910,height=900))
        assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
        box=preview.bounding_box();content=page.locator('#task-results').bounding_box()
        assert box['x']>=content['x']+content['width']
        page.screenshot(path=str(evidence/'browser-workbench-narrow.png'))
        page.set_viewport_size(dict(width=390,height=844))
        assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
        page.screenshot(path=str(evidence/'browser-workbench-mobile.png'))
        frame.update(status='closed',image=None)
        expect(preview.get_by_text('浏览器已关闭',exact=True).first).to_be_visible(timeout=5000)
        assert writes==[] and errors==[]
        browser.close()
