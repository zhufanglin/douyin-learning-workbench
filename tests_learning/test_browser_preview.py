import threading
from fastapi.testclient import TestClient
from learning.app import create_app
from learning.preview import BrowserPreview


class Page:
    url='https://www.douyin.com/search/test'
    closed=False
    shots=0
    focused=0
    def is_closed(self): return self.closed
    def screenshot(self,**kwargs):
        self.shots+=1
        return ('frame'+str(self.shots)).encode()
    def bring_to_front(self): self.focused+=1


def test_preview_lease_throttle_close_and_non_platform_page():
    clock=[100.0]; preview=BrowserPreview(clock=lambda:clock[0]); page=Page()
    preview.capture(page); assert page.shots==0
    preview.request(); preview.capture(page)
    assert preview.snapshot()['image'].startswith('data:image/jpeg;base64,')
    preview.capture(page); assert page.shots==1
    clock[0]+=2; preview.capture(page); assert page.shots==2
    clock[0]+=20; preview.capture(page); assert page.shots==2
    preview.request(); page.url='https://example.com/private'; preview.capture(page)
    assert preview.snapshot()['image'] is None
    clock[0]+=2; page.closed=True; preview.capture(page)
    assert preview.snapshot()['status']=='closed'


def test_capture_failure_never_fails_task_and_focus_is_one_shot():
    preview=BrowserPreview(); page=Page(); preview.request(focus=True)
    page.screenshot=lambda **kwargs: (_ for _ in ()).throw(RuntimeError('rendering'))
    preview.capture(page); preview.capture(page)
    assert page.focused==1
    assert preview.snapshot()['status']=='waiting'


def test_busy_worker_produces_preview_without_queuing_behind_task(tmp_path):
    from learning.browser import BrowserReader
    reader=BrowserReader(tmp_path/'browser'); entered=threading.Event(); release=threading.Event()
    page=Page()
    def task():
        reader.page=page; reader.preview.capture(page); entered.set(); release.wait(3)
    reader.busy=True
    reader.preview_snapshot()
    job=reader.pool.submit(task)
    try:
        assert entered.wait(2)
        assert reader.preview_snapshot()['image'] is not None
        assert not job.done()
    finally:
        release.set(); job.result(); reader.pool.shutdown()


def test_preview_api_does_not_start_browser_and_disables_caching(tmp_path):
    with TestClient(create_app(tmp_path/'a.db')) as api:
        r=api.get('/api/learning/browser/preview')
        assert r.status_code==200
        assert r.json()['status']=='idle'
        assert r.headers['cache-control']=='no-store'
        assert api.app.state.reader is None
        assert api.post('/api/learning/browser/focus',json={}).status_code==409


def test_real_rendered_frames_change_while_worker_is_busy(tmp_path):
    from playwright.sync_api import sync_playwright
    from learning.browser import BrowserReader,check_page
    reader=BrowserReader(tmp_path/'profile');reader.busy=True
    first=threading.Event();advance=threading.Event();second=threading.Event();finish=threading.Event()
    reader.preview_snapshot()
    def work():
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,channel='chromium');page=browser.new_page()
            page.route('**/*',lambda r:r.fulfill(body='<body style="background:red">Fixture only</body>',content_type='text/html'))
            page.goto('https://www.douyin.com/search/fixture');reader.page=page
            page._learning_preview_capture=lambda:reader.preview.capture(page)
            check_page(page);first.set();advance.wait(5)
            page.wait_for_timeout(1300)
            page.evaluate("document.body.style.background='blue'");check_page(page);second.set();finish.wait(5)
            browser.close();reader.page=None
    job=reader.pool.submit(work)
    try:
        assert first.wait(10)
        a=reader.preview_snapshot();assert a['image'] and a['busy']
        advance.set();assert second.wait(5)
        b=reader.preview_snapshot();assert b['image']!=a['image'] and b['sequence']>a['sequence']
        assert not job.done()
    finally:
        advance.set();finish.set();job.result(timeout=10);reader.pool.shutdown()
