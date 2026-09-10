import os
import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright,expect
from learning.app import create_app

@pytest.mark.skipif(not os.environ.get('LEARNING_UI_URL'),reason='Set LEARNING_UI_URL')
def test_field_configuration_and_date_filters(tmp_path):
 with TestClient(create_app(tmp_path/'db')) as api:
  s=api.app.state.store;t=s.create_task('样例','import')
  s.finish(t['id'],{'users':[{'id':'u','nickname':'样例用户'}],'comments':[
    {'id':'1','user_id':'u','video_id':'123','content':'需要XL','create_time':'2026-09-09T23:59:59+08:00'},
    {'id':'2','user_id':'u','video_id':'123','content':'需要小号','create_time':'2026-09-10T00:00:00+08:00'},
    {'id':'3','user_id':'u','video_id':'123','content':'请问价格'}]},'success','ok')
  with sync_playwright() as p:
   b=p.chromium.launch(headless=True,channel='chromium');page=b.new_page(timezone_id='Asia/Shanghai')
   def route(r):
    result=api.request(r.request.method,'/api/learning/'+r.request.url.split('/api/learning/')[1],json=r.request.post_data_json if r.request.post_data else None)
    r.fulfill(status=result.status_code,body=result.content,content_type='application/json')
   page.route('**/api/learning/**',route);page.goto(os.environ['LEARNING_UI_URL']+'#keyword')
   page.get_by_text('新建或编辑配置',exact=True).click()
   for label,value in [('配置名称','尺寸咨询'),('想找到什么需求的用户','尺寸需求'),('搜索关键词（每行一个）','规格')]:page.get_by_label(label,exact=True).fill(value)
   page.get_by_role('button',name='添加需求字段').click()
   page.get_by_role('textbox',name='字段名称 1').fill('规格')
   page.get_by_role('textbox',name='字段短语 1').fill('XL\n小号')
   page.get_by_role('button',name='保存并使用').click()
   expect(page.locator('#keyword')).to_have_value('规格')
   profile=api.get('/api/learning/business-profiles').json()['items'][0]
   assert profile['fields']==[{'name':'规格','terms':['XL','小号']}]
   page.goto(os.environ['LEARNING_UI_URL']+'#leads')
   page.get_by_role('combobox',name='分析业务').select_option(profile['id'])
   page.get_by_role('button',name='分析已存评论').click()
   expect(page.get_by_role('region',name='需求用户列表').get_by_text('已分析 3/3 条',exact=False)).to_be_visible()
   page.get_by_text('字段与评论时间筛选',exact=True).click()
   page.get_by_role('combobox',name='需求字段',exact=True).select_option('规格')
   page.get_by_role('textbox',name='字段包含').fill('xl')
   card=page.get_by_role('region',name='需求用户列表').locator('article')
   expect(card.get_by_text('需要XL',exact=True)).to_be_visible()
   expect(card.get_by_text('需要小号',exact=True)).to_have_count(0)
   page.get_by_role('button',name='清除字段与时间筛选').click()
   page.get_by_label('评论开始日期').fill('2026-09-09')
   page.get_by_label('评论结束日期').fill('2026-09-09')
   expect(card.get_by_text('需要XL',exact=True)).to_be_visible()
   expect(card.get_by_text('需要小号',exact=True)).to_have_count(0)
   expect(card.get_by_text('请问价格',exact=True)).to_have_count(0)
   page.get_by_role('combobox',name='评论时间状态').select_option('missing')
   expect(card.get_by_text('请问价格',exact=True)).to_be_visible()
   expect(card.get_by_text('需要XL',exact=True)).to_have_count(0)
   page.get_by_role('combobox',name='评论时间状态').select_option('all')
   page.get_by_label('评论开始日期').fill('2026-09-10')
   expect(page.get_by_text('开始日期不能晚于结束日期。')).to_be_visible()
   expect(card).to_have_count(0)
   page.get_by_role('button',name='清除字段与时间筛选').click()
   expect(card.get_by_text('请问价格',exact=True)).to_be_visible()
   page.set_viewport_size({'width':390,'height':844})
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
   b.close()
