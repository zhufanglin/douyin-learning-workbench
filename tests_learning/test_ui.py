"""Optional end-to-end check against a running local learning server.

Set LEARNING_UI_URL=http://127.0.0.1:8765. Uses intercepted local API fixtures; no real platform access.
"""
import json
import os
from pathlib import Path
from urllib.request import urlopen

import pytest
from playwright.sync_api import sync_playwright, expect

URL = os.environ.get('LEARNING_UI_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Set LEARNING_UI_URL to test the running UI.')


def test_comment_pages_show_100_then_100_then_5_without_refetching_previous_page():
    # Explicit local HTTP fixtures; no requests to Douyin and no live DB writes.
    parent = dict(id='paging-fixture', keyword='分页测试（虚构）', source='demo', status='simulated', note='模拟数据', created_at='2026-09-09T00:00:00Z')
    video = dict(id='fixture-video', title='分页测试视频（虚构）')
    child = dict(parent, id='paging-detail', status='success')
    count, requests = [100], []
    def route_api(route):
        path = route.request.url.split('/api/learning/')[1]
        if path.startswith('state'):
            data = dict(tasks=[parent], users=[], actions=[], logs=[], counts={})
        elif path.endswith('/comments/next'):
            requests.append(route.request.post_data_json)
            count[0] = min(205, count[0] + 100)
            data = child
        elif path.endswith('/comments'):
            data = child
        elif path == 'tasks/paging-detail':
            data = dict(task=child, users=[dict(id='u', nickname='虚构用户', profile_url='')],
                comments=[dict(id=str(i), user_id='u', content=f'虚构评论 {i + 1}') for i in range(count[0])],
                pagination=dict(revision=len(requests), target=count[0], exhausted=count[0] == 205))
        else:
            data = dict(task=parent, videos=[video], comments=[], users=[], logs=[])
        route.fulfill(json=data)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chromium')
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.route('**/api/learning/**', route_api)
        catalog_task = locals().get('parent', locals().get('task'))
        page.route('**/api/learning/catalog*', lambda r: r.fulfill(json=dict(tasks=[dict(catalog_task, counts=dict(videos=1, users=0, comments=0), videos=[video])], videos=[video], users=[], comments=[])))
        page.goto(URL.split('#')[0] + '#tasks')
        page.get_by_role('button').filter(has_text='→ 查看任务').first.click()
        page.get_by_role('button').filter(has_text=video['title']).click()
        page.get_by_role('button', name='读取此视频评论', exact=True).click()
        pane = page.get_by_label('所选视频评论')
        expect(pane.locator('article')).to_have_count(100)
        pane.get_by_role('button', name='下一批 100 条', exact=True).click()
        expect(pane.get_by_text('虚构评论 101', exact=True)).to_be_visible()
        expect(pane.locator('article')).to_have_count(100)
        pane.get_by_role('button', name='上一页', exact=True).click()
        expect(pane.get_by_text('虚构评论 1', exact=True)).to_be_visible()
        assert len(requests) == 1
        pane.get_by_role('button', name='下一页', exact=True).click()
        pane.get_by_role('button', name='下一批 100 条', exact=True).click()
        expect(pane.locator('article')).to_have_count(5)
        expect(pane.get_by_role('button', name='主评论已到底')).to_be_disabled()
        assert requests == [{'revision': 0}, {'revision': 1}]
        page.reload()
        expect(pane.locator('article')).to_have_count(100)
        pane.get_by_role('button', name='下一页', exact=True).click()
        expect(pane.get_by_text('虚构评论 101', exact=True)).to_be_visible()
        assert len(requests) == 2
        assert errors == []
        browser.close()


def test_reply_ui_groups_records_and_direct_export_contains_replies(tmp_path):
    import re
    parent = dict(id='reply-fixture', keyword='回复测试（虚构）', source='demo', status='success', note='本地测试', created_at='2026-09-09T00:00:00Z')
    child = dict(parent, id='reply-detail')
    video = dict(id='fixture-video', title='回复测试视频（虚构）')
    comments = [dict(id='parent', content='虚构主评论', user_id='main')]
    users = [dict(id='main', nickname='虚构主作者', profile_url=''), dict(id='reply-user', nickname='虚构回复作者', profile_url='')]
    requests = []
    def detail():
        return dict(task=child, videos=[video], comments=comments, users=users, logs=[],
            pagination=dict(revision=len(requests), target=100, exhausted=True,
                replies={'parent': dict(target=max(100, len(requests) * 100), exhausted=len(comments) == 206)}))
    def route_api(route):
        path = route.request.url.split('/api/learning/')[1]
        if path.startswith('state'): data = dict(tasks=[parent], users=[], actions=[], logs=[], counts={})
        elif path.endswith('/parent/replies'):
            requests.append(route.request.post_data_json)
            for i in range(len(comments) - 1, min(205, len(requests) * 100)):
                comments.append(dict(id=f'r{i + 1}', parent_comment_id='parent', kind='reply', content=f'虚构回复正文 {i + 1}', user_id='reply-user'))
            data = child
        elif path.endswith('/comments'): data = child
        elif path == 'tasks/reply-detail': data = detail()
        elif path.startswith('export/'):
            route.fulfill(body=json.dumps(detail(), ensure_ascii=False), content_type='application/json', headers={'Content-Disposition': 'attachment; filename="reply-fixture.json"'})
            return
        else: data = dict(task=parent, videos=[video], comments=[], users=[], logs=[])
        route.fulfill(json=data)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chromium')
        page = browser.new_page()
        page.route('**/api/learning/**', route_api)
        catalog_task = locals().get('parent', locals().get('task'))
        page.route('**/api/learning/catalog*', lambda r: r.fulfill(json=dict(tasks=[dict(catalog_task, counts=dict(videos=1, users=0, comments=0), videos=[video])], videos=[video], users=[], comments=[])))
        page.goto(URL.split('#')[0] + '#tasks')
        page.get_by_role('button').filter(has_text='→ 查看任务').first.click()
        page.get_by_role('button').filter(has_text=video['title']).click()
        page.get_by_role('button', name='读取此视频评论', exact=True).click()
        pane = page.get_by_label('所选视频评论')
        pane.get_by_role('button', name='读取回复', exact=True).click()
        thread = pane.get_by_label('此评论的回复')
        expect(thread.get_by_text('虚构回复正文 1', exact=True)).to_be_visible()
        expect(thread.get_by_text(re.compile(r'^虚构回复正文 '))).to_have_count(100)
        pane.get_by_role('button', name='继续读取回复（最多 100 条）', exact=True).click()
        expect(thread.get_by_text('虚构回复正文 101', exact=True)).to_be_visible()
        expect(thread.get_by_text(re.compile(r'^虚构回复正文 '))).to_have_count(100)
        thread.get_by_role('button', name='回复上一页', exact=True).click()
        expect(thread.get_by_text('虚构回复正文 1', exact=True)).to_be_visible()
        assert len(requests) == 2
        thread.get_by_role('button', name='回复下一页', exact=True).click()
        expect(thread.get_by_text('虚构回复正文 101', exact=True)).to_be_visible()
        pane.get_by_role('button', name='继续读取回复（最多 100 条）', exact=True).click()
        expect(thread.get_by_text('虚构回复正文 201', exact=True)).to_be_visible()
        expect(thread.get_by_text(re.compile(r'^虚构回复正文 '))).to_have_count(5)
        expect(pane.locator('article')).to_have_count(1)
        expect(pane.get_by_role('button', name='该评论回复已读完')).to_be_disabled()
        with page.expect_download() as download:
            pane.get_by_role('link', name='导出本视频评论（含已存回复）').click()
        destination = tmp_path / 'replies.json'
        download.value.save_as(destination)
        exported = json.loads(destination.read_text(encoding='utf8'))
        assert len(exported['comments']) == 206
        assert all(c['parent_comment_id'] == 'parent' for c in exported['comments'][1:])
        assert requests == [{'revision': 0}, {'revision': 1}, {'revision': 2}]
        browser.close()


@pytest.mark.parametrize('reader_version', [1, 2, 3, 4])
def test_reply_end_ui_disables_terminal_unsupported_but_allows_review_after_stall(reader_version, tmp_path):
    task = dict(id='ending-fixture', keyword='结束状态测试（虚构）', source='demo', status='partial', note='本地夹具', created_at='2026-09-09T00:00:00Z')
    video = dict(id='end-video', title='结束状态视频（虚构）')
    mode = ['unsupported']
    version = [reader_version]
    posts = []
    def api(route):
        path = route.request.url.split('/api/learning/')[1]
        if route.request.method == 'POST': posts.append(path)
        if path.startswith('state'): data = dict(tasks=[task], users=[], actions=[], logs=[], counts={})
        elif path.endswith('/comments'): data = dict(task, id='end-detail')
        elif path in ('tasks/end-detail', 'export/end-detail'):
            data = dict(task=dict(task, id='end-detail'), videos=[video], users=[], logs=[],
                comments=[dict(id='parent', content='主评论（虚构）', user_id='u', content_status='image_not_read', image_count=1),
                    dict(id='emoji', parent_comment_id='parent', user_id='u', content='[看][流泪]', content_type='emoji', emoji_labels=['[看]', '[流泪]']),
                    dict(id='image', parent_comment_id='parent', user_id='u', content='图片内容未读取', content_type='image_placeholder', content_status='image_not_read', image_count=2)],
                pagination=dict(revision=1, target=100, exhausted=True,
                    replies={'parent': dict(target=100, exhausted=False, end_state=mode[0], page_end=mode[0]=='unsupported', unsupported_count=2, image_placeholder_count=1, reader_version=version[0])}))
        else: data = dict(task=task, videos=[video], users=[], comments=[], logs=[])
        if path.startswith('export/'):
            route.fulfill(body=json.dumps(data), content_type='application/json', headers={'Content-Disposition':'attachment; filename="image-fixture.json"'})
        else:
            route.fulfill(json=data)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chromium')
        page = browser.new_page()
        page.route('**/api/learning/**', api)
        catalog_task = locals().get('parent', locals().get('task'))
        page.route('**/api/learning/catalog*', lambda r: r.fulfill(json=dict(tasks=[dict(catalog_task, counts=dict(videos=1, users=0, comments=0), videos=[video])], videos=[video], users=[], comments=[])))
        page.goto(URL.split('#')[0] + '#tasks')
        page.get_by_role('button').filter(has_text='→ 查看任务').first.click()
        page.get_by_role('button').filter(has_text=video['title']).click()
        page.get_by_role('button', name='读取此视频评论', exact=True).click()
        pane = page.get_by_label('所选视频评论')
        if reader_version < 4:
            expect(pane.get_by_role('button', name='补读表情与图片标识' if reader_version == 1 else '补读图片标识', exact=True)).to_be_enabled()
            assert not any(path.endswith('/replies') for path in posts)
            version[0] = 4
        expect(pane.get_by_role('button', name='已到页尾 · 有未支持内容', exact=True)).to_be_disabled()
        expect(pane.get_by_text('另有 2 条未识别内容未保存。', exact=True)).to_be_visible()
        expect(pane.get_by_text('已保存 1 条含图片的回复标识，图片内容未读取。', exact=True)).to_be_visible()
        expect(pane.get_by_text('图片内容未读取（1 张）', exact=True)).to_be_visible()
        assert not any(path.endswith('/replies') for path in posts)
        mode[0] = 'blocked'
        expect(pane.get_by_text('加载受阻或结束状态未确认，请核对页面后继续。', exact=True)).to_be_visible(timeout=5000)
        expect(pane.get_by_role('button', name='核对页面后继续回复', exact=True)).to_be_enabled()
        pane.get_by_role('button', name='查看已存回复（2）', exact=True).click()
        expect(pane.get_by_label('此评论的回复').get_by_text('[看][流泪]', exact=True)).to_be_visible()
        expect(pane.get_by_label('此评论的回复').get_by_text('图片内容未读取', exact=True)).to_be_visible()
        assert pane.get_by_label('此评论的回复').locator('img').count() == 0
        with page.expect_download() as download:
            pane.get_by_role('link', name='导出本视频评论（含已存回复）').click()
        destination = tmp_path / 'images.json'
        download.value.save_as(destination)
        exported = json.loads(destination.read_text(encoding='utf8'))
        assert exported['comments'][-1]['content_status'] == 'image_not_read'
        assert exported['comments'][-1]['image_count'] == 2
        browser.close()
