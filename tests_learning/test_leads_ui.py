import os
import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect
from learning.app import create_app

@pytest.mark.skipif(not os.environ.get('LEARNING_UI_URL'), reason='Set LEARNING_UI_URL')
def test_leads_merge_filter_and_sources(tmp_path):
 with TestClient(create_app(tmp_path/'db')) as api:
  store=api.app.state.store
  ids=[]
  for i in range(2):
   profile=api.post('/api/learning/business-profiles',json={'name':f'业务{i}','goal':f'目标{i}','keywords':[f'关键词{i}']}).json()
   ids.append(profile['id'])
   task=store.create_task(f'关键词{i}','import',profile['id'])
   store.finish(task['id'],{'users':[{'id':'u1','nickname':'同一个用户','profile_url':'https://www.douyin.com/user/u1'}], 'videos':[{'id':str(123+i),'title':'可核对的来源视频','author':'视频作者'}], 'comments':[{'id':f'c{i}','user_id':'u1','video_id':str(123+i),'content':f'业务{i}的留言','create_time':1700000000}]},'success','完成')
  catalog=api.get('/api/learning/catalog').json()
  assert {t['business_profile']['id'] for t in catalog['tasks']}==set(ids)
  api.delete('/api/learning/business-profiles/'+ids[0])
  assert any(t['business_profile']['id']==ids[0] for t in api.get('/api/learning/catalog').json()['tasks'])
  with sync_playwright() as p:
   b=p.chromium.launch(headless=True,channel='chromium');page=b.new_page()
   def route(r):
    path='/api/learning/'+r.request.url.split('/api/learning/')[1]
    result=api.request(r.request.method,path)
    r.fulfill(status=result.status_code,body=result.content,content_type='application/json')
   page.route('**/api/learning/**',route)
   page.goto(os.environ['LEARNING_UI_URL']+'#leads')
   region=page.get_by_role('region',name='需求用户列表')
   expect(region.locator('article')).to_have_count(1)
   expect(region.get_by_text('业务0的留言',exact=True)).to_be_visible()
   expect(region.get_by_text('业务1的留言',exact=True)).to_be_visible()
   page.get_by_role('combobox',name='来源视频',exact=True).select_option('["import","123"]')
   expect(region.get_by_text('业务1的留言',exact=True)).to_have_count(0)
   expect(region.get_by_text('业务0的留言',exact=True)).to_be_visible()
   expect(region.get_by_role('link',name='可核对的来源视频')).to_have_attribute('href','https://www.douyin.com/video/123')
   page.get_by_role('textbox',name='昵称或评论').fill('不存在')
   expect(region.locator('article')).to_have_count(0)
   page.get_by_role('textbox',name='昵称或评论').fill('同一个用户')
   expect(region.locator('article')).to_have_count(1)
   page.set_viewport_size({'width':390,'height':844})
   assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
   b.close()
