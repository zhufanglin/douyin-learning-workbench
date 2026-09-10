import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect
from learning.app import create_app

URL = os.environ.get('LEARNING_UI_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Set LEARNING_UI_URL')


@pytest.mark.parametrize('view,kind,label', [('tasks','tasks','删除测试任务'),('videos','videos','删除测试视频'),('users','users','删除测试用户'),('comments','comments','删除测试评论'),('keyword','tasks','删除本次搜索任务'),('task-logs','logs','删除日志：已保存测试数据')])
def test_delete_row_confirmation_cancel_commit_and_refresh(tmp_path, view, kind, label):
    with TestClient(create_app(tmp_path/'d.db')) as api:
        store = api.app.state.store
        task = store.create_task('测试任务','live')
        store.finish(task['id'], dict(videos=[dict(id='v1',title='测试视频')],users=[dict(id='u1',nickname='测试用户')],comments=[dict(id='c1',video_id='v1',user_id='u1',content='测试评论')]), 'blocked', '已保存测试数据')
        commits = []
        def route_api(route):
            path = route.request.url.split('/api/learning/')[1]
            if route.request.method == 'POST':
                assert path.startswith('deletion/')
                if path.endswith('commit'): commits.append(route.request.post_data_json)
                result = api.post('/api/learning/'+path,json=route.request.post_data_json)
            else: result = api.get('/api/learning/'+path)
            route.fulfill(status=result.status_code,body=result.content,content_type='application/json')
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True,channel='chromium')
            page = browser.new_page(viewport=dict(width=1366,height=900))
            page.route('**/api/learning/**',route_api)
            if view == 'keyword': page.add_init_script('sessionStorage.setItem("learning-search-task", "'+task['id']+'")')
            page.goto(URL.split('#')[0]+'#'+view)
            if view in ('videos','users','comments'): page.locator('.library-group summary').first.click()
            if view != 'keyword':
                page.get_by_role('button',name='选择',exact=True).click()
                page.get_by_role('checkbox',name='选择'+label.removeprefix('删除'),exact=True).check()
            row_delete = page.get_by_role('button',name=label if view == 'keyword' else '批量删除所选记录',exact=True)
            row_delete.click()
            dialog = page.get_by_role('dialog',name='删除本地记录')
            expect(dialog.get_by_role('button',name='确认删除',exact=True)).to_be_enabled()
            expect(dialog.get_by_text('将删除',exact=True)).to_be_visible()
            dialog.get_by_role('button',name='取消',exact=True).click()
            expect(dialog).to_have_count(0)
            assert commits == []
            expect(row_delete).to_be_visible()
            row_delete.click()
            expect(dialog.get_by_role('button',name='确认删除',exact=True)).to_be_enabled()
            if view == 'comments':
                evidence=Path(os.environ.get('LEARNING_EVIDENCE_DIR',str(tmp_path))); evidence.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(evidence/'delete-confirmation.png'),animations='disabled')
            dialog.get_by_role('button',name='确认删除',exact=True).click()
            expect(dialog).to_have_count(0)
            expect(row_delete).to_have_count(0)
            assert len(commits)==1
            assert (commits[0]['kind'] if view == 'keyword' else commits[0]['targets'][0]['kind'])==kind
            if view=='keyword':
                expect(page.get_by_role('region',name='本次搜索进度')).to_have_count(0)
                assert page.evaluate('sessionStorage.getItem("learning-search-task")') is None
            else:
                page.reload()
                expect(row_delete).to_have_count(0)
            page.set_viewport_size(dict(width=390,height=844))
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            browser.close()
