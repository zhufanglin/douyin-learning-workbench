import json
import zipfile
from playwright.sync_api import sync_playwright
from learning.downloads import Downloads, run_downloads
from learning.store import Store


def test_native_file_missing_control_verification_stops_batch(tmp_path):
    manager = Downloads(Store(tmp_path/'d.db'))
    videos = [dict(id=str(10000+i),source='live',title='测试视频'+str(i)) for i in range(4)]
    job,_ = manager.create('a'*32,videos)
    visits = []
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,channel='chromium'); page=browser.new_page()
        def route(r):
            url=r.request.url
            if url.endswith('/file.mp4'):
                r.fulfill(body=b'\x00\x00\x00\x18ftypisom'+b'\x00'*32,headers={'Content-Type':'video/mp4','Content-Disposition':'attachment; filename=sample.mp4'})
            else:
                visits.append(url)
                body = '<a id="file" download="sample.mp4">下载视频</a><script>file.href=URL.createObjectURL(new Blob([new Uint8Array([0,0,0,24,102,116,121,112,105,115,111,109,0,0,0,0])],{type:"video/mp4"}))</script>' if url.endswith('10000') else '安全验证' if url.endswith('10002') else '视频暂无下载入口'
                r.fulfill(body='<meta charset="utf-8">'+body,content_type='text/html')
        page.route('**/*',route)
        run_downloads(page,manager,job['id'])
        result=manager.get(job['id'])
        assert [i['status'] for i in result['items']] == ['success','unavailable','paused','paused']
        assert result['ready'] and result['status']=='paused'
        assert not any(url.endswith('10003') for url in visits)
        with zipfile.ZipFile(manager.folder(job['id'])/'videos.zip') as z:
            assert z.namelist()==['live-10000.mp4','results.json']
            assert json.loads(z.read('results.json'))['items'][0]['status']=='success'
        browser.close()


def test_cancel_before_navigation_and_wrong_file(tmp_path):
    from learning.downloads import download_one
    manager=Downloads(Store(tmp_path/'d.db'))
    video=dict(id='12345',source='live',title='视频')
    job,_=manager.create('a'*32,[video]); manager.cancel(job['id'])
    run_downloads(None,manager,job['id'])
    assert manager.get(job['id'])['status']=='cancelled'
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,channel='chromium'); page=browser.new_page()
        def route(r):
            if r.request.url.endswith('/file.mp4'):
                r.fulfill(body=b'<html>Error</html>',headers={'Content-Type':'video/mp4','Content-Disposition':'attachment; filename=x.mp4'})
            else: r.fulfill(body='<meta charset="utf-8"><a id="file" download="bad.mp4">下载视频</a><script>file.href=URL.createObjectURL(new Blob(["Error"],{type:"video/mp4"}))</script>',content_type='text/html')
        page.route('**/*',route)
        result=download_one(page,video,manager.folder(job['id']))
        assert result['status']=='failed'
        assert not list(manager.folder(job['id']).glob('*.mp4'))
        browser.close()
