import os
import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright,expect
from learning.app import create_app
@pytest.mark.skipif(not os.environ.get('LEARNING_UI_URL'),reason='Set LEARNING_UI_URL')
def test_search_mode_controls_send_selected_mode(tmp_path):
 with TestClient(create_app(tmp_path/'db')) as api:
  class Reader:
   def close(self):pass
   def preview_snapshot(self,**kw):return {'status':'idle'}
   def submit(self,store,task,**kw):store.finish(task['id'],{},'success','隔离模式测试完成')
  api.app.state.reader=Reader()
  with sync_playwright() as p:
   b=p.chromium.launch(headless=True,channel='chromium');page=b.new_page()
   def route(r):
    result=api.request(r.request.method,'/api/learning/'+r.request.url.split('/api/learning/')[1],json=r.request.post_data_json if r.request.post_data else None)
    r.fulfill(status=result.status_code,body=result.content,content_type='application/json')
   page.route('**/api/learning/**',route);page.goto(os.environ['LEARNING_UI_URL']+'#keyword')
   expect(page.locator('input[value=videos]')).to_be_checked()
   for mode in ('videos','comments'):
    page.locator('input[value='+mode+']').check()
    page.locator('#keyword').fill('测试'+mode)
    page.get_by_role('button',name='开始网页读取',exact=True).click()
    expect(page.get_by_text('隔离模式测试完成',exact=False).first).to_be_visible()
    assert any(t['keyword']=='测试'+mode and t['search_mode']==mode for t in api.app.state.store.snapshot()['tasks'])
    expect(page.get_by_role('button',name='开始网页读取',exact=True)).to_be_enabled()
   page.set_viewport_size({'width':390,'height':844})
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
   b.close()
