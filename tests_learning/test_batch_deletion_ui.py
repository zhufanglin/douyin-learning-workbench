import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect
from learning.app import create_app

URL=os.environ.get('LEARNING_UI_URL')
pytestmark=pytest.mark.skipif(not URL,reason='Set LEARNING_UI_URL')


def setup_route(page,api,writes):
    def route(route):
        path=route.request.url.split('/api/learning/')[1]
        if route.request.method=='POST':
            assert path in ['deletion/batch-preview','deletion/batch-commit']
            if path.endswith('commit'): writes.append(route.request.post_data_json)
            response=api.post('/api/learning/'+path,json=route.request.post_data_json)
        else: response=api.get('/api/learning/'+path)
        route.fulfill(status=response.status_code,body=response.content,content_type='application/json')
    page.route('**/api/learning/**',route)


def test_task_page_selection_scope_running_exclusion_and_batch(tmp_path):
    with TestClient(create_app(tmp_path/'b.db')) as api:
        store=api.app.state.store
        for i in range(23):
            t=store.create_task('批量任务 '+str(i),'live')
            if i != 22: store.finish(t['id'],{},'success','完成')
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,channel='chromium')
            page=browser.new_page(viewport=dict(width=1366,height=900)); writes=[]
            setup_route(page,api,writes)
            page.goto(URL.split('#')[0]+'#tasks')
            panel=page.locator('#task-results')
            expect(panel.locator('.history-task')).to_have_count(20)
            expect(panel.get_by_role('checkbox')).to_have_count(0)
            page.get_by_role('button',name='选择',exact=True).click()
            page.get_by_role('button',name='取消选择',exact=True).click()
            expect(panel.get_by_role('checkbox')).to_have_count(0)
            page.get_by_role('button',name='选择',exact=True).click()
            page.get_by_role('checkbox',name='全选当前页',exact=True).check()
            expect(panel.get_by_text('已选 19 条',exact=True)).to_be_visible()
            expect(page.get_by_role('checkbox',name='选择批量任务 22',exact=True)).to_be_disabled()
            panel.get_by_role('button',name='下一页',exact=True).click()
            expect(panel.locator('.history-task')).to_have_count(3)
            expect(panel.get_by_role('checkbox')).to_have_count(0)
            page.get_by_role('button',name='选择',exact=True).click()
            expect(panel.get_by_text('已选 0 条',exact=True)).to_be_visible()
            page.get_by_role('checkbox',name='全选当前页',exact=True).check()
            expect(panel.get_by_text('已选 3 条',exact=True)).to_be_visible()
            page.get_by_label('搜索历史任务关键词').fill('批量任务 0')
            expect(panel.get_by_role('checkbox')).to_have_count(0)
            page.get_by_role('button',name='清空筛选',exact=True).click()
            page.get_by_role('button',name='选择',exact=True).click()
            page.get_by_role('checkbox',name='全选当前页',exact=True).check()
            page.get_by_role('button',name='批量删除所选记录',exact=True).click()
            dialog=page.get_by_role('dialog',name='删除本地记录')
            expect(dialog.get_by_text('已选 19 条记录',exact=True)).to_be_visible()
            dialog.get_by_role('button',name='取消',exact=True).click()
            assert writes==[]
            page.get_by_role('button',name='批量删除所选记录',exact=True).click()
            expect(dialog.get_by_role('button',name='确认删除')).to_be_enabled()
            evidence=Path(os.environ.get('LEARNING_EVIDENCE_DIR',str(tmp_path))); evidence.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(evidence/'batch-confirmation.png'),animations='disabled')
            dialog.get_by_role('button',name='确认删除',exact=True).click()
            expect(dialog).to_have_count(0)
            expect(panel.locator('.history-task')).to_have_count(4)
            expect(panel.get_by_text('已选 0 条',exact=True)).to_be_visible()
            assert len(writes)==1 and len(writes[0]['targets'])==19
            page.reload()
            expect(panel.locator('.history-task')).to_have_count(4)
            page.set_viewport_size(dict(width=390,height=844))
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            browser.close()


@pytest.mark.parametrize('view', ['videos','users','comments','task-logs'])
def test_group_and_log_batch_selection(tmp_path,view):
    with TestClient(create_app(tmp_path/'b.db')) as api:
        store=api.app.state.store; t=store.create_task('分组批量测试','live')
        store.finish(t['id'],dict(videos=[dict(id='v1',title='批量视频一'),dict(id='v2',title='批量视频二')],users=[dict(id='u1',nickname='用户一'),dict(id='u2',nickname='用户二')],comments=[dict(id='c1',video_id='v1',user_id='u1',content='评论一'),dict(id='c2',video_id='v1',user_id='u2',content='评论二')]),'success','完成')
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,channel='chromium'); page=browser.new_page(); writes=[]
            setup_route(page,api,writes)
            page.goto(URL.split('#')[0]+'#'+view)
            if view!='task-logs': page.locator('.library-group summary').first.click()
            scope=page.locator('.library-group').first if view!='task-logs' else page.locator('#task-logs')
            expect(scope.get_by_role('checkbox')).to_have_count(0)
            scope.get_by_role('button',name='选择',exact=True).click()
            scope.get_by_role('checkbox',name='全选',exact=False).check()
            scope.get_by_role('button',name='取消选择',exact=True).click()
            expect(scope.get_by_role('checkbox')).to_have_count(0)
            scope.get_by_role('button',name='选择',exact=True).click()
            expect(scope.get_by_text('已选 0 条',exact=True)).to_be_visible()
            scope.get_by_role('checkbox',name='全选',exact=False).check()
            expect(scope.get_by_text('已选 2 条',exact=True)).to_be_visible()
            scope.get_by_role('button',name='批量删除所选记录',exact=True).click()
            dialog=page.get_by_role('dialog',name='删除本地记录')
            expect(dialog.get_by_text('已选 2 条记录',exact=True)).to_be_visible()
            dialog.get_by_role('button',name='确认删除',exact=True).click()
            expect(dialog).to_have_count(0)
            assert len(writes)==1 and len(writes[0]['targets'])==2
            expected_kind='logs' if view=='task-logs' else view
            assert all(r['kind']==expected_kind for r in writes[0]['targets'])
            assert store.snapshot()['counts'][view]==0 if view!='task-logs' else not store.result(t['id'])['logs']
            browser.close()
