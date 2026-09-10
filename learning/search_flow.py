"""Normal search-tab selection and visible page state. No private requests."""
import re
from urllib.parse import urlparse, parse_qs


def ensure_video_search(page, cancelled):
    from .browser import check_page, PagePaused
    def selected():
        return parse_qs(urlparse(page.url).query).get('type') == ['video'] or page.locator('[role="tab"][aria-selected="true"]').filter(has_text=re.compile(r'^视频$')).count() > 0
    check_page(page)
    if selected(): return True
    controls = []
    for _ in range(20):
        if cancelled(): return False
        check_page(page)
        controls = [c for c in page.get_by_text('视频',exact=True).all() if c.is_visible()]
        if len(controls) == 1: break
        page.wait_for_timeout(500)
    if len(controls) != 1:
        raise PagePaused('pending_layout','未能唯一识别“视频”分类入口，已停止；请在浏览器中选择视频分类后继续。')
    controls[0].click(timeout=5000)
    for _ in range(20):
        if cancelled(): return False
        check_page(page)
        if selected():
            page.wait_for_timeout(500)
            check_page(page)
            return True
        page.wait_for_timeout(500)
    raise PagePaused('pending_layout','已点击“视频”，但未确认分类切换完成；请核对浏览器，未继续读取综合结果。')


def search_page_state(page):
    # Read transient labels atomically: the virtual list can replace nodes at any time.
    return page.locator('body').evaluate('''root=>{
      const excluded='[id^="waterfall_item_"], .search-result-card, [data-e2e="comment-item"], nav, aside, [role="dialog"]';
      let ended=false, loading=false;
      for(const e of root.querySelectorAll('*')) {
        const text=(e.textContent||'').trim();
        const end=/^(暂时没有更多了|没有更多了|暂无更多结果|没有更多搜索结果|没有找到相关结果|暂无搜索结果)$/.test(text);
        const load=/^(正在加载|加载中|加载更多)(?:[.。…]*)$/.test(text);
        if((!end&&!load)||e.closest(excluded))continue;
        const r=e.getBoundingClientRect();
        if(r.width>0&&r.height>0&&r.bottom>0&&r.top<innerHeight&&getComputedStyle(e).visibility!=='hidden'){ended ||= end;loading ||= load;}
      }
      return {ended,loading};
    }''')


def scroll_search(page):
    """Use live DOM references in one operation, avoiding stale virtual-list locators."""
    from pathlib import Path
    import json
    selectors=json.loads(Path(__file__).with_name('selectors.json').read_text(encoding='utf-8'))
    return page.locator('body').evaluate('''(root,selector)=>{
      const visible=e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
      let rows=[...root.querySelectorAll(selector)].filter(visible);
      if(!rows.length)rows=[...root.querySelectorAll('a[href*="/video/"], a[href*="modal_id="]')].filter(visible);
      const last=rows[rows.length-1];if(!last)return {before:0,after:0,height:0};
      let p=last.parentElement;
      while(p){const style=getComputedStyle(p);if(/auto|scroll/.test(style.overflowY)&&p.scrollHeight>p.clientHeight+8)break;p=p.parentElement;}
      const target=p||document.scrollingElement;
      const before=target.scrollTop;
      last.scrollIntoView({block:'end',behavior:'instant'});
      target.scrollBy(0,Math.max(400,(p?p.clientHeight:innerHeight)*.8));
      return {before,after:target.scrollTop,height:target.scrollHeight};
    }''',selectors.get('search_card') or 'a[href*="/video/"], a[href*="modal_id="]')
