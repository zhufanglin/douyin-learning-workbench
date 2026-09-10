import os
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright, expect

URL = os.environ.get('LEARNING_UI_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Set LEARNING_UI_URL')


def test_search_feedback_pending_running_pause_results_and_motion(tmp_path):
    task = dict(id='feedback-search', keyword='交互测试', source='live', status='running', note='正在打开抖音搜索页', created_at='2026-09-10T00:00:00+00:00')
    detail = dict(task=task, videos=[], comments=[], users=[], logs=[])
    pending, writes, errors = [], [], []
    broken = [False]
    def route_api(route):
        path = route.request.url.split('/api/learning/')[1]
        if route.request.method == 'POST':
            writes.append(path)
            if path == 'tasks':
                pending.append(route)
            elif path == 'tasks/feedback-search/cancel':
                task.update(status='cancelled', note='任务已暂停，已保存结果保留')
                route.fulfill(json=task)
            else:
                route.fulfill(status=409, json={'detail': '测试不允许该操作'})
        elif path.startswith('state'):
            route.fulfill(json=dict(tasks=[task] if pending else [], counts={}, logs=[], capabilities=dict(video_url_read=True)))
        elif path.startswith('catalog'):
            route.fulfill(json=dict(tasks=[], videos=[], users=[], comments=[]))
        elif path == 'tasks/feedback-search':
            route.fulfill(status=503 if broken[0] else 200, json={'detail': '暂时断开'} if broken[0] else detail)
        else:
            route.fulfill(status=404, json={'detail': path})
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chromium')
        page = browser.new_page(viewport=dict(width=1366, height=768))
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.route('**/api/learning/**', route_api)
        page.goto(URL.split('#')[0] + '#keyword')
        page.get_by_label('关键词', exact=True).fill('交互测试')
        page.get_by_role('button', name='开始网页读取', exact=True).click()
        expect(page.get_by_role('button', name='正在提交…', exact=True)).to_be_disabled()
        feedback = page.get_by_role('region', name='本次搜索进度')
        expect(feedback).to_be_visible()
        assert feedback.bounding_box()['y'] < 600
        expect(feedback.get_by_text('正在提交搜索请求', exact=True)).to_be_visible()
        pending[0].fulfill(json=task)
        expect(page.get_by_role('button', name='正在读取…', exact=True)).to_be_disabled()
        detail['videos'] = [dict(id=str(i), title=f'测试视频 {i}') for i in range(37)]
        task['note'] = '已收集 37/100 个视频，正在读取'
        expect(feedback.get_by_text('已保存 37 / 100 个视频', exact=True)).to_be_visible()
        expect(feedback.get_by_role('progressbar')).to_have_attribute('aria-valuenow', '37')
        page.reload()
        expect(page.get_by_role('button', name='正在读取…', exact=True)).to_be_disabled()
        expect(feedback.get_by_text('已保存 37 / 100 个视频', exact=True)).to_be_visible()
        evidence = Path(os.environ.get('LEARNING_EVIDENCE_DIR', str(tmp_path)))
        evidence.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(evidence/'search-running.png'), animations='disabled')
        task.update(status='waiting_verification', note='请本人完成图形验证，再继续读取')
        expect(feedback.get_by_text('需要你完成验证', exact=True)).to_be_visible()
        expect(feedback.get_by_role('progressbar')).to_have_attribute('aria-valuenow', '37')
        task.update(status='partial', note='页面暂时没有更多视频，保留已收集结果')
        expect(feedback.get_by_text('已保存部分结果', exact=True)).to_be_visible()
        expect(feedback.get_by_role('progressbar')).to_have_attribute('aria-valuenow', '37')
        task.update(status='search_exhausted', note='当前视频搜索页明确提示没有更多结果')
        expect(feedback.get_by_text('视频搜索页已到底', exact=True)).to_be_visible()
        expect(feedback.get_by_role('progressbar')).to_have_attribute('aria-valuenow', '37')
        task.update(status='search_stalled', note='连续 30 秒没有新增视频，未确认页面到底')
        expect(feedback.get_by_text('等待新结果超时，已保留数据', exact=True)).to_be_visible()
        task.update(status='failed', note='页面读取超时，请核对页面')
        expect(feedback.get_by_text('读取失败', exact=True)).to_be_visible()
        task.update(status='running', note='正在继续读取')
        expect(feedback.get_by_role('button', name='暂停读取', exact=True)).to_be_visible()
        broken[0] = True
        expect(feedback.get_by_text('状态更新中断，请先核对任务；不要重复提交。', exact=True)).to_be_visible(timeout=15000)
        expect(page.get_by_role('button', name='正在读取…', exact=True)).to_be_disabled()
        broken[0] = False
        feedback.get_by_role('button', name='重新核对状态').click()
        expect(feedback.get_by_text('状态更新中断，请先核对任务；不要重复提交。', exact=True)).to_have_count(0)
        feedback.get_by_role('button', name='暂停读取', exact=True).click()
        expect(feedback.get_by_text('已暂停读取', exact=True)).to_be_visible()
        assert writes == ['tasks', 'tasks/feedback-search/cancel']
        task.update(status='success', note='已保存全部本次结果')
        expect(feedback.get_by_text('本次读取完成', exact=True)).to_be_visible()
        feedback.get_by_role('button', name='查看本次搜索结果').click()
        expect(page.locator('main')).to_have_attribute('data-page', 'videos')
        expect(page.get_by_role('heading', name='任务详情', exact=True)).to_be_visible()
        page.emulate_media(reduced_motion='reduce')
        page.get_by_role('navigation').get_by_role('link', name='新建搜索', exact=True).click()
        assert page.locator('main').evaluate('(el) => getComputedStyle(el).animationName') == 'none'
        page.set_viewport_size(dict(width=390, height=844))
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        page.screenshot(path=str(evidence/'search-mobile.png'), animations='disabled')
        assert errors == []
        browser.close()
