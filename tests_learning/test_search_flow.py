import pytest
from playwright.sync_api import sync_playwright
from learning.browser import PagePaused, collect_search


@pytest.fixture
def page():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,channel='chromium')
        yield browser.new_page(viewport={'width':1000,'height':800})
        browser.close()


def test_select_video_category_and_fail_closed_for_verification(page):
    from learning.search_flow import ensure_video_search
    page.route('**/search/test*',lambda r:r.fulfill(body='''<meta charset="utf-8"><nav><button>综合</button><button onclick="history.replaceState({},'', '?type=video');this.setAttribute('aria-selected','true')">视频</button><button>用户</button></nav>''',content_type='text/html'))
    page.goto('https://www.douyin.com/search/test')
    assert ensure_video_search(page,lambda:False)
    assert page.url.endswith('?type=video')
    page.set_content('<p>安全验证</p><button>视频</button>')
    with pytest.raises(PagePaused) as exc: ensure_video_search(page,lambda:False)
    assert exc.value.status=='waiting_verification'


def test_end_marker_excludes_video_title_and_hidden_or_offscreen_text(page):
    from learning.search_flow import search_page_state
    page.set_content('<div id="waterfall_item_123"><span>暂时没有更多了</span></div><p hidden>暂时没有更多了</p><p style="position:absolute;top:3000px">暂时没有更多了</p>')
    assert not search_page_state(page)['ended']
    page.set_content('<main><p>暂时没有更多了</p></main>')
    assert search_page_state(page)['ended']


def test_explicit_end_keeps_real_count_and_stall_is_separate(page):
    page.set_content('<a href="https://www.douyin.com/video/123">一个视频</a><p>暂时没有更多了</p>')
    data={'videos':[]}
    with pytest.raises(PagePaused) as exc: collect_search(page,data,100,lambda:None,lambda:False,poll_ms=20,idle_timeout=.2)
    assert exc.value.status=='search_exhausted'
    assert len(data['videos'])==1
    page.set_content('<a href="https://www.douyin.com/video/123">一个视频</a>')
    with pytest.raises(PagePaused) as exc: collect_search(page,{'videos':[]},100,lambda:None,lambda:False,poll_ms=20,idle_timeout=.08)
    assert exc.value.status=='search_stalled'


def test_slow_loading_more_than_five_polls_and_nested_scroll(page):
    page.set_content('''<div id="list" style="height:180px;overflow-y:auto"><div id="waterfall_item_1" style="height:500px">00:10<br>第一个</div></div>
    <script>let scheduled=false;list.addEventListener('scroll',()=>{if(!scheduled){scheduled=true;setTimeout(()=>list.insertAdjacentHTML('beforeend','<div id="waterfall_item_2">00:20<br>第二个</div>'),400)}})</script>''')
    data={'videos':[]}; notes=[]
    collect_search(page,data,2,lambda:notes.append(data.get('search_note')),lambda:False,poll_ms=20,idle_timeout=2)
    assert [v['id'] for v in data['videos']]==['1','2']
    assert page.locator('#list').evaluate('(e)=>e.scrollTop')>0


def test_cancellation_and_verification_stop_without_claiming_end(page):
    page.set_content('<a href="https://www.douyin.com/video/123">一个视频</a>')
    data={'videos':[]}
    collect_search(page,data,100,lambda:None,lambda:True,poll_ms=20)
    assert not data['videos']
    with pytest.raises(PagePaused) as exc:
        collect_search(page,data,100,lambda:page.set_content('安全验证'),lambda:False,poll_ms=20)
    assert exc.value.status=='waiting_verification'
    assert len(data['videos'])==1
