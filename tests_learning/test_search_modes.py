import pytest
from fastapi.testclient import TestClient
from learning.app import create_app
from learning.store import Store

def test_modes_recorded_and_resumed(tmp_path):
 with TestClient(create_app(tmp_path/'db')) as api:
  class Reader:
   def close(self):pass
   def submit(self,store,task,**kwargs):pass
  api.app.state.reader=Reader()
  for mode in ('videos','comments'):
   t=api.post('/api/learning/tasks',json={'keyword':'测试','source':'live','search_mode':mode}).json()
   assert t['search_mode']==mode
   assert api.post('/api/learning/tasks/'+t['id']+'/resume-search').json()['search_mode']==mode
   assert api.post('/api/learning/browser/search-current',json={'keyword':'测试','search_mode':mode}).json()['search_mode']==mode
  assert api.post('/api/learning/tasks',json={'keyword':'测试','search_mode':'invalid'}).status_code==422

@pytest.mark.parametrize('partial',[False,True])
def test_video_mode_never_collects_comments(tmp_path,monkeypatch,partial):
 from learning import browser,search_flow,search_comments
 s=Store(tmp_path/'db');t=s.create_task('测试','live',search_mode='videos');reader=browser.BrowserReader(tmp_path/'profile')
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
  data['videos']=[{'id':'12345'}]
  if partial:raise browser.PagePaused('search_stalled','部分搜索结果')
 monkeypatch.setattr(browser,'collect_search',search)
 def forbidden(*a):raise AssertionError('Video mode must not read comments')
 monkeypatch.setattr(search_comments,'collect_search_comments',forbidden)
 try:
  reader._run(s,t,False)
  result=s.result(t['id'])
  assert result['task']['status']==('partial' if partial else 'success')
  assert len(result['videos'])==1 and result['comments']==[]
  assert len(s.snapshot()['tasks'])==1
 finally:reader.pool.shutdown(wait=True)
