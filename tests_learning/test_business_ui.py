import os
import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright,expect
from learning.app import create_app
URL=os.environ.get('LEARNING_UI_URL')
pytestmark=pytest.mark.skipif(not URL,reason='Set LEARNING_UI_URL')
def test_two_business_goals_and_task_snapshot(tmp_path):
 with TestClient(create_app(tmp_path/'db')) as api:
  class Reader:
   def close(self):pass
   def preview_snapshot(self,**kw):return {'status':'idle'}
   def submit(self,store,task,**kw):store.finish(task['id'],{},'success','隔离测试，无平台访问')
  api.app.state.reader=Reader()
  with sync_playwright() as p:
   b=p.chromium.launch(headless=True,channel='chromium');page=b.new_page()
   def route(r):
    path='/api/learning/'+r.request.url.split('/api/learning/')[1]
    result=api.request(r.request.method,path,json=r.request.post_data_json if r.request.post_data else None)
    r.fulfill(status=result.status_code,body=result.content,content_type='application/json')
   page.route('**/api/learning/**',route);page.goto(URL+'#keyword')
   page.get_by_text('新建或编辑配置',exact=True).click()
   for name,goal,word in [('产品咨询','找询价需求','商品咨询'),('服务咨询','找预约需求','服务预约')]:
    page.get_by_role('button',name='新建配置',exact=True).click()
    page.get_by_label('配置名称',exact=True).fill(name)
    page.get_by_label('想找到什么需求的用户',exact=True).fill(goal)
    page.get_by_label('搜索关键词（每行一个）',exact=True).fill(word)
    page.get_by_role('button',name='保存并使用',exact=True).click()
    expect(page.locator('#keyword')).to_have_value(word)
   items=api.get('/api/learning/business-profiles').json()['items'];first=next(v for v in items if v['name']=='产品咨询')
   page.get_by_role('combobox',name='业务目标配置',exact=True).select_option(first['id'])
   expect(page.locator('#keyword')).to_have_value('商品咨询')
   page.get_by_role('button',name='开始网页读取',exact=True).click()
   expect(page.get_by_text('隔离测试，无平台访问',exact=False).first).to_be_visible()
   task=api.app.state.store.snapshot()['tasks'][0]
   assert api.app.state.store.result(task['id'])['business_profile']['id']==first['id']
   page.set_viewport_size({'width':390,'height':844})
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
   b.close()
