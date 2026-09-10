"""Conservative visible-page adapter. Unrecognized layouts stop before a send.
Selectors are fixture-tested; live Douyin compatibility must be verified per login.
"""
import re
import json
from urllib.parse import urljoin, urlparse
from .browser import PagePaused, check_page


def profile_url(value):
    parsed=urlparse(value.strip())
    if parsed.scheme!='https' or parsed.hostname not in ('www.douyin.com','douyin.com') or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('请输入完整的 https://www.douyin.com/user/ 用户主页链接。')
    if not re.fullmatch(r'/user/[A-Za-z0-9_.=-]+/?',parsed.path):
        raise ValueError('需要用户主页链接，不能使用视频或搜索链接。')
    return 'https://www.douyin.com'+parsed.path.rstrip('/')


def unique(locator, explanation):
    found=[item for item in locator.all() if item.is_visible()]
    if len(found)!=1: raise PagePaused('blocked',explanation)
    return found[0]


def sender_identity(value):
    value=value.strip()
    if re.fullmatch(r'@[A-Za-z0-9_.-]{1,100}',value): return value
    url=profile_url(value)
    if url.rsplit('/',1)[-1] in ('self','me'): raise ValueError('self 不是唯一账号，请点击读取本人账号，或填写 @抖音号。')
    return url


def own_profiles(page, include_alias=False):
    own=set()
    navigation=page.locator('nav, [role="navigation"], [data-e2e="douyin-navigation"], #douyin-navigation')
    for link in navigation.get_by_role('link',name=re.compile(r'^(我|我的|我的主页)$')).all():
        if not link.is_visible(): continue
        try:
            url=profile_url(urljoin(page.url,link.get_attribute('href') or ''))
            if include_alias or url.rsplit('/',1)[-1] not in ('self','me'): own.add(url)
        except ValueError: pass
    return own


def current_actor(page):
    links=own_profiles(page,include_alias=True)
    if len(links)!=1: return ''
    url=next(iter(links))
    if url.rsplit('/',1)[-1] not in ('self','me'): return url
    probe=page.context.new_page()
    try:
        probe.route('**/*',lambda route: route.abort() if route.request.resource_type in ('image','media','font') else route.fallback())
        probe.goto(url,wait_until='domcontentloaded',timeout=20000)
        for _ in range(24):
            check_page(probe)
            profiles=probe.locator('[data-e2e="user-info"]')
            visible=[p for p in profiles.all() if p.is_visible()]
            if len(visible)==1 and urlparse(probe.url).path.rstrip('/') in ('/user/self','/user/me'):
                handles=re.findall(r'抖音号[：:]\s*([A-Za-z0-9_.-]+)',visible[0].inner_text())
                if len(set(handles))==1: return '@'+handles[0]
            probe.wait_for_timeout(250)
        return ''
    finally:
        probe.close()
        page.bring_to_front()


def inspect_session(page):
    try:
        if urlparse(page.url).hostname not in ('www.douyin.com','douyin.com'):
            return dict(status='needs_identity',sender='',note='工具浏览器尚未打开抖音，请先打开浏览器登录。')
        check_page(page)
        actor=current_actor(page)
        if actor:
            return dict(status='identified',sender=actor,note='已从工具浏览器的“我的”入口核对本人账号：'+actor+'；尚未关注或发送。')
        return dict(status='needs_identity',sender='',note='未能从工具浏览器核对本人账号，请在该浏览器打开“我的”并完成登录，再读取账号。')
    except PagePaused as exc:
        return dict(status=exc.status,sender='',note=str(exc))


def check_identity(page, action, verify_sender=True):
    check_page(page)
    try: current=profile_url(page.url)
    except ValueError: current=''
    if current!=action['target']: raise PagePaused('blocked','浏览器没有停留在指定用户主页，已停止。')
    for _ in range(40):
        check_page(page)
        if any(p.is_visible() for p in page.locator('[data-e2e="user-info"]').all()): break
        page.wait_for_timeout(250)
    actor=current_actor(page) if verify_sender else action['sender']
    if actor!=action['sender']:
        raise PagePaused('waiting_login','无法确认当前登录账号与填写的本人主页一致，请本人登录并核对；未执行。')
    for _ in range(40):
        check_page(page)
        if any(p.is_visible() for p in page.locator('[data-e2e="user-info"]').all()): break
        page.wait_for_timeout(250)
    profile=unique(page.locator('[data-e2e="user-info"]'),'未能唯一识别用户主页操作区，需适配真实页面后再执行。')
    if action['sender'].startswith('@') and re.search(r'抖音号[：:]\s*'+re.escape(action['sender'][1:])+r'(?![A-Za-z0-9_.-])',profile.inner_text()):
        raise PagePaused('blocked','目标是当前本人账号，未执行。')
    parent=profile.locator('..')
    if parent.locator('[data-e2e="user-info"]').count()==1 and parent.locator('[data-e2e="user-info-follow-btn"]').count():
        profile=parent
    return profile


def followed(profile):
    return any(b.is_visible() for b in profile.get_by_role('button',name=re.compile(r'^(已关注|互相关注|相互关注)$')).all())


def chat_scope(page, action, profile, open_chat):
    native=page.locator('#imSaasContainerId')
    if open_chat and not (native.count() and native.is_visible()) and not any(d.is_visible() for d in page.get_by_role('dialog').all()):
        unique(profile.get_by_role('button',name='私信',exact=True),'未发现唯一可用私信入口，未发送。').click(timeout=5000)
        for _ in range(24):
            check_page(page)
            if native.locator('.StackLayoutStackChatHeadertitle').count(): break
            page.wait_for_timeout(250)
    if native.count() and native.is_visible():
        title=unique(native.locator('.StackLayoutStackChatHeadertitle'),'聊天对象标题不唯一，未发送。')
        # A nickname is not an identity: use the title's actual profile navigation.
        with page.expect_popup(timeout=5000) as opened:
            title.click(timeout=5000)
        target_page=opened.value
        try:
            target_page.wait_for_url(re.compile(r'https://(?:www\.)?douyin\.com/user/'),wait_until='commit',timeout=10000)
            if profile_url(target_page.url)!=action['target']:
                raise PagePaused('blocked','聊天窗口实际指向其他用户，未发送。')
        finally:
            target_page.close(); page.bring_to_front()
        history=unique(native.locator('.messageMessageListlist'),'聊天记录尚未加载，无法核对重复消息。')
        editor=unique(native.locator('[data-e2e="msg-input"] [data-slate-editor="true"][contenteditable="true"]'),'消息输入框不唯一或不可访问，未发送。')
        return native,history,editor
    def candidates():
        found=[]
        for dialog in page.get_by_role('dialog').all():
            if not dialog.is_visible(): continue
            targets=[]
            for link in dialog.locator('header a[href]').all():
                try: targets.append(profile_url(urljoin(page.url,link.get_attribute('href'))))
                except (ValueError,TypeError): pass
            if set(targets)=={action['target']}: found.append(dialog)
        return found
    dialogs=candidates()
    if not dialogs and open_chat:
        unique(profile.get_by_role('button',name='私信',exact=True),'未发现唯一可用私信入口，未发送。').click(timeout=5000)
        for _ in range(12):
            check_page(page); dialogs=candidates()
            if dialogs: break
            page.wait_for_timeout(250)
    if len(dialogs)!=1: raise PagePaused('blocked','不能通过聊天窗口顶部的主页链接确认接收对象，未发送。')
    dialog=dialogs[0]
    history=unique(dialog.get_by_role('log'),'未识别聊天记录区域，无法核对重复消息，未发送。')
    editor=unique(dialog.get_by_role('textbox'),'消息输入框不唯一或不可访问，未发送。')
    return dialog,history,editor


def outgoing_exists(history, message):
    # Require explicit self-authorship; an incoming identical message is not evidence.
    native=history.locator('.messageMessageBoxisFromMe [data-e2e="msg-item-content"]')
    return any(m.is_visible() and m.inner_text().strip()==message for m in [*history.get_by_role('article',name='我发送的消息',exact=True).all(),*native.all()])


def send_button(dialog):
    if dialog.get_attribute('id')=='imSaasContainerId':
        return unique(dialog.locator('[data-e2e="msg-input"] .e2e-send-msg-btn'),'未识别唯一发送按钮，未发送。')
    return unique(dialog.get_by_role('button',name='发送',exact=True),'未识别唯一发送按钮，未发送。')


def editor_text(editor):
    text=editor.input_value() if editor.evaluate('(e)=>e.tagName==="TEXTAREA" || e.tagName==="INPUT"') else editor.inner_text()
    # The live empty Slate editor contains a zero-width caret placeholder.
    # It also appends the same caret marker after typed text. Preserve internal
    # characters and real drafts; remove only the editor's boundary markers.
    return '' if not text.strip(' \t\r\n\u200b\ufeff') else text.strip('\u200b\ufeff')


def inspect(page, action, open_chat=False):
    profile=check_identity(page,action)
    if action['kind']=='follow':
        if followed(profile): return True,profile,None
        button=unique(profile.get_by_role('button',name=re.compile(r'^(关注|回关)$')),'未找到唯一关注按钮，已停止；不会点击其他用户的关注入口。')
        if not button.is_enabled(): raise PagePaused('blocked','关注按钮当前不可用，未执行。')
        return False,profile,button
    dialog,history,editor=chat_scope(page,action,profile,open_chat)
    if outgoing_exists(history,action['message']): return True,history,None
    # Do not overwrite an existing draft typed by the user.
    draft=editor_text(editor)
    if draft.strip() and draft!=action['message']: raise PagePaused('blocked','聊天输入框已有其他草稿，已停止，未覆盖。')
    send_button(dialog)
    return False,history,(dialog,editor)


def run_action(page, ledger, action, phase):
    attempted=False
    try:
        if phase in ('prepare','verify') and page.url!=action['target']:
            page.goto(action['target'],wait_until='domcontentloaded',timeout=30000)
        exists,scope,control=inspect(page,action,open_chat=phase in ('prepare','verify'))
        if exists:
            return ledger.mark(action['id'],'success' if phase=='verify' else 'already_done','页面已显示已关注状态。' if action['kind']=='follow' else '本会话已显示本人发送的相同消息，不再重复发送。')
        if phase=='verify': return ledger.mark(action['id'],'uncertain','页面仍不能确认操作结果，未再次执行。')
        if phase=='prepare': return ledger.mark(action['id'],'ready','已核对当前账号、目标和操作入口；尚未关注或发送。请在 5 分钟内明确确认。')
        if action['kind']=='message':
            dialog,editor=control
            editor.fill(action['message'],timeout=5000)
            # Re-resolve the recipient after input events, before sending anything.
            dialog,scope,editor=chat_scope(page,action,check_identity(page,action),False)
            text=editor_text(editor)
            if text!=action['message']: raise PagePaused('blocked','输入内容与确认消息不一致，未发送。')
            control=send_button(dialog)
            if not control.is_enabled(): raise PagePaused('blocked','当前不满足发送条件，发送按钮不可用。')
        if action['kind']=='follow':
            profile=check_identity(page,action)
            if followed(profile): return ledger.mark(action['id'],'already_done','页面已显示关注状态，未重复点击。')
            control=unique(profile.get_by_role('button',name=re.compile(r'^(关注|回关)$')),'关注入口变化，已停止。')
        attempted=True
        control.click(timeout=5000)
        if action['kind']=='message' and dialog.get_attribute('id')=='imSaasContainerId':
            # Confirm from a freshly loaded conversation, not a local pending echo.
            page.wait_for_timeout(1500)
            check_page(page)
            page.reload(wait_until='domcontentloaded',timeout=30000)
            exists,_,_=inspect(page,action,open_chat=True)
            return ledger.mark(action['id'],'success' if exists else 'uncertain','刷新会话后已核对本人发送的相同消息，不代表对方已读。' if exists else '已点击一次发送，但刷新后无法核实，禁止自动重发。')
        for _ in range(16):
            check_page(page)
            check_identity(page,action,verify_sender=False)
            if action['kind']=='message':
                _,scope,_=chat_scope(page,action,check_identity(page,action),False)
            if (action['kind']=='follow' and followed(scope)) or (action['kind']=='message' and outgoing_exists(scope,action['message'])):
                return ledger.mark(action['id'],'success','页面已核对关注状态。' if action['kind']=='follow' else '页面已显示本人发送的消息；不代表对方已读。')
            page.wait_for_timeout(250)
        return ledger.mark(action['id'],'uncertain','已尝试一次操作，但页面未给出可确认结果；只允许核对，不会自动重试。')
    except Exception as exc:
        # Narrow public-profile diagnostics; never save chat history or cookies.
        if not attempted and phase=='prepare':
            try:
                evidence=page.locator('[data-e2e="user-info"]').evaluate_all('''els=>els.map(e=>({text:e.innerText,controls:[...e.querySelectorAll('button,[role="button"]')].map(b=>({tag:b.tagName,text:b.innerText,role:b.getAttribute('role'),visible:!!b.getClientRects().length})),heading:e.querySelector('h1')?.innerText}))''')
                folder=ledger.store.path.parent/'account_diagnostics'; folder.mkdir(exist_ok=True)
                (folder/(action['id']+'.json')).write_text(json.dumps({'url':page.url,'profile':evidence,'error':str(exc)[:1600]},ensure_ascii=False),encoding='utf-8')
            except Exception: pass
        status='uncertain' if attempted or phase=='verify' else exc.status if isinstance(exc,PagePaused) else 'blocked'
        note=str(exc) if isinstance(exc,PagePaused) else '网页核对未完成（'+type(exc).__name__+'），请检查浏览器。'
        return ledger.mark(action['id'],status, note + (' 已尝试操作，禁止重复执行。' if attempted else ''))
