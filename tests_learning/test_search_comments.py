import pytest
from learning.store import Store

def test_pipeline_saves_comments_and_stops_on_verification(tmp_path,monkeypatch):
    from learning.search_comments import collect_search_comments
    from learning import browser,video_metadata
    s=Store(tmp_path/'db');t=s.create_task('测试','live');data={'videos':[{'id':'12345'},{'id':'23456'}],'comments':[],'users':[]}
    class Page:
        url=''
        def goto(self,url,**kwargs):self.url=url
        def wait_for_timeout(self,*args):pass
    p=Page()
    monkeypatch.setattr(browser,'check_page',lambda p:None)
    monkeypatch.setattr(video_metadata,'read_video_detail',lambda p,id:{'id':id})
    def collect(page,id,batch,progress,cancelled):
        if id=='23456':raise browser.PagePaused('waiting_verification','验证')
        batch['comments']=[{'id':'c1','video_id':id,'user_id':'u1','content':'测试'}]
        batch['users']=[{'id':'u1'}];progress()
    monkeypatch.setattr(browser,'collect_comments',collect)
    with pytest.raises(browser.PagePaused):collect_search_comments(p,s,t,data)
    result=s.result(t['id']);assert len(result['comments'])==1
    children=[v['comment_task_id'] for v in result['videos']]
    assert s.result(children[0])['pagination']['target']==100
    assert s.get_task(children[1])['status']=='waiting_verification'

def test_cancel_parent_does_not_start_another_video(tmp_path,monkeypatch):
    from learning.search_comments import collect_search_comments
    from learning import browser,video_metadata
    s=Store(tmp_path/'db');t=s.create_task('测试','live');data={'videos':[{'id':'12345'},{'id':'23456'}],'comments':[],'users':[]}
    class Page:
        url=''
        def goto(self,url,**kwargs):self.url=url
        def wait_for_timeout(self,*args):pass
    monkeypatch.setattr(browser,'check_page',lambda p:None)
    monkeypatch.setattr(video_metadata,'read_video_detail',lambda p,id:{'id':id})
    def collect(*args):s.cancel(t['id'])
    monkeypatch.setattr(browser,'collect_comments',collect)
    collect_search_comments(Page(),s,t,data)
    assert len(s.snapshot()['tasks'])==2
    assert s.get_task(data['videos'][0]['comment_task_id'])['status']=='cancelled'

def test_search_worker_automatically_reads_comments_after_partial_search(tmp_path,monkeypatch):
    from learning import browser,search_flow,video_metadata
    s=Store(tmp_path/'db');t=s.create_task('测试','live');reader=browser.BrowserReader(tmp_path/'profile')
    class Page:
        url=''
        def goto(self,url,**kwargs):self.url=url
        def wait_for_timeout(self,*args):pass
        def is_closed(self):return True
    reader.page=Page();reader.busy=True
    monkeypatch.setattr(reader,'_ensure_browser',lambda:None)
    monkeypatch.setattr(browser,'check_page',lambda p:None)
    monkeypatch.setattr(search_flow,'ensure_video_search',lambda *a:True)
    def search(page,data,*args,**kwargs):
        data['videos']=[{'id':'12345'},{'id':'23456'}]
        raise browser.PagePaused('search_stalled','部分搜索结果')
    monkeypatch.setattr(browser,'collect_search',search)
    monkeypatch.setattr(video_metadata,'read_video_detail',lambda p,id:{'id':id})
    def comments(page,id,batch,progress,cancelled):
        batch['comments']=[{'id':'c'+id,'video_id':id,'user_id':'u1','content':'评论'}]
        batch['users']=[{'id':'u1'}];progress()
        if id=='12345':raise browser.PagePaused('partial','部分评论')
    monkeypatch.setattr(browser,'collect_comments',comments)
    try:
        reader._run(s,t,False)
        result=s.result(t['id']);assert result['task']['status']=='partial'
        assert len(result['comments'])==2 and len(result['users'])==1
        assert all(v.get('comment_task_id') for v in result['videos'])
        assert not reader.busy
    finally:reader.pool.shutdown(wait=True)
