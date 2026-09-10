import pytest
from learning.store import Store
from learning.account_actions import AccountActions

PAYLOAD=dict(sender='https://www.douyin.com/user/sender', target='https://www.douyin.com/user/recipient', kind='message', message='这是一条获准测试消息')


def test_ready_confirm_exact_content_and_no_repeat(tmp_path):
    ledger=AccountActions(Store(tmp_path/'a.db'))
    intent=ledger.prepare(PAYLOAD)
    assert intent['status']=='checking'
    ready=ledger.mark(intent['id'],'ready','已核对')
    assert ready['confirm_token']
    with pytest.raises(ValueError): ledger.confirm(intent['id'],'wrong')
    action=ledger.confirm(intent['id'],ready['confirm_token'])
    assert action['status']=='executing'
    with pytest.raises(ValueError): ledger.confirm(intent['id'],ready['confirm_token'])
    ledger.mark(intent['id'],'uncertain','点击后未能核实')
    assert ledger.prepare(PAYLOAD)['status']=='uncertain'
    with pytest.raises(ValueError): ledger.confirm(intent['id'],ready['confirm_token'])


def test_restart_does_not_resend_and_accounts_are_isolated(tmp_path):
    store=Store(tmp_path/'a.db'); ledger=AccountActions(store)
    a=ledger.prepare(PAYLOAD); ready=ledger.mark(a['id'],'ready','已核对')
    ledger.confirm(a['id'],ready['confirm_token'])
    recovered=AccountActions(store)
    assert recovered.get(a['id'])['status']=='uncertain'
    assert recovered.prepare(dict(PAYLOAD,sender='https://www.douyin.com/user/another'))['id']!=a['id']


def test_ready_expires_and_blocked_can_only_prepare_again(tmp_path):
    store=Store(tmp_path/'a.db'); ledger=AccountActions(store)
    a=ledger.prepare(PAYLOAD); ready=ledger.mark(a['id'],'ready','已核对')
    with store.connect() as db: db.execute('UPDATE account_actions SET expires_at=0 WHERE id=?',(a['id'],))
    with pytest.raises(ValueError): ledger.confirm(a['id'],ready['confirm_token'])
    ledger.mark(a['id'],'waiting_login','待登录')
    assert ledger.prepare(PAYLOAD)['status']=='checking'


def test_api_requires_scope_and_confirmation(tmp_path):
    from fastapi.testclient import TestClient
    from learning.app import create_app
    class Reader:
        def __init__(self): self.calls=[]
        def submit_account_action(self,ledger,action,phase):
            self.calls.append(phase)
            ledger.mark(action['id'],'ready' if phase=='prepare' else 'success','本地接口测试')
        def open_account_browser(self): return {'note':'测试浏览器已打开'}
        def close(self): pass
    with TestClient(create_app(tmp_path/'api.db')) as api:
        reader=Reader(); api.app.state.reader=reader
        assert api.post('/api/learning/account-actions/browser/open',json={}).status_code==200
        assert reader.calls==[]
        assert api.post('/api/learning/account-actions/prepare',json=PAYLOAD).status_code==422
        ready=api.post('/api/learning/account-actions/prepare',json=dict(PAYLOAD,authorized=True)).json()
        assert reader.calls==['prepare']
        path='/api/learning/account-actions/'+ready['id']+'/confirm'
        assert api.post(path,json=dict(token=ready['confirm_token'],confirmed=False)).status_code==422
        assert api.post(path,json=dict(token='wrong',confirmed=True)).status_code==409
        assert api.post(path,json=dict(token=ready['confirm_token'],confirmed=True)).status_code==200
        assert api.post(path,json=dict(token=ready['confirm_token'],confirmed=True)).status_code==409
        assert reader.calls==['prepare','execute']
