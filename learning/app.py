import json
import os
import threading
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .service import demo_search, import_records
from .store import Store

ROOT = Path(__file__).resolve().parent.parent


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    keyword: str = Field(min_length=1, max_length=80)
    source: Literal['demo', 'live'] = 'demo'
    limit: int = Field(default=100, ge=1, le=100)

    @field_validator('keyword')
    @classmethod
    def trim(cls, value):
        if not value.strip():
            raise ValueError('请输入关键词。')
        return value.strip()


class VideoMetadataRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    video_ids: list[str] = Field(min_length=1, max_length=100)


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source: Literal['demo', 'live', 'import']
    user_id: str = Field(min_length=1, max_length=200)
    kind: Literal['follow', 'message']
    message: str = Field(default='', max_length=500)


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    records: list[dict] = Field(min_length=1, max_length=500)


class VideoRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    url: str = Field(min_length=1, max_length=2000)

    @field_validator('url')
    @classmethod
    def video_url(cls, value):
        from .browser import current_video_id
        video_id = current_video_id(value.strip())
        if not video_id:
            raise ValueError('请输入抖音视频详情链接或带 modal_id 的弹窗链接。')
        return f'https://www.douyin.com/video/{video_id}'


class CommentBatchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=0)


class DeleteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['tasks', 'videos', 'users', 'comments', 'logs']
    source: Literal['live', 'import']
    id: str = Field(min_length=1, max_length=300)


class DeleteCommitRequest(DeleteRequest):
    token: str = Field(min_length=64, max_length=64)


class BatchDeleteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    targets: list[DeleteRequest] = Field(min_length=1, max_length=500)


class BatchDeleteCommitRequest(BatchDeleteRequest):
    token: str = Field(min_length=64, max_length=64)


class ExportRequest(BatchDeleteRequest):
    format: Literal['json','csv'] = 'json'
    task_id: str = Field(default='',max_length=300)


class DownloadRequest(BatchDeleteRequest):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')


class AccountPrepareRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sender: str = Field(min_length=1, max_length=1000)
    target: str = Field(min_length=1, max_length=1000)
    kind: Literal['follow','message']
    message: str = Field(default='', max_length=500)
    authorized: Literal[True]

    @field_validator('message')
    @classmethod
    def trim_message(cls, value):
        return value.strip()

    @field_validator('sender')
    @classmethod
    def normalize_sender(cls, value):
        from .account_browser import sender_identity
        return sender_identity(value)

    @field_validator('target')
    @classmethod
    def normalize_profile(cls, value):
        from .account_browser import profile_url
        return profile_url(value)


class AccountConfirmRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(min_length=1,max_length=100)
    confirmed: Literal[True]


def create_app(db_path=None):
    store = Store(db_path or os.environ.get('LEARNING_DB') or ROOT / 'learning_data' / 'learning.db')
    store.recover()
    from .account_actions import AccountActions
    account_ledger = AccountActions(store)
    from .downloads import Downloads
    downloads = Downloads(store)

    @asynccontextmanager
    async def lifespan(app):
        yield
        if getattr(app.state, 'reader', None):
            app.state.reader.close()

    app = FastAPI(title='抖音学习工作台', version='0.1.0', lifespan=lifespan)
    app.state.store = store
    app.state.account_ledger = account_ledger
    app.state.downloads = downloads
    app.state.reader = None
    app.state.reader_lock = threading.Lock()
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])

    @app.middleware('http')
    async def local_boundary(request: Request, call_next):
        origin = request.headers.get('origin')
        if origin and urlparse(origin).netloc != request.headers.get('host'):
            return JSONResponse({'detail': '仅接受本地同源请求。'}, status_code=403)
        if request.method in ('POST', 'PUT', 'PATCH'):
            try:
                length = int(request.headers.get('content-length', '0'))
            except ValueError:
                return JSONResponse({'detail': '无效请求长度。'}, status_code=400)
            if length > 2_000_000:
                return JSONResponse({'detail': '导入文件不得超过 2 MB。'}, status_code=413)
        return await call_next(request)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({'detail': '记录不存在。'}, status_code=404)

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'app': 'douyin-learning', 'version': '0.1.0', 'pid': os.getpid()}

    @app.get('/api/learning/state')
    def state(include_demo: bool = True):
        return {**store.snapshot(include_demo=include_demo), 'capabilities': {'video_url_read': True}}

    @app.get('/api/learning/browser/preview')
    def browser_preview():
        reader=app.state.reader
        data=reader.preview_snapshot() if reader else dict(status='idle',image=None,url='',sequence=0,age_ms=None,busy=False)
        return JSONResponse(data,headers={'Cache-Control':'no-store'})

    @app.post('/api/learning/browser/focus')
    def browser_focus():
        reader=app.state.reader
        if reader is None: raise HTTPException(409,detail='浏览器尚未启动，请先开始网页任务。')
        reader.preview_snapshot(focus=True)
        return {'note':'已请求切换到当前执行浏览器。'}

    @app.post('/api/learning/deletion/batch-preview')
    def batch_deletion_preview(request: BatchDeleteRequest):
        from .deletion import delete_batch
        try:
            return delete_batch(store, [r.model_dump() for r in request.targets])
        except ValueError as exc:
            raise HTTPException(409, detail=str(exc))

    @app.post('/api/learning/export-selected')
    def export_selected(request: ExportRequest):
        from .exports import selected_records, encode_export
        try:
            data = selected_records(store, [r.model_dump() for r in request.targets], request.task_id)
            body, media = encode_export(data, request.format)
            return Response(body, media_type=media, headers={'Content-Disposition':f'attachment; filename="selected-{data["kind"]}.{request.format}"'})
        except ValueError as exc:
            raise HTTPException(409, detail=str(exc))

    @app.get('/api/learning/downloads')
    def download_list():
        return {'items':downloads.list()}

    @app.post('/api/learning/downloads')
    def download_create(request: DownloadRequest):
        from .exports import selected_records
        from .browser import BrowserReader
        if any(t.kind != 'videos' for t in request.targets) or len(request.targets)>100:
            raise HTTPException(422, detail='请选择 1 至 100 条视频。')
        try:
            data = selected_records(store,[r.model_dump() for r in request.targets])
            job, created = downloads.create(request.request_id,data['records'])
            if created:
                with app.state.reader_lock:
                    if app.state.reader is None: app.state.reader = BrowserReader(ROOT/'learning_data'/'browser')
                app.state.reader.submit_downloads(downloads,job['id'])
            return downloads.get(job['id'])
        except ValueError as exc:
            raise HTTPException(409, detail=str(exc))

    @app.post('/api/learning/downloads/{identity}/cancel')
    def download_cancel(identity: str):
        return downloads.cancel(identity)

    @app.get('/api/learning/downloads/{identity}/file')
    def download_file(identity: str):
        job = downloads.get(identity)
        if not job['ready']: raise HTTPException(409,detail='没有已完成的视频下载包。')
        return FileResponse(downloads.folder(identity)/'videos.zip',media_type='application/zip',filename=f'videos-{identity}.zip')

    @app.post('/api/learning/deletion/batch-commit')
    def batch_deletion_commit(request: BatchDeleteCommitRequest):
        from .deletion import delete_batch
        try:
            return delete_batch(store, [r.model_dump() for r in request.targets], request.token)
        except ValueError as exc:
            raise HTTPException(409, detail=str(exc))

    @app.post('/api/learning/deletion/preview')
    def deletion_preview(request: DeleteRequest):
        from .deletion import delete_records
        try:
            return delete_records(store, request.kind, request.source, request.id)
        except ValueError as exc:
            raise HTTPException(409, detail=str(exc))

    @app.post('/api/learning/deletion/commit')
    def deletion_commit(request: DeleteCommitRequest):
        from .deletion import delete_records
        try:
            return delete_records(store, request.kind, request.source, request.id, request.token)
        except ValueError as exc:
            raise HTTPException(409, detail=str(exc))

    @app.post('/api/learning/tasks')
    def create_task(request: SearchRequest):
        task = store.create_task(request.keyword, request.source)
        if request.source == 'demo':
            result = demo_search(request.keyword)
            return store.finish(task['id'], result, 'simulated',
                                f"模拟完成：{len(result['videos'])} 个视频，{len(result['comments'])} 条评论；未访问抖音。")
        # Loaded only for an explicitly selected real read. No original crawler imports.
        from .browser import BrowserReader
        with app.state.reader_lock:
            if app.state.reader is None:
                app.state.reader = BrowserReader(ROOT / 'learning_data' / 'browser')
        app.state.reader.submit(store, task, limit=request.limit)
        return store.get_task(task['id'])

    @app.get('/api/learning/catalog')
    def read_catalog(keyword: str = '', task_id: str = '', start: datetime | None = None, end: datetime | None = None):
        from .catalog import catalog
        return catalog(store, keyword, task_id,
            (start if start.tzinfo else start.replace(tzinfo=timezone.utc)).isoformat() if start else '',
            (end if end.tzinfo else end.replace(tzinfo=timezone.utc)).isoformat() if end else '')

    @app.post('/api/learning/tasks/{task_id}/resume-search')
    def resume_search(task_id: str):
        previous = store.get_task(task_id)
        if previous['source'] != 'live' or app.state.reader is None:
            raise HTTPException(409, detail='请先打开真实关键词搜索页面。')
        task = store.create_task(previous['keyword'], 'live')
        app.state.reader.submit(store, task, search_current=True)
        return store.get_task(task['id'])

    @app.post('/api/learning/browser/search-current')
    def current_search(request: SearchRequest):
        if app.state.reader is None:
            raise HTTPException(409, detail='请先运行一次网页搜索。')
        task = store.create_task(request.keyword, 'live')
        app.state.reader.submit(store, task, search_current=True, limit=request.limit)
        return store.get_task(task['id'])

    @app.post('/api/learning/tasks/{task_id}/video-metadata')
    def video_metadata(task_id: str, request: VideoMetadataRequest):
        parent=store.result(task_id)
        if parent['task']['source']!='live':
            raise HTTPException(409, detail='仅能补充真实网页视频；导入数据请使用已有指标。')
        import re
        ids=list(dict.fromkeys(request.video_ids))
        by_id={v['id']:v for v in parent['videos']}
        if any(not re.fullmatch(r'[0-9]{5,30}',vid) or vid not in by_id for vid in ids):
            raise HTTPException(400, detail='所选视频不在这个任务中，或视频编号无效。')
        from .browser import BrowserReader
        with app.state.reader_lock:
            if app.state.reader is None: app.state.reader=BrowserReader(ROOT/'learning_data'/'browser')
            try: return app.state.reader.submit_video_metadata(store,parent['task'],[by_id[vid] for vid in ids])
            except ValueError as exc: raise HTTPException(409,detail=str(exc))

    @app.post('/api/learning/tasks/{task_id}/videos/{video_id}/comments')
    def selected_video(task_id: str, video_id: str):
        parent = store.result(task_id)
        video = next((v for v in parent['videos'] if v['id'] == video_id), None)
        if video is None:
            raise HTTPException(404, detail='该视频不在所选任务结果中。')
        if parent['task']['source'] == 'live':
            request = VideoRequest(url=video['url'])
            return open_video(request)
        comments = [c for c in parent['comments'] if c['video_id'] == video_id]
        user_ids = {c['user_id'] for c in comments}
        task = store.create_task('查看视频：' + video.get('title', video_id)[:60], parent['task']['source'])
        return store.finish(task['id'], {'videos': [video], 'comments': comments,
            'users': [u for u in parent['users'] if u['id'] in user_ids]},
            'simulated' if parent['task']['source'] == 'demo' else 'success', '已显示该视频保存的评论与用户；未访问真实平台。')

    @app.post('/api/learning/browser/read-current')
    def read_current():
        if app.state.reader is None:
            raise HTTPException(409, detail='请先运行一次网页读取，打开本工具的浏览器。')
        task = store.create_task('读取当前视频评论', 'live')
        app.state.reader.submit(store, task, current=True)
        return store.get_task(task['id'])

    @app.post('/api/learning/browser/open-video')
    def open_video(request: VideoRequest):
        from .browser import BrowserReader
        task = store.create_task('读取指定视频评论', 'live')
        with app.state.reader_lock:
            if app.state.reader is None:
                app.state.reader = BrowserReader(ROOT / 'learning_data' / 'browser')
        app.state.reader.submit(store, task, direct_url=request.url)
        return store.get_task(task['id'])

    @app.get('/api/learning/tasks/{task_id}')
    def result(task_id: str):
        data = store.result(task_id)
        image_path = store.path.parent / 'diagnostics' / f'{task_id}.png'
        data['screenshot_url'] = f'/api/learning/tasks/{task_id}/screenshot' if image_path.is_file() else None
        return data

    @app.post('/api/learning/tasks/{task_id}/comments/next')
    def next_comments(task_id: str, request: CommentBatchRequest):
        from .browser import BrowserReader
        try:
            task = store.begin_comment_batch(task_id, request.revision)
        except ValueError as exc:
            raise HTTPException(409, detail=str(exc)) from exc
        with app.state.reader_lock:
            if app.state.reader is None:
                app.state.reader = BrowserReader(ROOT / 'learning_data' / 'browser')
        paging = store.result(task_id)['pagination']
        app.state.reader.submit(store, task, direct_url=f"https://www.douyin.com/video/{paging['video_id']}")
        return store.get_task(task_id)

    @app.get('/api/learning/tasks/{task_id}/screenshot')
    def screenshot(task_id: str):
        store.get_task(task_id)
        path = store.path.parent / 'diagnostics' / f'{task_id}.png'
        if not path.is_file():
            raise HTTPException(404, detail='此任务没有诊断截图。')
        return FileResponse(path, media_type='image/png', headers={'Cache-Control': 'no-store'})

    @app.post('/api/learning/tasks/{task_id}/comments/{parent_id}/replies')
    def read_replies(task_id: str, parent_id: str, request: CommentBatchRequest):
        from .browser import BrowserReader
        try:
            task = store.begin_reply_batch(task_id, parent_id, request.revision)
        except ValueError as exc:
            raise HTTPException(409, detail=str(exc)) from exc
        with app.state.reader_lock:
            if app.state.reader is None:
                app.state.reader = BrowserReader(ROOT / 'learning_data' / 'browser')
        paging = store.result(task_id)['pagination']
        app.state.reader.submit(store, task, direct_url=f"https://www.douyin.com/video/{paging['video_id']}")
        return store.get_task(task_id)

    @app.post('/api/learning/tasks/{task_id}/cancel')
    def cancel(task_id: str):
        return store.cancel(task_id)

    def action_reader():
        from .browser import BrowserReader
        with app.state.reader_lock:
            if app.state.reader is None:
                app.state.reader = BrowserReader(ROOT / 'learning_data' / 'browser')
        return app.state.reader

    @app.post('/api/learning/account-actions/browser/inspect')
    def inspect_account_browser():
        try: return action_reader().inspect_account_browser()
        except ValueError as exc: raise HTTPException(409,detail=str(exc))
        except Exception: raise HTTPException(409,detail='账号核对未完成，请检查工具浏览器；未执行关注或发送。')

    @app.post('/api/learning/account-actions/browser/open')
    def open_account_browser():
        try: return action_reader().open_account_browser()
        except ValueError as exc: raise HTTPException(409,detail=str(exc))
        except Exception: raise HTTPException(503,detail='打开浏览器未完成，请检查独立浏览器窗口。未关注或发送。')

    @app.get('/api/learning/account-actions')
    def account_actions():
        return {'items':account_ledger.list()}

    @app.post('/api/learning/account-actions/prepare')
    def prepare_account_action(request: AccountPrepareRequest):
        if request.sender == request.target:
            raise HTTPException(422, detail='请选择与本人不同的测试对象。')
        if request.kind=='message' and not request.message.strip():
            raise HTTPException(422, detail='请输入要确认发送的消息。')
        if request.kind=='follow' and request.message:
            raise HTTPException(422, detail='关注操作不应包含消息。')
        intent = account_ledger.prepare(request.model_dump(exclude={'authorized'}))
        if intent.pop('dispatch',False):
            action_reader().submit_account_action(account_ledger, intent, 'prepare')
        return account_ledger.get(intent['id'])

    @app.get('/api/learning/account-actions/{id}')
    def account_action(id: str):
        return account_ledger.get(id)

    @app.post('/api/learning/account-actions/{id}/confirm')
    def confirm_account_action(id: str, request: AccountConfirmRequest):
        try: intent = account_ledger.confirm(id,request.token)
        except ValueError as exc: raise HTTPException(409, detail=str(exc))
        action_reader().submit_account_action(account_ledger, intent, 'execute')
        return account_ledger.get(id)

    @app.post('/api/learning/account-actions/{id}/verify')
    def verify_account_action(id: str):
        try: intent = account_ledger.verify(id)
        except ValueError as exc: raise HTTPException(409, detail=str(exc))
        action_reader().submit_account_action(account_ledger, intent, 'verify')
        return account_ledger.get(id)

    @app.post('/api/learning/actions')
    def action(request: ActionRequest):
        if request.source != 'demo':
            raise HTTPException(409, detail={'status': 'pending_integration', 'message': '真实关注和私信尚未接入；不会发送或点击关注。'})
        if request.kind == 'message' and not request.message.strip():
            raise HTTPException(422, detail='模拟消息不能为空。')
        return store.simulate_action(request.user_id, request.kind, request.message)

    @app.post('/api/learning/import')
    def import_data(request: ImportRequest):
        try:
            data = import_records(request.records)
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
        task = store.create_task('导入 MediaCrawler JSON', 'import')
        return store.finish(task['id'], data, 'success', '导入完成；来源为本地文件，未经实时网页验证。')

    @app.get('/api/learning/export/{task_id}')
    def export(task_id: str):
        data = json.dumps(store.result(task_id), ensure_ascii=False, indent=2)
        return Response(data, media_type='application/json', headers={
            'Content-Disposition': f'attachment; filename="task-{task_id}.json"'})

    @app.get('/license')
    def license_text():
        return FileResponse(ROOT / 'LICENSE', media_type='text/plain')

    static = ROOT / 'api' / 'webui'
    if (static / 'assets').exists():
        app.mount('/assets', StaticFiles(directory=static / 'assets'), name='assets')
    if (static / 'logos').exists():
        app.mount('/logos', StaticFiles(directory=static / 'logos'), name='logos')

    @app.get('/')
    def index():
        if not (static / 'index.html').exists():
            raise HTTPException(503, detail='请先在 webui 目录运行 npm run build。')
        return FileResponse(static / 'index.html')

    return app
