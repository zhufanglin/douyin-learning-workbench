import os
import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright,expect
from learning.app import create_app

@pytest.mark.skipif(not os.environ.get('LEARNING_UI_URL'),reason='Set LEARNING_UI_URL')
def test_manual_judgment_persists_and_business_isolation(tmp_path):
 with TestClient(create_app(tmp_path/'db')) as api:
  ids=[]
  for word in ['询价','预约']:
   ids.append(api.post('/api/learning/business-profiles',json={'name':word,'goal':word,'keywords':[word],'demand_terms':[word]}).json()['id'])
  s=api.app.state.store;t=s.create_task('测试','import')
  s.finish(t['id'],{'users':[{'id':'u','nickname':'测试用户'}],'comments':[{'id':'c','user_id':'u','video_id':'123','content':'我想询价'}]},'success','ok')
  with sync_playwright() as p:
   b=p.chromium.launch(headless=True,channel='chromium');page=b.new_page()
   def route(r):
    result=api.request(r.request.method,'/api/learning/'+r.request.url.split('/api/learning/')[1],json=r.request.post_data_json if r.request.post_data else None)
    r.fulfill(status=result.status_code,body=result.content,content_type='application/json')
   page.route('**/api/learning/**',route);page.goto(os.environ['LEARNING_UI_URL']+'#leads')
   page.get_by_role('combobox',name='分析业务').select_option(ids[0])
   page.get_by_role('button',name='分析已存评论').click()
   card=page.get_by_role('region',name='需求用户列表').locator('article')
   expect(card.get_by_text('命中原文：',exact=False)).to_be_visible()
   expect(card.get_by_text('可能需求',exact=True)).to_be_visible()
   card.get_by_role('button',name='人工判断',exact=True).click()
   card.get_by_role('combobox',name='判断类别').select_option('clear')
   card.get_by_role('textbox',name='判断依据').fill('核对后确认询价')
   card.get_by_role('button',name='保存判断').click()
   expect(card.get_by_text('明确需求',exact=True)).to_be_visible()
   page.get_by_role('button',name='分析已存评论').click()
   expect(card.get_by_text('明确需求',exact=True)).to_be_visible()
   page.reload();page.get_by_role('combobox',name='分析业务').select_option(ids[0])
   expect(card.get_by_text('明确需求',exact=True)).to_be_visible()
   page.get_by_role('combobox',name='分析业务').select_option(ids[1])
   page.get_by_role('button',name='分析已存评论').click()
   expect(card.get_by_text('待判断',exact=True)).to_be_visible()
   expect(card.get_by_text('明确需求',exact=True)).to_have_count(0)
   page.set_viewport_size({'width':390,'height':844})
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
   b.close()
