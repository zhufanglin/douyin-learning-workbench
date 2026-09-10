"""Ordinary Playwright worker for visible-page reading and explicitly authorized actions."""
import hashlib
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from playwright.sync_api import sync_playwright, TimeoutError as BrowserTimeout
from .images import IMAGE_SCAN_JS, image_fields, image_identity, placeholder_count


class PagePaused(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def save_diagnostic(page, store, task_id):
    """Save this task's own browser view locally; never capture other applications."""
    folder = store.path.parent / 'diagnostics'
    folder.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(page.url)
    info = {'url': f'{parsed.scheme}://{parsed.netloc}{parsed.path}'}
    for key, read in [('title', page.title), ('visible_text', lambda: page.locator('body').inner_text(timeout=3000)[:3000])]:
        try:
            info[key] = read()
        except Exception as exc:
            info[key + '_error'] = type(exc).__name__
    try:
        info['video_id'] = current_video_id(page.url)
        config = json.loads(Path(__file__).with_name('selectors.json').read_text(encoding='utf-8'))
        info['card_nodes'] = page.locator(config.get('diagnostic_nodes', 'li, [data-index], [data-id], [data-aweme-id]')).evaluate_all('''els => els
            .filter(e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden')
            .slice(0, 100).map(e => ({tag: e.tagName, attrs: [...e.attributes].filter(a => /^(id|class|data-)/.test(a.name)).map(a => [a.name,a.value]),
                text: e.innerText.slice(0, 180)}))''')
        info['visible_links'] = page.locator('a[href]').evaluate_all('''els => els
            .filter(e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden')
            .slice(0, 150).map(e => {const u = new URL(e.href); return {path: u.origin + u.pathname,
                modal_id: u.searchParams.get('modal_id'), text: e.innerText.slice(0, 100), class: e.className}})''')
        info['dom_markers'] = page.locator('[data-e2e]').evaluate_all('''els => [...new Set(els
            .filter(e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden')
            .map(e => e.getAttribute('data-e2e')))].slice(0, 100)''')
        info['reply_structure'] = page.locator('[data-e2e="comment-list"]').evaluate_all('''els=>els.flatMap(root=>[...root.querySelectorAll('*')]
            .filter(e=>!e.children.length && e.getClientRects().length && /^(展开.*回复|收起(?:回复)?)$/.test(e.innerText?.trim()||''))
            .slice(0,3).map(e=>{let parent=e;for(let i=0;i<6 && parent.parentElement;i++){
                if(parent.querySelector('[data-e2e="comment-item"]'))break;parent=parent.parentElement;}
                return {text:e.innerText, html:parent.outerHTML.slice(0,26000)}}))''')
        info['comment_structure'] = page.locator('[data-e2e="comment-item"]').first.evaluate('''e => [e, ...e.querySelectorAll('*')]
            .slice(0, 100).map(n => ({tag: n.tagName, marker: n.getAttribute('data-e2e'),
                class: n.getAttribute('class'), parent: n.parentElement?.getAttribute('class'),
                text: [...n.childNodes].filter(c => c.nodeType === 3).map(c => c.textContent).join('').trim().slice(0, 300),
                rendered: n.tagName === 'svg' || n.tagName === 'path' ? '' : (n.innerText || '').slice(0, 300)}))''', timeout=3000) if page.locator('[data-e2e="comment-item"]').count() else []
    except Exception as exc:
        info['structure_error'] = type(exc).__name__
    diagnostic = folder / f'{task_id}.json'
    diagnostic.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        page.screenshot(path=str(folder / f'{task_id}.png'), timeout=5000)
    except Exception as exc:
        info['screenshot_error'] = type(exc).__name__
        diagnostic.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
        store.log(task_id, 'warning', f'截图未完成（{type(exc).__name__}）；页面文字诊断已保存在本机。')


def check_page(page):
    preview=getattr(page,'_learning_preview_capture',None)
    if preview: preview()
    text = page.locator('body').inner_text(timeout=15000)
    if any(word in text for word in ('安全验证', '请完成下方验证', '拖动滑块', '访问过于频繁', '操作过于频繁')):
        raise PagePaused('waiting_verification', '页面要求验证或限制访问，已暂停。请本人检查浏览器；不会自动重试。')
    for dialog in page.locator('[role="dialog"], [data-e2e="login-dialog"]').all():
        if dialog.is_visible() and '登录' in dialog.inner_text():
            raise PagePaused('waiting_login', '请本人在弹出的浏览器完成登录，再回到这里新建读取任务。')
    if any(word in text for word in ('扫码登录后', '登录后即可查看', '登录后查看完整', '请登录后查看')):
        raise PagePaused('waiting_login', '页面需要登录，已暂停，等待本人操作。')


def valid_path(href, kind):
    url = urlparse(href)
    if url.scheme != 'https' or url.hostname not in ('www.douyin.com', 'douyin.com'):
        return None
    pattern = r'/video/(\d+)' if kind == 'video' else r'/user/([A-Za-z0-9_.=-]+)'
    match = re.fullmatch(pattern, url.path.rstrip('/'))
    return match.group(1) if match else None


def current_video_id(href):
    # MediaCrawler media_platform/douyin/help.py also supports modal_id.
    # Keep this URL-only adapter independent of that module's signing imports.
    parsed = urlparse(href)
    if parsed.scheme != 'https' or parsed.hostname not in ('www.douyin.com', 'douyin.com'):
        return None
    ids = parse_qs(parsed.query, keep_blank_values=True).get('modal_id')
    if ids is not None:
        return ids[0] if len(ids) == 1 and re.fullmatch(r'[0-9]+', ids[0]) else None
    return valid_path(href, 'video')


def read_search(page, limit=100, allow_empty=False):
    check_page(page)
    selectors = json.loads(Path(__file__).with_name('selectors.json').read_text(encoding='utf-8'))
    links = page.locator('a[href*="/video/"], a[href*="modal_id="]').evaluate_all('''els => els
        .filter(e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden')
        .map(e => ({url: e.href, title: e.innerText || e.getAttribute('aria-label') || ''}))''')
    cards = []
    if selectors.get('search_card'):
        cards = page.locator(selectors['search_card']).evaluate_all('''(els, attr) => els
            .filter(e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden')
            .map(e => ({id: attr ? e.getAttribute(attr) : null, title: e.innerText}))''', selectors.get('search_id_attribute'))
    found = {}
    # When cards are present, global links can belong to related searches or photo posts.
    for link in ([] if cards else links):
        video_id = current_video_id(link['url'])
        if video_id and video_id not in found:
            found[video_id] = dict(id=video_id, title=link['title'].strip()[:1000] or '页面未展示标题',
                                   url=f'https://www.douyin.com/video/{video_id}', author='')
    for card in cards:
        title = card['title'].strip()
        if not title:
            continue
        match = re.fullmatch(r'(?:waterfall_item_)?([0-9]+)', card['id'] or '')
        if not match:
            continue
        actual_id = match.group(1)
        lines = title.splitlines()
        if not re.fullmatch(r'(?:[0-9]{1,2}:)?[0-9]{1,3}:[0-9]{2}', lines[0].strip()):
            continue
        duration = lines[0].strip()
        author = next((line for line in lines if line.startswith('@')), '')
        if len(lines) > 3 and re.fullmatch(r'[0-9:]+', lines[0]) and author:
            title = '\n'.join(lines[2:lines.index(author)])
        found.setdefault(actual_id, dict(id=actual_id, title=title[:1000],
            url=f'https://www.douyin.com/video/{actual_id}', author=author, content_type='video', duration=duration))
    if not found and not allow_empty:
        raise PagePaused('pending_layout', '未识别到可见视频链接，可能尚未加载、需要登录或页面结构已变化；未判定为零结果成功。')
    return list(found.values())[:limit]


def collect_search(page, data, limit, progress, cancelled, *, idle_timeout=30, timeout=150, poll_ms=2000):
    """Distinguish a visible end marker from slow loading; keep every saved result."""
    from .search_flow import search_page_state, scroll_search
    found = {v['id']: v for v in data['videos']}
    started = last_new = time.monotonic()
    end_observations = 0
    last_report = -10
    while True:
        if cancelled(): return
        check_page(page)
        before = len(found)
        for video in read_search(page, limit=100, allow_empty=True):
            if video['id'] not in found:
                found[video['id']] = dict(video, search_rank=len(found) + 1)
            if len(found) >= limit: break
        data['videos'] = list(found.values())[:limit]
        now = time.monotonic()
        if len(found) > before:
            last_new = now
            data['search_note'] = f'已收集 {len(found)}/{limit} 个视频，正在读取视频分类结果…'
            progress()
            last_report = now
        if len(found) >= limit: return
        check_page(page)
        state = search_page_state(page)
        end_observations = end_observations + 1 if state['ended'] and not state['loading'] else 0
        if end_observations >= 2:
            raise PagePaused('search_exhausted', f'已收集 {len(found)}/{limit} 个视频；当前视频搜索页明确提示没有更多结果，已读到页尾。100 是上限，无需反复读取同一页。')
        idle = now - last_new
        if now - started >= timeout:
            raise PagePaused('search_stalled', f'已收集 {len(found)}/{limit} 个视频；本次读取达到时间上限，结果已保存，未确认页面到底。可检查页面后继续读取。')
        if idle >= idle_timeout and not end_observations:
            raise PagePaused('search_stalled' if found else 'pending_layout', f'已收集 {len(found)}/{limit} 个视频；连续 {int(idle_timeout)} 秒没有新增可识别视频，结果已保存，未确认页面到底。请检查加载状态，必要时继续读取当前搜索页。')
        if now - last_report >= 4:
            data['search_note'] = f'已收集 {len(found)}/{limit} 个视频；'+ ('页面正在加载，' if state['loading'] else '正在滚动并等待更多结果，') + f'已等待 {int(idle)} 秒。'
            progress()
            last_report = now
        scroll_search(page)
        # Remain responsive to cancellation during each loading wait.
        for remaining in range(poll_ms, 0, -500):
            if cancelled(): return
            page.wait_for_timeout(min(500, remaining))


def dom_comment_id(video_id, user_id, text, parent_id=None):
    identity = f'{video_id}|{user_id}|{text}' if parent_id is None else f'{video_id}|{parent_id}|{user_id}|{text}'
    return ('dom-' if parent_id is None else 'dom-reply-') + hashlib.sha256(identity.encode()).hexdigest()[:24]


def read_comments(page, video_id, allow_empty=False, include_positions=False):
    check_page(page)
    selectors = json.loads(Path(__file__).with_name('selectors.json').read_text(encoding='utf-8'))
    rows = page.locator('[data-e2e="comment-item"]').evaluate_all('''(rows, selectors) => {
        const scanImages = ''' + IMAGE_SCAN_JS + ''';
        const visible = e => e && e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden';
        return rows.map((row, index) => {
            if (!visible(row) || row.closest('.replyContainer')) return null;
            const anchors = [...row.querySelectorAll(selectors.comment_user)].filter(visible);
            const anchor = anchors.find(a => a.innerText.trim()) || anchors[0];
            const content = row.querySelector(selectors.comment_text);
            const images=scanImages(row, content);
            return anchor && (visible(content) || images.image_count) ? {index, href: anchor.href, nickname: anchor.innerText.trim(), text: visible(content)?content.innerText.trim():'', ...images} : null;
        }).filter(Boolean);
    }''', selectors)
    comments, users = {}, {}
    for row in rows:
        user_id = valid_path(row['href'], 'user')
        text = row['text']
        identity = image_identity(row)
        if not user_id or not identity:
            continue
        # Visible DOM has no guaranteed platform comment ID; label derived IDs explicitly.
        comment_id = dom_comment_id(video_id, user_id, identity)
        comments[comment_id] = dict(id=comment_id, video_id=video_id, user_id=user_id, content=text[:2000] or '图片内容未读取', kind='comment', **image_fields(row))
        if not text:
            comments[comment_id]['content_type'] = 'image_placeholder'
        if include_positions:
            comments[comment_id]['_row_index'] = row['index']
        users[user_id] = dict(id=user_id, nickname=row['nickname'][:200] or '未展示昵称',
                              profile_url=f'https://www.douyin.com/user/{user_id}')
    if not comments and not allow_empty:
        raise PagePaused('pending_layout', '视频已读取，但未识别到可见评论；请本人展开评论后使用“读取当前视频评论”。')
    return dict(comments=list(comments.values()), users=list(users.values()),
                unidentified_image_count=sum(bool(row.get('image_count')) and (not image_identity(row) or not valid_path(row['href'], 'user')) for row in rows))


def comments_ended(page):
    # Only explicit footer text within the comment list; never a comment saying "没有更多了".
    config = json.loads(Path(__file__).with_name('selectors.json').read_text(encoding='utf8'))
    endings = config.get('comment_end_texts', ['没有更多评论了', '暂无更多评论', '没有更多了', '暂时没有更多了', '暂时没有评论', '暂时没有更多评论'])
    return page.locator('[data-e2e="comment-list"]').evaluate_all('''(lists,endings) => lists.some(list =>
        [...list.querySelectorAll('*')].some(e => !e.closest('[data-e2e="comment-item"]') &&
            e.children.length === 0 && e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden' &&
            endings.includes(e.innerText?.trim())))''', endings)


def scroll_comments(page):
    rows = page.locator('[data-e2e="comment-item"]')
    index = rows.evaluate_all('''els => els.map((e,i) => e.getClientRects().length &&
        getComputedStyle(e).visibility !== 'hidden' ? i : -1).filter(i => i >= 0).pop() ?? null''')
    if index is not None:
        last = rows.nth(index)
        last.scroll_into_view_if_needed(timeout=3000)
        box = last.bounding_box()
        if box:
            page.mouse.move(box['x'] + box['width'] / 2, box['y'] + min(box['height'] / 2, 100))
            page.mouse.wheel(0, 650)


def collect_comments(page, video_id, data, progress, cancelled):
    replies = [c for c in data['comments'] if c.get('parent_comment_id')]
    found = {c['id']: c for c in data['comments'] if not c.get('parent_comment_id')}
    users = {u['id']: u for u in data['users']}
    paging = data['pagination']
    deadline, stale, previous_window = time.monotonic() + 150, 0, None
    while True:
        if cancelled():
            return
        check_page(page)
        if current_video_id(page.url) != video_id:
            raise PagePaused('needs_review', '当前视频发生变化，已暂停；不会把其他视频评论混入本任务。')
        before = len(found)
        batch = read_comments(page, video_id, allow_empty=True)
        window = tuple(c['id'] for c in batch['comments'])
        for comment in batch['comments']:
            if len(found) >= paging['target']:
                break
            if comment['id'] not in found:
                found[comment['id']] = dict(comment, comment_rank=len(found) + 1)
            elif comment.get('content_status') == 'image_not_read':
                found[comment['id']].update({key: comment[key] for key in ('content_status', 'image_count', 'image_fingerprints')})
        wanted = {c['user_id'] for c in found.values()}
        users.update({u['id']: u for u in batch['users'] if u['id'] in wanted})
        data.update(comments=list(found.values()) + replies, users=list(users.values()))
        paging['image_placeholder_count'] = placeholder_count(found.values())
        paging['unidentified_image_count'] = batch.get('unidentified_image_count', 0)
        if len(found) > before:
            progress()
            stale = 0
        else:
            stale = stale + 1 if window == previous_window else 0
        previous_window = window
        # If the DOM already has extra rows, the footer is beyond this batch.
        if comments_ended(page) and all(c['id'] in found for c in batch['comments']):
            paging['exhausted'] = True
            if paging['image_placeholder_count'] or paging['unidentified_image_count']:
                raise PagePaused('partial', f"主评论已到页尾，已保存 {len(found)} 条记录；其中 {paging['image_placeholder_count']} 条图片内容未读取，另有 {paging['unidentified_image_count']} 条图片缺少可用标识或作者，无法保存。")
            return
        if len(found) >= paging['target']:
            return
        if time.monotonic() >= deadline or stale >= (15 if not found else 6):
            raise PagePaused('partial' if found else 'pending_layout',
                f'累计保存 {len(found)} 条主评论，页面暂未加载更多可识别内容；尚未确认到底。可点击继续读取，未自动重试。')
        scroll_comments(page)
        page.wait_for_timeout(2000)


class BrowserReader:
    def __init__(self, profile):
        self.profile = profile
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='visible-browser')
        self.lock = threading.Lock()
        self.busy = False
        self.playwright = None
        self.context = None
        self.page = None
        from .preview import BrowserPreview
        self.preview = BrowserPreview()
        self._preview_pending = False
        self._closing = False

    def preview_snapshot(self, focus=False):
        self.preview.request(focus=focus)
        with self.lock:
            busy=self.busy
            schedule=not busy and not self._preview_pending and not self._closing
            if schedule: self._preview_pending=True
        if schedule:
            def refresh():
                try: self.preview.capture(self.page)
                finally:
                    with self.lock: self._preview_pending=False
            try: self.pool.submit(refresh)
            except RuntimeError:
                with self.lock: self._preview_pending=False
                self.preview.clear()
        return dict(self.preview.snapshot(),busy=busy)

    def submit(self, store, task, current=False, direct_url=None, limit=100, search_current=False):
        with self.lock:
            if self.busy:
                store.finish(task['id'], {}, 'blocked', '另一个网页读取任务正在执行，请稍后再试。')
                return
            self.busy = True
        self.pool.submit(self._run, store, task, current, direct_url, limit, search_current)

    def submit_downloads(self, manager, identity):
        with self.lock:
            if self.busy:
                manager.finish(identity,'blocked','浏览器正被其他任务使用，请结束后重新选择下载。')
                return
            self.busy = True
        def work():
            try:
                self._ensure_browser()
                from .downloads import run_downloads
                run_downloads(self.page,manager,identity)
            except Exception as exc:
                manager.finish(identity,'failed','浏览器下载中断（'+type(exc).__name__+'）；未自动重试。')
            finally:
                with self.lock: self.busy = False
        self.pool.submit(work)

    def inspect_account_browser(self):
        with self.lock:
            if self.busy: raise ValueError('浏览器正被任务使用，请结束后再核对账号。')
            self.busy = True
        def work():
            try:
                self._ensure_browser()
                if self.page.url == 'about:blank':
                    self.page.goto('https://www.douyin.com/',wait_until='domcontentloaded',timeout=30000)
                from .account_browser import inspect_session
                return inspect_session(self.page)
            finally:
                with self.lock: self.busy = False
        return self.pool.submit(work).result(timeout=40)

    def open_account_browser(self):
        with self.lock:
            if self.busy: raise ValueError('浏览器正被任务使用，请等待任务结束。')
            self.busy = True
        def work():
            try:
                self._ensure_browser()
                self.page.goto('https://www.douyin.com/',wait_until='domcontentloaded',timeout=30000)
                return {'note':'已打开独立抖音浏览器，请本人完成登录，再复制本人主页和测试对象主页链接。'}
            finally:
                with self.lock: self.busy = False
        return self.pool.submit(work).result(timeout=40)

    def submit_account_action(self, ledger, action, phase):
        with self.lock:
            if self.busy:
                ledger.mark(action['id'], 'uncertain' if phase=='verify' else 'blocked', '浏览器正被其他任务使用；本次未点击关注或发送。')
                return
            self.busy = True
        def work():
            try:
                self._ensure_browser()
                from .account_browser import run_action
                run_action(self.page, ledger, action, phase)
            except Exception as exc:
                ledger.mark(action['id'], 'uncertain' if phase=='verify' else 'blocked', '浏览器不可用（'+type(exc).__name__+'）；本次未执行。')
            finally:
                with self.lock: self.busy = False
        self.pool.submit(work)

    def _ensure_browser(self):
        if self.playwright is None:
            self.playwright = sync_playwright().start()
        if self.page is None or self.page.is_closed():
            if self.context:
                try:
                    self.context.close()
                except Exception:
                    pass
            self.context = self.playwright.chromium.launch_persistent_context(
                str(self.profile), headless=False, channel='chromium', viewport={'width': 1280, 'height': 900})
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            self.page.set_default_timeout(5000)
        self.page._learning_preview_capture = lambda: self.preview.capture(self.page)
        self.preview.capture(self.page)

    def _run(self, store, task, current, direct_url=None, limit=100, search_current=False):
        previous = store.result(task['id'])
        data = {kind: previous[kind] for kind in ('videos', 'comments', 'users')}
        if previous.get('pagination'):
            data['pagination'] = previous['pagination']
        try:
            if store.get_task(task['id'])['status'] != 'running':
                return
            self._ensure_browser()
            if direct_url and (not data.get('pagination') or current_video_id(self.page.url) != current_video_id(direct_url)):
                self.page.goto(direct_url, wait_until='domcontentloaded', timeout=30000)
            if current or direct_url:
                check_page(self.page)
                video_id = current_video_id(self.page.url)
                if not video_id:
                    raise PagePaused('pending_layout', '请先在此工具打开的浏览器进入视频详情页，再读取当前视频评论。')
                if direct_url and video_id != current_video_id(direct_url):
                    raise PagePaused('needs_review', '页面未打开所选视频，已暂停。')
                data.setdefault('pagination', dict(video_id=video_id, revision=0, target=100, exhausted=False, scope='top_level_text'))
                data['videos'] = [dict(id=video_id, title=self.page.title()[:1000], url=f'https://www.douyin.com/video/{video_id}', author='')]
                if direct_url:
                    for _ in range(30):
                        check_page(self.page)
                        selectors = json.loads(Path(__file__).with_name('selectors.json').read_text(encoding='utf-8'))
                        if self.page.locator('[data-e2e="comment-item"]').locator(selectors['comment_text']).count():
                            break
                        self.page.wait_for_timeout(1000)
                store.finish(task['id'], data, 'running', '正在读取首批或继续本批主评论，每页 100 条。')
                if data['pagination'].get('active_reply'):
                    from .replies import collect_replies
                    parent_id = data['pagination']['active_reply']
                    store.finish(task['id'], data, 'running', '正在定位主评论并展开其回复；不会点击发送回复按钮。')
                    collect_replies(self.page, video_id, data,
                        lambda: store.finish(task['id'], data, 'running', f"此讨论已保存 {sum(c.get('parent_comment_id') == parent_id for c in data['comments'])} 条回复，正在读取…"),
                        lambda: store.get_task(task['id'])['status'] != 'running')
                    count = sum(c.get('parent_comment_id') == parent_id for c in data['comments'])
                    done = data['pagination']['replies'][parent_id]['exhausted']
                    images = data['pagination']['replies'][parent_id].get('image_placeholder_count', 0)
                    image_note = f'其中 {images} 条含图片，仅记录标识，图片内容未读取。' if images else ''
                    store.finish(task['id'], data, 'success', f"已保存此讨论 {count} 条回复；" + ('页面已无更多展开入口，已读完当前可识别回复。' if done else '本批完成，可继续读取回复。') + image_note)
                    return
                collect_comments(self.page, video_id, data,
                    lambda: store.finish(task['id'], data, 'running', f"累计 {sum(not c.get('parent_comment_id') for c in data['comments'])}/{data['pagination']['target']} 条主评论，正在加载…"),
                    lambda: store.get_task(task['id'])['status'] != 'running')
            else:
                search_url = 'https://www.douyin.com/search/' + quote(task['keyword'], safe='')
                if search_current:
                    if self.page.url.split('?')[0].rstrip('/') != search_url:
                        raise PagePaused('pending_layout', '当前浏览器不在这个关键词的搜索页，请先回到对应搜索页。')
                else:
                    self.page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
                from .search_flow import ensure_video_search
                store.finish(task['id'], data, 'running', '正在切换到视频分类，随后读取搜索结果…')
                if not ensure_video_search(self.page, lambda: store.get_task(task['id'])['status'] != 'running'):
                    return
                collect_search(self.page, data, limit,
                    lambda: store.finish(task['id'], data, 'running', data.get('search_note', '正在读取视频分类…')),
                    lambda: store.get_task(task['id'])['status'] != 'running')
                store.finish(task['id'], data, 'success', f"已收集 {len(data['videos'])} 个视频，请点击列表中的视频查看评论。")
                return
            ending = '页面明确提示主评论已到底。' if data['pagination']['exhausted'] else '本批读取完成，可点击下一批 100 条。'
            images = data['pagination'].get('image_placeholder_count', 0)
            if images:
                ending += f'其中 {images} 条含图片，仅记录标识，图片内容未读取。'
            store.finish(task['id'], data, 'success', f"累计保存 {sum(not c.get('parent_comment_id') for c in data['comments'])} 条主评论；{ending}可在各主评论下单独读取回复。")
        except PagePaused as exc:
            self._mark_reply_blocked(data)
            store.finish(task['id'], data, exc.status, str(exc))
        except BrowserTimeout:
            self._mark_reply_blocked(data)
            store.finish(task['id'], data, 'failed', '页面加载超时，已停止；未自动重试。请检查网络和浏览器。')
        except Exception as exc:
            self._mark_reply_blocked(data)
            # Never include raw browser errors, cookies, or page contents in persistent logs.
            store.finish(task['id'], data, 'failed', f'浏览器读取失败（{type(exc).__name__}），请检查浏览器是否关闭或完成安装。')
        finally:
            try:
                if self.page and not self.page.is_closed() and (store.get_task(task['id'])['status'] not in ('success', 'cancelled') or data.get('pagination', {}).get('active_reply')):
                    save_diagnostic(self.page, store, task['id'])
            except Exception:
                store.log(task['id'], 'warning', '未能保存页面诊断截图；原任务状态保持不变。')
            with self.lock:
                self.busy = False

    @staticmethod
    def _mark_reply_blocked(data):
        paging = data.get('pagination', {})
        state = paging.get('replies', {}).get(paging.get('active_reply'))
        if state is not None and state.get('end_state') not in ('complete', 'unsupported', 'batch_complete'):
            state.update(end_state='blocked', page_end=False)

    def _close(self):
        if self.context:
            try:
                self.context.close()
            except Exception:
                pass
        if self.playwright:
            self.playwright.stop()

    def close(self):
        self._closing=True
        self.preview.clear()
        self.pool.submit(self._close)
        self.pool.shutdown(wait=False, cancel_futures=False)
