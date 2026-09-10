"""Opt-in, in-memory viewport snapshots. All page access stays on its worker."""
import base64
import threading
import time
from urllib.parse import urlparse


class BrowserPreview:
    def __init__(self, clock=time.monotonic):
        self.clock=clock
        self.lock=threading.Lock()
        self.lease=0
        self.last_attempt=0
        self.captured=0
        self.focus=False
        self.state=dict(status='idle',image=None,url='',sequence=0)

    def request(self, focus=False):
        with self.lock:
            self.lease=self.clock()+8
            self.focus=self.focus or focus

    def clear(self,status='closed'):
        with self.lock:
            self.state.update(status=status,image=None,url='')

    def snapshot(self):
        with self.lock:
            return dict(self.state,age_ms=round((self.clock()-self.captured)*1000) if self.captured else None)

    def capture(self,page):
        now=self.clock()
        with self.lock:
            if now>self.lease: return
            focus=self.focus; self.focus=False
            if not focus and now-self.last_attempt<1.2: return
            self.last_attempt=now
        try:
            if page is None or page.is_closed():
                self.clear('closed' if page else 'idle'); return
            parsed=urlparse(page.url)
            if parsed.scheme!='https' or parsed.hostname not in ('douyin.com','www.douyin.com'):
                self.clear('waiting'); return
            if focus: page.bring_to_front()
            shot=page.screenshot(type='jpeg',quality=48,full_page=False,timeout=900)
            with self.lock:
                self.captured=self.clock()
                self.state=dict(status='live',image='data:image/jpeg;base64,'+base64.b64encode(shot).decode(),url=parsed.scheme+'://'+parsed.netloc+parsed.path,sequence=self.state['sequence']+1)
        except Exception:
            # Preview failure must never stop capture or an authorized action.
            with self.lock: self.state['status']='waiting'
