import csv
import io
import json
import pytest
from fastapi.testclient import TestClient
from learning.app import create_app


def test_selected_export_scope_formats_and_no_mutation(tmp_path):
    with TestClient(create_app(tmp_path/'test.db')) as api:
        store = api.app.state.store
        task = store.create_task('导出测试', 'live')
        store.finish(task['id'], {'videos':[{'id':'123','title':'=危险公式'}, {'id':'456','title':'未选择'}]}, 'success','完成')
        before = store.result(task['id'])
        target = dict(kind='videos', source='live', id='123')
        r = api.post('/api/learning/export-selected', json={'targets':[target,target], 'format':'json'})
        assert r.status_code == 200
        assert len(r.json()['records']) == 1
        assert r.json()['records'][0]['id'] == '123'
        r = api.post('/api/learning/export-selected', json={'targets':[target], 'format':'csv'})
        rows = list(csv.DictReader(io.StringIO(r.content.decode('utf-8-sig'))))
        assert rows[0]['title'] == "'=危险公式"
        r = api.post('/api/learning/export-selected', json={'targets':[dict(target,id='missing')], 'format':'json'})
        assert r.status_code == 404
        r = api.post('/api/learning/export-selected', json={'targets':[dict(target,source='import')], 'format':'json'})
        assert r.status_code == 404
        r = api.post('/api/learning/export-selected', json={'targets':[dict(kind='tasks',source='live',id=task['id'])], 'format':'json'})
        assert len(r.json()['records'][0]['videos']) == 2
        assert store.result(task['id']) == before


def test_task_video_export_keeps_historical_snapshot_and_import_log_source(tmp_path):
    with TestClient(create_app(tmp_path/'test.db')) as api:
        store=api.app.state.store
        old=store.create_task('旧任务','import'); store.finish(old['id'], {'videos':[dict(id='12345',title='旧标题')]}, 'success','导入完成')
        new=store.create_task('新任务','import'); store.finish(new['id'], {'videos':[dict(id='12345',title='新标题')]}, 'success','导入完成')
        r=api.post('/api/learning/export-selected',json={'targets':[dict(kind='videos',source='import',id='12345')],'task_id':old['id']})
        assert r.json()['records'][0]['title']=='旧标题'
        log=store.snapshot(False)['logs'][0]
        assert log['source']=='import'
        r=api.post('/api/learning/export-selected',json={'targets':[dict(kind='logs',source='import',id=str(log['id']))]})
        assert r.json()['records'][0]['task_id']==new['id']


def test_download_job_duplicate_validation_and_recovery(tmp_path):
    from learning.downloads import Downloads
    from learning.store import Store
    store = Store(tmp_path/'test.db')
    manager = Downloads(store)
    videos = [dict(id='123',source='live',title='视频')]
    job, created = manager.create('a'*32, videos)
    assert created
    assert not manager.create('a'*32, videos)[1]
    with pytest.raises(ValueError): manager.create('b'*32, videos)
    manager.finish(job['id'], 'blocked', '浏览器忙')
    job2, created = manager.create('b'*32, videos)
    assert created
    recovered = Downloads(store).get(job2['id'])
    assert recovered['status'] == 'interrupted'
    assert recovered['items'][0]['status'] == 'interrupted'
    assert not manager.get(job['id'])['ready']


def test_download_api_repeated_submission_dispatches_once(tmp_path):
    with TestClient(create_app(tmp_path/'test.db')) as api:
        store=api.app.state.store
        task=store.create_task('视频','live'); store.finish(task['id'],{'videos':[dict(id='12345',title='视频')]},'success','完成')
        calls=[]
        class Reader:
            def close(self): pass
            def submit_downloads(self,manager,identity): calls.append(identity)
        api.app.state.reader=Reader()
        payload={'request_id':'a'*32,'targets':[dict(kind='videos',source='live',id='12345')]}
        for _ in range(2): assert api.post('/api/learning/downloads',json=payload).status_code==200
        assert calls==['a'*32]
        assert api.get('/api/learning/downloads/'+'a'*32+'/file').status_code==409
        assert api.post('/api/learning/downloads/'+'a'*32+'/cancel').json()['cancel_requested']
        assert api.post('/api/learning/downloads',json=dict(payload,request_id='b'*32)).status_code==409
        assert len(api.get('/api/learning/downloads').json()['items'])==1
