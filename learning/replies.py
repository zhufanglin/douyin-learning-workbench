"""Read one public discussion thread using its visible expand controls only."""
import json
import time
from pathlib import Path
from . import REPLY_READER_VERSION
from .images import IMAGE_SCAN_JS, image_fields, image_identity, placeholder_count

from .browser import PagePaused, check_page, current_video_id, dom_comment_id, read_comments, scroll_comments, valid_path


def discussion_scope(row):
    levels = row.evaluate('''row => {
        let e=row, levels=0;
        while(e.parentElement && levels<6 && !e.parentElement.matches('[data-e2e="comment-list"]') &&
              [...e.parentElement.querySelectorAll('[data-e2e="comment-item"]')].filter(n=>!n.closest('.replyContainer')).length===1) {e=e.parentElement;levels++;}
        return levels;
    }''')
    for _ in range(levels):
        row = row.locator('..')
    return row


def thread_view(scope, selectors):
    return scope.evaluate('''(scope,s) => {
        const scanImages = ''' + IMAGE_SCAN_JS + ''';
        const visible=e=>e && e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
        const main=scope.matches('[data-e2e="comment-item"]') ? scope : [...scope.querySelectorAll('[data-e2e="comment-item"]')].find(n=>!n.closest('.replyContainer'));
        const mainContent=main?.querySelector(s.comment_text);
        const contents=[...scope.querySelectorAll(s.reply_text || s.comment_text)].filter(visible);
        const parsedRows=new Set();
        const replies=contents.filter(e=>e!==mainContent && !mainContent?.contains(e)).map(content=>{
            let e=content.parentElement;
            while(e && e!==scope) {
                if(e.querySelectorAll(s.reply_text || s.comment_text).length>1) return null;
                const author=[...e.querySelectorAll(s.comment_user)].find(a=>visible(a)&&a.innerText.trim()&&!content.contains(a));
                if(author) {parsedRows.add(content.closest('[data-e2e="comment-item"]'));
                    const text=content.innerText.trim();
                    const images=[...content.querySelectorAll('img')].filter(visible);
                    const labels=images.map(img=>img.alt?.trim()||'');
                    const emoji=!text && labels.length>0 && labels.every(label=>/^\\[[^\\[\\]\\r\\n]{1,40}\\]$/.test(label));
                    return {href:author.href,nickname:author.innerText.trim(),text:emoji?labels.join(''):text,
                        content_type:emoji?'emoji':'text',emoji_labels:emoji?labels:[],
                        ...scanImages(content.closest('[data-e2e="comment-item"]') || e, content)};}
                e=e.parentElement;
            }
            return null;
        }).filter(Boolean);
        const controls=[...scope.querySelectorAll('*')].map((e,index)=>({e,index})).filter(({e})=>
            visible(e) && !e.children.length && e.closest('button') && !e.closest('a') && !e.closest(s.comment_text) && !e.closest(s.reply_text || s.comment_text) &&
            /^(展开\\s*(?:更多\\s*)?(?:[0-9]+\\s*条\\s*)?回复|展开\\s*更多|查看更多回复|收起(?:回复)?)$/.test(e.innerText?.trim() || ''))
            .map(({e,index})=>({index,text:e.innerText.trim(),collapse:e.innerText.trim().startsWith('收起')}));
        const replyRows=[...scope.querySelectorAll('.replyContainer [data-e2e="comment-item"]')].filter(visible);
        for(const row of replyRows.filter(row=>!parsedRows.has(row))) {
            const images=scanImages(row,null);
            const author=[...row.querySelectorAll(s.comment_user)].find(a=>visible(a)&&a.innerText.trim());
            if(images.image_keys.length && author) {
                parsedRows.add(row);
                replies.push({href:author.href,nickname:author.innerText.trim(),text:'',content_type:'image_placeholder',...images});
            }
        }
        const unparsed_count=replyRows.filter(row=>!parsedRows.has(row)).length;
        const loading=[...scope.querySelectorAll('*')].some(e=>visible(e)&&!e.children.length&&
            !e.closest('[data-e2e="comment-item"]')&&/^(加载中[.。…]*|正在加载[.。…]*)$/.test(e.innerText?.trim()||''));
        return {replies,controls,loading,unparsed_count};
    }''', selectors)


def reply_id(video_id, user_id, raw, parent_id):
    # Preserve existing text IDs; distinguish literal bracket text from actual emoji images.
    identity = image_identity(raw) if raw.get('content_type') != 'emoji' else '\x00emoji:' + raw['text']
    return dom_comment_id(video_id, user_id, identity, parent_id)


def collect_replies(page, video_id, data, progress, cancelled):
    paging = data['pagination']
    parent_id = paging['active_reply']
    state = paging['replies'][parent_id]
    parent = next(c for c in data['comments'] if c['id'] == parent_id)
    if parent.get('video_id') != video_id:
        raise PagePaused('needs_review', '回复所属视频不匹配，已暂停。')
    selectors = json.loads(Path(__file__).with_name('selectors.json').read_text(encoding='utf8'))
    found = {c['id']: c for c in data['comments'] if c.get('parent_comment_id') == parent_id}
    other = [c for c in data['comments'] if c.get('parent_comment_id') != parent_id]
    users = {u['id']: u for u in data['users']}
    deadline, previous, stale = time.monotonic() + 150, None, 0
    clicked = set()
    expected = None
    state.update(end_state='reading', page_end=False, reader_version=REPLY_READER_VERSION)
    while time.monotonic() < deadline:
        if cancelled(): return
        check_page(page)
        if current_video_id(page.url) != video_id:
            raise PagePaused('needs_review', '视频发生变化，已停止读取回复。')
        main = read_comments(page, video_id, allow_empty=True, include_positions=True)['comments']
        match = next((c for c in main if c['id'] == parent_id), None)
        if not match:
            window = tuple(c['id'] for c in main)
            stale = stale + 1 if window == previous else 0
            previous = window
            if stale >= 6:
                state['end_state'] = 'blocked'
                raise PagePaused('partial', '页面尚未找到所选主评论，已暂停；保留原有评论，不会读取其他讨论的回复。')
            scroll_comments(page)
            page.wait_for_timeout(1500)
            continue
        row = page.locator('[data-e2e="comment-item"]').nth(match['_row_index'])
        row.scroll_into_view_if_needed(timeout=3000)
        scope = discussion_scope(row)
        view = thread_view(scope, selectors)
        readable = [r for r in view['replies'] if valid_path(r['href'], 'user') and image_identity(r)]
        unsupported = view['unparsed_count'] + len(view['replies']) - len(readable)
        observed = view['unparsed_count'] + len(view['replies'])
        state.update(unsupported_count=unsupported, observed_count=observed)
        before = len(found)
        for raw in readable:
            user_id = valid_path(raw['href'], 'user')
            if not user_id: continue
            rid = reply_id(video_id, user_id, raw, parent_id)
            if rid not in found and len(found) < state['target']:
                found[rid] = dict(id=rid, video_id=video_id, user_id=user_id, content=raw['text'][:2000] or '图片内容未读取',
                    kind='reply', parent_comment_id=parent_id, reply_rank=len(found) + 1, **image_fields(raw))
                if not raw['text']:
                    found[rid]['content_type'] = 'image_placeholder'
                if raw.get('content_type') == 'emoji':
                    found[rid].update(content_type='emoji', emoji_labels=raw['emoji_labels'])
                users[user_id] = dict(id=user_id, nickname=raw['nickname'][:200], profile_url=f'https://www.douyin.com/user/{user_id}')
            elif rid in found and raw.get('image_count'):
                found[rid].update(image_fields(raw))
        data.update(comments=other + list(found.values()), users=list(users.values()))
        state['image_placeholder_count'] = placeholder_count(found.values())
        if len(found) > before: progress()
        expand = next((c for c in view['controls'] if not c['collapse']), None)
        collapsed = any(c['collapse'] for c in view['controls'])
        signature = (len(found), tuple(c['text'] for c in view['controls']), observed, unsupported, view['loading'])
        stale = stale + 1 if signature == previous else 0
        previous = signature
        if not expand and collapsed and observed and not view['loading'] and stale >= 1:
            if expected is None or observed >= expected:
                all_saved = all(reply_id(video_id, valid_path(r['href'], 'user'), r, parent_id) in found for r in readable)
                if all_saved:
                    state['page_end'] = True
                    if unsupported or state['image_placeholder_count']:
                        state.update(end_state='unsupported', exhausted=False)
                        raise PagePaused('partial', f"已到回复页尾，保存 {len(found)} 条回复记录，其中 {state['image_placeholder_count']} 条图片内容未读取；另有 {unsupported} 条未识别内容未保存。已停止继续读取，不代表所有内容均已保存。")
                    state['end_state'] = 'complete'
                    state['exhausted'] = True
                    return
        if len(found) >= state['target']:
            state['end_state'] = 'batch_complete'
            return
        if stale >= 6:
            state['end_state'] = 'blocked'
            # Persist a local DOM diagnostic for selector adaptation; never export it with records.
            raise PagePaused('partial', f'回复加载受阻或结束状态未确认，已保存 {len(found)} 条回复；请核对页面后再继续，未自动重试。')
        if expand:
            import re
            number = re.fullmatch(r'展开\s*(\d+)\s*条\s*回复', expand['text'])
            if number and not view['replies']:
                expected = int(number.group(1))
            token = (expand['text'], len(view['replies']))
            if token not in clicked:
                check_page(page)
                if current_video_id(page.url) != video_id:
                    raise PagePaused('needs_review', '视频发生变化，已暂停。')
                control = scope.locator('*').nth(expand['index'])
                if control.inner_text().strip() != expand['text']:
                    raise PagePaused('partial', '回复入口发生变化，请核对后继续。')
                control.click(timeout=3000)
                clicked.add(token)
        page.wait_for_timeout(1500)
    state['end_state'] = 'blocked'
    raise PagePaused('partial', f'本批回复读取达到时间上限，已保存 {len(found)} 条；可核对后继续。')
