import os
import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright,expect
from learning.app import create_app
from tests_learning.test_batch_deletion_ui import setup_route

URL=os.environ.get('LEARNING_UI_URL')
pytestmark=pytest.mark.skipif(not URL,reason='Set LEARNING_UI_URL')

@pytest.mark.parametrize('view,count',[('videos',2),('users',1),('comments',100)])
def test_one_toolbar_deduplicates_groups_and_limits_visible_page(tmp_path,view,count):
    with TestClient(create_app(tmp_path/'db')) as api:
        s=api.app.state.store
        for i in range(2):
            t=s.create_task('统一批量'+str(i),'live')
            s.finish(t['id'],{'videos':[{'id':'12345','title':'视频一'},{'id':'23456','title':'视频二'}],
              'users':[{'id':'u1','nickname':'同一用户'}],
              'comments':[{'id':str(k),'video_id':'12345' if k<60 else '23456','user_id':'u1','content':'评论'+str(k)} for k in range(105)]},'success','完成')
        with sync_playwright() as p:
            b=p.chromium.launch(headless=True,channel='chromium');page=b.new_page();writes=[];setup_route(page,api,writes)
            page.goto(URL+'#'+view);page.get_by_role('button',name='选择',exact=True).click()
            expect(page.locator('.batch-toolbar')).to_have_count(1)
            expect(page.locator('.unified-selection-list input[type=checkbox]')).to_have_count(count)
            expect(page.locator('.library-group')).to_have_count(0)
            page.get_by_role('checkbox',name='全选当前页',exact=True).check()
            expect(page.get_by_text(f'已选 {count} 条',exact=True)).to_be_visible()
            if view=='comments':
                page.get_by_role('button',name='选择下一页',exact=True).click()
                expect(page.locator('.unified-selection-list input[type=checkbox]')).to_have_count(5)
                expect(page.get_by_text('已选 0 条',exact=True)).to_be_visible()
            page.get_by_role('button',name='取消选择',exact=True).click()
            expect(page.get_by_role('checkbox')).to_have_count(0)
            page.get_by_role('button',name='选择',exact=True).click()
            expect(page.get_by_text('已选 0 条',exact=True)).to_be_visible()
            page.get_by_label('搜索历史任务关键词').fill('无匹配')
            expect(page.get_by_role('checkbox')).to_have_count(0)
            assert not writes
            b.close()
