"""Persist browser-provided downloads; no media API, signing or access bypass."""
import json
import re
import threading
import zipfile
from pathlib import Path
from .store import now

ACTIVE = ('queued','running')


class Downloads:
    def __init__(self, store):
        self.root = store.path.parent / 'downloads'
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        for path in self.root.glob('*/job.json'):
            job = json.loads(path.read_text(encoding='utf-8'))
            if job['status'] in ACTIVE:
                self.finish(job['id'], 'interrupted', '服务重启，下载中断；未自动重试。')
                self.archive(job['id'])

    def folder(self, identity):
        if not re.fullmatch('[a-f0-9]{32}', identity): raise KeyError(identity)
        return self.root / identity

    def get(self, identity):
        with self.lock:
            path = self.folder(identity) / 'job.json'
            if not path.exists(): raise KeyError(identity)
            return json.loads(path.read_text(encoding='utf-8'))

    def save(self, job):
        path = self.folder(job['id']) / 'job.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(path)

    def list(self):
        with self.lock:
            return sorted([self.get(p.parent.name) for p in self.root.glob('*/job.json')], key=lambda j:j['created_at'], reverse=True)[:20]

    def create(self, identity, videos):
        with self.lock:
            if (self.folder(identity)/'job.json').exists():
                job = self.get(identity)
                if [(r['source'],r['id']) for r in job['items']] != [(r['source'],r['id']) for r in videos]:
                    raise ValueError('此下载请求编号已用于其他记录。')
                return job, False
            if any(j['status'] in ACTIVE for j in self.list()):
                raise ValueError('已有视频下载正在进行，请等待完成或停止。')
            job = dict(id=identity, created_at=now(), status='queued', note='等待浏览器逐条下载', ready=False, cancel_requested=False,
                       items=[dict(id=v['id'],source=v['source'],title=v.get('title') or v['id'],status='queued',attempted=False,note='等待下载') for v in videos])
            self.save(job)
            return job, True

    def update_item(self, identity, index, **fields):
        with self.lock:
            job = self.get(identity)
            job['status'] = 'running'
            job['items'][index]['attempted'] = True
            job['items'][index].update(fields)
            self.save(job)

    def cancel(self, identity):
        with self.lock:
            job = self.get(identity)
            if job['status'] in ACTIVE:
                job['cancel_requested'] = True
                job['note'] = '正在停止，当前下载处理结束后不再读取下一条。'
                self.save(job)
            return job

    def finish(self, identity, status, note):
        with self.lock:
            job = self.get(identity)
            for item in job['items']:
                if item['status'] in ACTIVE: item.update(status=status, note=note if item.get('attempted') else '未执行：'+note)
            job.update(status=status,note=note)
            self.save(job)

    def archive(self, identity):
        with self.lock:
            job = self.get(identity)
            if job['status'] in ACTIVE: raise ValueError('下载尚未结束。')
            files = [i for i in job['items'] if i['status']=='success']
            if not files: return
            folder = self.folder(identity)
            with zipfile.ZipFile(folder/'videos.tmp', 'w', compression=zipfile.ZIP_STORED) as archive:
                for item in files: archive.write(folder/item['file'], item['file'])
                archive.writestr('results.json', json.dumps(job, ensure_ascii=False, indent=2))
            (folder/'videos.tmp').replace(folder/'videos.zip')
            job['ready'] = True
            self.save(job)


def download_one(page, item, folder):
    from .browser import check_page, current_video_id, PagePaused
    from playwright.sync_api import TimeoutError
    if not re.fullmatch(r'\d{5,30}', item['id']):
        return dict(status='unavailable',note='记录没有有效的抖音视频编号。')
    page.goto('https://www.douyin.com/video/'+item['id'], wait_until='domcontentloaded', timeout=30000)
    page.wait_for_timeout(1000)
    check_page(page)
    if current_video_id(page.url) != item['id']:
        return dict(status='unavailable',note='页面未打开目标视频。')
    # Only an unambiguous, visible download control provided by the normal page.
    controls = page.get_by_role('button',name=re.compile(r'^(下载|下载视频)$')).all() + page.get_by_role('link',name=re.compile(r'^(下载|下载视频)$')).all()
    controls = [c for c in controls if c.is_visible() and c.is_enabled()]
    if len(controls) != 1:
        return dict(status='unavailable',note='页面未提供可识别的下载入口；可打开原视频手动检查。')
    try:
        with page.expect_download(timeout=15000) as info: controls[0].click(timeout=5000)
        download = info.value
    except TimeoutError:
        check_page(page)
        return dict(status='unavailable',note='页面没有返回视频文件，可能要求使用客户端或不允许下载。')
    suffix = Path(download.suggested_filename).suffix.lower()
    if suffix not in ('.mp4','.webm','.mov'):
        download.cancel()
        return dict(status='unavailable',note='下载返回的不是支持的视频文件。')
    filename = item['source']+'-'+item['id']+suffix
    path = folder/filename
    download.save_as(str(path))
    with path.open('rb') as stream: signature = stream.read(32)
    if not (signature[4:8] == b'ftyp' or signature[:4] == b'\x1aE\xdf\xa3'):
        path.unlink(missing_ok=True)
        return dict(status='failed',note='文件内容不是可识别的视频，未纳入下载包。')
    return dict(status='success',note='已保存平台提供的视频文件。',file=filename,bytes=path.stat().st_size)


def run_downloads(page, manager, identity):
    from .browser import PagePaused
    job = manager.get(identity)
    status, note = 'completed', '下载处理完毕，请查看每条结果。'
    try:
        for index, item in enumerate(job['items']):
            if manager.get(identity)['cancel_requested']:
                status,note = 'cancelled','已停止，未继续下载剩余视频。'
                break
            manager.update_item(identity,index,status='running',note='正在检查页面下载入口…')
            try:
                result = download_one(page,item,manager.folder(identity))
            except PagePaused as exc:
                status,note = 'paused',str(exc)
                manager.update_item(identity,index,status='paused',note=note)
                break
            except Exception as exc:
                result = dict(status='failed',note='下载失败（'+type(exc).__name__+'），未自动重试。')
            manager.update_item(identity,index,**result)
    except Exception:
        status,note = 'failed','下载处理中断，未自动重试。'
        raise
    finally:
        manager.finish(identity,status,note)
        manager.archive(identity)
