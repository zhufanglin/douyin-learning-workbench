import pytest
from playwright.sync_api import sync_playwright
from learning.store import Store
from learning.account_actions import AccountActions
from learning.account_browser import run_action

SENDER='https://www.douyin.com/user/sender'
TARGET='https://www.douyin.com/user/recipient'


def test_self_alias_identifies_visible_handle_and_stops_changed_actor(tmp_path):
    from learning.account_browser import inspect_session
    ledger=AccountActions(Store(tmp_path/'a.db'))
    action=ledger.prepare(dict(sender='@tester',target=TARGET,kind='follow',message=''))
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,channel='chromium'); context=browser.new_context()
        current={'handle':'tester'}
        def route(r):
            body=f'<meta charset="utf-8"><nav><a href="/user/self">我的</a></nav><div data-e2e="user-info"><h1>本人</h1><p>抖音号： {current["handle"]}</p></div>' if '/user/self' in r.request.url else html().replace(SENDER,'/user/self')
            r.fulfill(body=body,content_type='text/html')
        context.route('**/*',route); page=context.new_page(); page.goto(TARGET)
        assert inspect_session(page)['sender']=='@tester'
        assert len(context.pages)==1
        ready=run_action(page,ledger,action,'prepare')
        assert ready['status']=='ready',ready
        current['handle']='different'
        result=run_action(page,ledger,ledger.confirm(action['id'],ready['confirm_token']),'execute')
        assert result['status']=='waiting_login',result
        assert page.evaluate('window.followClicks')==0
        assert len(context.pages)==1
        browser.close()


def test_native_message_authorship_not_incoming_match():
    from learning.account_browser import outgoing_exists
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,channel='chromium'); page=browser.new_page()
        page.set_content('<div id="history"><div class="messageMessageBoxcontentBox"><div data-e2e="msg-item-content">测试</div></div></div>')
        assert not outgoing_exists(page.locator('#history'),'测试')
        page.set_content('<div id="history"><div class="messageMessageBoxcontentBox messageMessageBoxisFromMe"><div data-e2e="msg-item-content">测试</div></div></div>')
        assert outgoing_exists(page.locator('#history'),'测试')
        browser.close()


def test_native_sibling_controls_wait_for_profile_and_ignore_recommendations(tmp_path):
    ledger=AccountActions(Store(tmp_path/'a.db'))
    action=ledger.prepare(dict(sender=SENDER,target=TARGET,kind='follow',message=''))
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,channel='chromium'); page=browser.new_page()
        body=f'''<meta charset="utf-8"><nav><a href="{SENDER}">我</a></nav><section id="profile"></section><aside><button onclick="window.wrong++">关注</button></aside>
        <script>window.wrong=0;window.sent=0;setTimeout(()=>document.querySelector('#profile').innerHTML=`<div data-e2e="user-info"><h1>目标</h1></div><div><button data-e2e="user-info-follow-btn" onclick="window.sent++;this.textContent='相互关注'">回关</button></div>`,400)</script>'''
        page.route('**/*',lambda r:r.fulfill(body=body,content_type='text/html'))
        ready=run_action(page,ledger,action,'prepare'); assert ready['status']=='ready',ready
        result=run_action(page,ledger,ledger.confirm(action['id'],ready['confirm_token']),'execute')
        assert result['status']=='success',result
        assert page.evaluate('[window.sent,window.wrong]')==[1,0]
        browser.close()


def test_session_probe_under_real_navigation_marker_and_ambiguous_identity():
    from learning.account_browser import inspect_session
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,channel='chromium'); page=browser.new_context().new_page()
        page.context.route('**/*',lambda r:r.fulfill(body=f'<meta charset="utf-8"><div data-e2e="douyin-navigation"><a href="{SENDER}">我的</a></div>',content_type='text/html'))
        page.goto('https://www.douyin.com/')
        assert inspect_session(page)['sender']==SENDER
        page.set_content('<nav><a href="https://www.douyin.com/user/self">我的</a></nav>')
        assert inspect_session(page)['status']=='needs_identity'
        page.set_content(f'<nav><a href="{SENDER}">我的</a><a href="{TARGET}">我</a></nav>')
        assert inspect_session(page)['status']=='needs_identity'
        page.set_content('安全验证')
        assert inspect_session(page)['status']=='waiting_verification'
        browser.close()


@pytest.mark.parametrize('mode,expected',[('persisted','success'),('local_echo','uncertain'),('wrong_chat','blocked')])
def test_native_chat_checks_profile_and_requires_persisted_message(tmp_path,mode,expected):
    ledger=AccountActions(Store(tmp_path/'native.db'))
    action=ledger.prepare(dict(sender=SENDER,target=TARGET,kind='message',message='测试'))
    chat_target=TARGET if mode!='wrong_chat' else 'https://www.douyin.com/user/other'
    saved={'value':False,'clicks':0}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,channel='chromium'); context=browser.new_context()
        context.expose_function('recordSend',lambda: saved.update(value=mode=='persisted',clicks=saved['clicks']+1))
        def route(r):
            if r.request.url=='https://fixture.invalid/slow.png': return
            existing='<div class="messageMessageBoxisFromMe"><div data-e2e="msg-item-content">测试</div></div>' if saved['value'] else ''
            body=f'''<meta charset="utf-8"><img src="https://fixture.invalid/slow.png"><nav><a href="{SENDER}">我</a></nav><div data-e2e="user-info"><button>私信</button></div>
            <div id="imSaasContainerId"><div class="StackLayoutStackChatHeadertitle" onclick="window.open('{chat_target}')">同名用户</div>
            <div class="messageMessageListlist"><div data-e2e="msg-item-content">测试</div>{existing}</div>
            <div data-e2e="msg-input"><div contenteditable="true" data-slate-editor="true" oninput="if(!this.textContent.endsWith(String.fromCharCode(8203)))this.textContent+=String.fromCharCode(8203)">\u200b</div><button class="e2e-send-msg-btn" onclick="recordSend();this.previousElementSibling.textContent='';">发送</button></div></div>'''
            r.fulfill(body=body,content_type='text/html')
        context.route('**/*',route); page=context.new_page()
        result=run_action(page,ledger,action,'prepare')
        assert saved['clicks']==0
        if mode!='wrong_chat':
            assert result['status']=='ready',result
            result=run_action(page,ledger,ledger.confirm(action['id'],result['confirm_token']),'execute')
        assert result['status']==expected,result
        assert saved['clicks']==(0 if mode=='wrong_chat' else 1)
        assert len(context.pages)==1
        browser.close()

def html(mode='normal'):
    sender=SENDER if mode!='wrong_sender' else 'https://www.douyin.com/user/other'
    chat=TARGET if mode!='wrong_chat' else 'https://www.douyin.com/user/other'
    return f'''<html><head><meta charset="utf-8"></head><body><nav aria-label="主导航"><a href="{sender}">我</a></nav>
    <div data-e2e="user-info"><button onclick="window.followClicks++;this.textContent='已关注'">关注</button><button>私信</button></div>
    <div role="dialog"><header><a href="{chat}">测试接收对象</a></header>
    <div role="log"><article aria-label="收到的消息">测试消息</article></div><textarea aria-label="消息">{'其他草稿' if mode=='draft' else ''}</textarea>
    <button onclick="window.sendClicks++;{'void 0' if mode=='uncertain' else "const a=document.createElement('article');a.setAttribute('aria-label','我发送的消息');a.textContent=document.querySelector('textarea').value;document.querySelector('[role=log]').append(a);document.querySelector('textarea').value='';"}">发送</button></div>
    {'安全验证' if mode=='verification' else ''}<script>window.followClicks=0;window.sendClicks=0;</script></body></html>'''

@pytest.mark.parametrize('kind',['follow','message'])
def test_prepare_never_sends_then_confirm_once(tmp_path,kind):
    ledger=AccountActions(Store(tmp_path/'a.db'))
    action=ledger.prepare(dict(sender=SENDER,target=TARGET,kind=kind,message='测试消息' if kind=='message' else ''))
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,channel='chromium'); page=browser.new_page()
        page.route('**/*',lambda r:r.fulfill(body=html(),content_type='text/html'))
        ready=run_action(page,ledger,action,'prepare')
        assert ready['status']=='ready',ready
        assert page.evaluate('window.followClicks+window.sendClicks')==0
        action=ledger.confirm(action['id'],ready['confirm_token'])
        result=run_action(page,ledger,action,'execute')
        assert result['status']=='success',result
        assert page.evaluate('window.followClicks+window.sendClicks')==1
        assert ledger.prepare({k:action[k] for k in ('sender','target','kind','message')})['status']=='success'
        with pytest.raises(ValueError): ledger.confirm(action['id'],ready['confirm_token'])
        browser.close()

@pytest.mark.parametrize('mode,status',[('wrong_sender','waiting_login'),('wrong_chat','blocked'),('draft','blocked'),('verification','waiting_verification'),('uncertain','uncertain')])
def test_stop_or_keep_uncertain_without_repeat(tmp_path,mode,status):
    ledger=AccountActions(Store(tmp_path/'a.db')); payload=dict(sender=SENDER,target=TARGET,kind='message',message='测试消息'); action=ledger.prepare(payload)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,channel='chromium'); page=browser.new_page()
        page.route('**/*',lambda r:r.fulfill(body=html(mode),content_type='text/html'))
        result=run_action(page,ledger,action,'prepare')
        if mode=='uncertain':
            result=run_action(page,ledger,ledger.confirm(action['id'],result['confirm_token']),'execute')
        assert result['status']==status,result
        assert page.evaluate('window.sendClicks')==(1 if mode=='uncertain' else 0)
        if mode=='uncertain':
            assert ledger.prepare(payload)['status']=='uncertain'
            verification=ledger.verify(action['id'])
            assert run_action(page,ledger,verification,'verify')['status']=='uncertain'
            assert page.evaluate('window.sendClicks')==1
        browser.close()
