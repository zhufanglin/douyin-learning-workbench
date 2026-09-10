import json
import os
from pathlib import Path
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect
from learning.app import create_app
import pytest

URL = os.environ.get('LEARNING_UI_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Set LEARNING_UI_URL')


def test_four_entries_history_filters_drawer_return_and_no_platform_writes(tmp_path):
    with TestClient(create_app(tmp_path / 'library.db')) as api:
        store = api.app.state.store
        search = store.create_task('露营搜索', 'live')
        v1 = dict(id='7000000000000000001', title='山野露营测试视频', search_rank=1)
        v2 = dict(id='7000000000000000002', title='第二个测试视频', search_rank=2)
        store.finish(search['id'], dict(videos=[v1, v2]), 'success', '已存两个视频')
        read = store.create_task('露营视频评论读取', 'live')
        user = dict(id='u1', nickname='测试作者', profile_url='')
        comments = [dict(id=f'c{i}', video_id=v1['id'], user_id='u1', comment_rank=i+1, content=f'测试评论 {i+1}') for i in range(205)]
        store.finish(read['id'], dict(videos=[v1], users=[user], comments=comments), 'success', '已保存评论')
        second = store.create_task('第二视频评论读取', 'live')
        store.finish(second['id'], dict(videos=[v2], users=[user], comments=[dict(id='other', video_id=v2['id'], user_id='u1', content='另一视频下的评论')]), 'success', '已保存')
        with store.connect() as db:
            db.execute("UPDATE tasks SET created_at='2026-09-08T02:00:00+00:00' WHERE id=?", (search['id'],))
            db.execute("UPDATE tasks SET created_at='2026-09-09T02:00:00+00:00' WHERE id!=?", (search['id'],))
        writes, errors = [], []
        def route_api(route):
            path = route.request.url.split('/api/learning/')[1]
            if route.request.method != 'GET':
                writes.append(path)
                route.fulfill(status=409, json={'detail': '测试禁止平台操作'})
                return
            response = api.get('/api/learning/' + path)
            route.fulfill(status=response.status_code, body=response.content, headers={'Content-Type':'application/json', **({'Content-Disposition':response.headers['content-disposition']} if 'content-disposition' in response.headers else {})})
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, channel='chromium')
            page = browser.new_page(viewport=dict(width=1440, height=1000))
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.route('**/api/learning/**', route_api)
            page.goto(URL.split('#')[0] + '#overview')
            expect(page.locator('#search-workspace')).to_have_count(0)
            expect(page.locator('#task-results')).to_have_count(0)
            expect(page.locator('#task-logs')).to_have_count(0)
            panel = page.locator('#task-results')
            page.get_by_role('button', name='查看累计任务', exact=True).click()
            expect(panel.get_by_role('heading', name='累计任务', exact=True)).to_be_visible()
            expect(panel.locator('.history-task')).to_have_count(3)
            page.get_by_label('任务执行日期', exact=True).fill('2026-09-08')
            expect(panel.locator('.history-task')).to_have_count(1)
            panel.get_by_role('button').filter(has_text='露营搜索').click()
            expect(panel.get_by_text('执行时间：2026/9/8 10:00:00', exact=False)).to_be_visible()
            page.get_by_label('视频列表').get_by_role('button').filter(has_text=v1['title']).click()
            pane = page.get_by_label('所选视频评论')
            expect(pane.locator('article')).to_have_count(100)
            pane.get_by_role('button', name='下一页', exact=True).click()
            expect(pane.get_by_text('测试评论 101', exact=True)).to_be_visible()
            pane.get_by_role('button', name='测试作者', exact=True).first.click()
            drawer = page.get_by_role('dialog')
            expect(drawer.get_by_text('已存 206 条评论 · 涉及 2 个视频', exact=True)).to_be_visible()
            page.get_by_role('button', name='关闭用户详情').click()
            expect(pane.get_by_text('测试评论 101', exact=True)).to_be_visible()
            with page.expect_download() as download:
                pane.get_by_role('link', name='导出本视频评论（含已存回复）').click()
            target = tmp_path / 'export.json'
            download.value.save_as(target)
            assert len(json.loads(target.read_text(encoding='utf-8'))['comments']) == 205
            # A task with comments must use its own snapshot, even after a newer update.
            newer = store.create_task('较新读取记录', 'live')
            store.finish(newer['id'], dict(videos=[v1], users=[user], comments=[dict(comments[0], content='较新内容')]), 'success', '更新')
            panel.get_by_role('button', name='返回累计任务').click()
            expect(page.get_by_label('任务执行日期', exact=True)).to_have_value('2026-09-08')
            expect(panel.locator('.history-task')).to_have_count(1)
            page.get_by_role('button', name='清空筛选', exact=True).click()
            page.get_by_label('筛选来源任务', exact=True).select_option(read['id'])
            panel.get_by_role('button').filter(has_text='→ 查看任务').first.click()
            expect(page.get_by_label('所选视频评论').get_by_text('测试评论 1', exact=True)).to_be_visible()
            expect(page.get_by_label('所选视频评论').get_by_text('较新内容', exact=True)).to_have_count(0)
            panel.get_by_role('button', name='返回累计任务').click()
            page.get_by_role('button', name='清空筛选', exact=True).click()
            for view in ['已存视频', '去重用户', '已存评论']:
                page.get_by_role('navigation').get_by_role('link', name=view, exact=True).click()
                expect(panel.get_by_role('heading', name=view, exact=True)).to_be_visible()
                expect(page.get_by_role('navigation').get_by_role('link', name=view, exact=True)).to_have_class('is-active')
            page.get_by_label('筛选视频', exact=True).select_option(json.dumps(['live',v1['id']], separators=(',',':')))
            expect(panel.locator('.library-group')).to_have_count(1)
            panel.locator('.library-group summary').click()
            expect(panel.locator('.library-comment')).to_have_count(100)
            panel.get_by_role('button', name='分组下一页').click()
            expect(panel.locator('.library-comment')).to_have_count(100)
            panel.get_by_role('button', name='分组下一页').click()
            expect(panel.locator('.library-comment')).to_have_count(5)
            assert writes == [], writes
            assert errors == [], errors
            evidence = Path(os.environ.get('LEARNING_EVIDENCE_DIR', str(tmp_path)))
            evidence.mkdir(parents=True, exist_ok=True)
            panel.locator('.library-group').scroll_into_view_if_needed()
            page.screenshot(path=str(evidence / 'comments.png'), animations='disabled')
            page.get_by_role('navigation').get_by_role('link', name='累计任务', exact=True).click()
            expect(panel.locator('.history-task')).to_have_count(4)
            page.screenshot(path=str(evidence / 'tasks.png'), animations='disabled')
            page.set_viewport_size(dict(width=390,height=844))
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            page.screenshot(path=str(evidence / 'mobile.png'))
            browser.close()


def test_independent_routes_reload_back_filters_and_search_progress(tmp_path):
    with TestClient(create_app(tmp_path / 'routes.db')) as api:
        store = api.app.state.store
        for i in range(23):
            task = store.create_task(f'分页任务 {i}', 'live')
            store.finish(task['id'], dict(videos=[], users=[], comments=[]), 'success', '本地测试记录')
        writes = []
        def route_api(route):
            path = route.request.url.split('/api/learning/')[1]
            if route.request.method == 'POST':
                writes.append(path)
                assert path == 'tasks'
                payload = route.request.post_data_json
                assert payload == dict(keyword='页面测试', source='live', limit=100)
                task = store.create_task(payload['keyword'], 'live')
                store.finish(task['id'], dict(videos=[], users=[], comments=[]), 'success', '测试搜索已结束')
                route.fulfill(json=task)
                return
            response = api.get('/api/learning/' + path)
            route.fulfill(status=response.status_code, body=response.content, content_type='application/json')
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, channel='chromium')
            page = browser.new_page(viewport=dict(width=1440, height=1000))
            page.route('**/api/learning/**', route_api)
            base = URL.split('#')[0]
            nav = page.get_by_role('navigation')
            main = page.locator('main')
            for route, label in [('overview', '工作台概览'), ('keyword', '新建搜索'), ('tasks', '累计任务'), ('videos', '已存视频'), ('users', '去重用户'), ('comments', '已存评论'), ('task-logs', '任务日志')]:
                page.goto(base + '#' + route)
                expect(main).to_have_attribute('data-page', route)
                expect(main.get_by_role('heading', name=label, exact=True, level=1)).to_be_visible()
                expect(nav.locator('[aria-current="page"]')).to_have_count(1)
                expect(page.locator('#search-workspace')).to_have_count(int(route == 'keyword'))
                expect(page.locator('#task-logs')).to_have_count(int(route == 'task-logs'))
                expect(page.locator('#task-results')).to_have_count(int(route in ['tasks', 'videos', 'users', 'comments']))
                expect(page.locator('.workspace-stats')).to_have_count(int(route == 'overview'))
                page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                expect(main).to_have_attribute('data-page', route)
            nav.get_by_role('link', name='累计任务', exact=True).click()
            page.get_by_label('搜索历史任务关键词').fill('分页任务')
            panel = page.locator('#task-results')
            panel.get_by_role('button', name='下一页', exact=True).click()
            expect(panel.locator('.history-task')).to_have_count(3)
            panel.locator('.history-task').first.click()
            expect(panel.get_by_role('heading', name='任务详情', exact=True)).to_be_visible()
            page.go_back()
            expect(panel.locator('.history-task')).to_have_count(3)
            nav.get_by_role('link', name='已存评论', exact=True).click()
            expect(page.get_by_label('搜索历史任务关键词')).to_have_value('')
            page.go_back()
            expect(page.get_by_label('搜索历史任务关键词')).to_have_value('分页任务')
            expect(panel.locator('.history-task')).to_have_count(3)
            page.reload()
            expect(main).to_have_attribute('data-page', 'tasks')
            expect(panel.locator('.history-task')).to_have_count(3)
            page.go_forward()
            expect(main).to_have_attribute('data-page', 'comments')
            nav.get_by_role('link', name='新建搜索', exact=True).click()
            page.get_by_label('关键词', exact=True).fill('页面测试')
            page.get_by_role('button', name='开始网页读取').click()
            expect(main.get_by_text('测试搜索已结束')).to_be_visible()
            expect(main).to_have_attribute('data-page', 'keyword')
            expect(panel).to_have_count(0)
            page.get_by_role('button', name='查看本次搜索结果').click()
            expect(main).to_have_attribute('data-page', 'videos')
            expect(panel.get_by_role('heading', name='任务详情', exact=True)).to_be_visible()
            page.reload()
            expect(panel.get_by_role('heading', name='任务详情', exact=True)).to_be_visible()
            assert writes == ['tasks']
            page.set_viewport_size(dict(width=390, height=844))
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            browser.close()
