"""Read only visible video information. No private APIs or inferred hidden counts."""
import re
import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal

METRICS = {'digg_count': '点赞', 'comment_count': '评论', 'collect_count': '收藏', 'share_count': '分享', 'play_count': '播放', 'danmaku_count': '弹幕'}


def parse_count(raw):
    if raw is None: return None
    value = str(raw).strip().replace(',', '').replace('，', '')
    if not re.fullmatch(r'\d+(?:\.\d+)?[万亿wWkKmM]?\+?', value): return None
    value = value.rstrip('+')
    unit = value[-1] if value[-1] in '万亿wWkKmM' else ''
    number = Decimal(value[:-1] if unit else value)
    scale = {'万':10000, '亿':100000000, 'w':10000, 'k':1000, 'm':1000000}.get(unit.lower(), 1)
    result = number * scale
    return int(result) if result == int(result) and result <= 9007199254740991 else None


def observed_metric(text, source):
    value = parse_count(text)
    if value is None: return None
    return dict(value=value, text=str(text).strip(), approximate=bool(re.search('[万亿wWkKmM+]',str(text))),
                source=source, observed_at=datetime.now(timezone.utc).isoformat(timespec='seconds'))


def duration_seconds(text):
    if not re.fullmatch(r'(?:\d{1,2}:)?\d{1,3}:\d{2}', text or ''): return None
    parts = [int(p) for p in text.split(':')]
    if parts[-1]>=60 or len(parts)==3 and parts[-2]>=60: return None
    return sum(value * 60**i for i,value in enumerate(reversed(parts)))


def published_fields(text):
    result = {'published_text': text} if text else {}
    # Relative labels stay as labels: "2 days ago" is not an exact publication time.
    match = re.search(r'(20\d{2})[年/.-](\d{1,2})[月/.-](\d{1,2})日?(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?', text or '')
    if match:
        try:
            y,m,d,h,minute,sec = match.groups()
            result['published_at'] = datetime(int(y),int(m),int(d),int(h or 0),int(minute or 0),int(sec or 0),tzinfo=timezone(timedelta(hours=8))).isoformat()
            result['published_precision'] = 'time' if h else 'day'
        except ValueError: pass
    return result


def search_card_fields(lines):
    result = {'duration': lines[0].strip(), 'duration_seconds': duration_seconds(lines[0].strip()), 'metrics': {}}
    # Search card layout: duration, visible like count, caption, author, publication label.
    if len(lines)>1:
        metric = observed_metric(lines[1].strip(), 'search_card')
        if metric: result['metrics']['digg_count'] = metric
    # Caption mentions may start with @ too. Only accept the trailing author row.
    author_index = next((i for i in range(len(lines)-1,max(1,len(lines)-3),-1) if lines[i].strip().startswith('@')), None)
    if author_index is not None:
        result['author'] = lines[author_index].strip()
        if author_index+1<len(lines): result.update(published_fields(lines[author_index+1].strip()))
    return result


def search_text_fields(text):
    """Only decode the known multiline card; never numbers in an ordinary caption."""
    lines=[line.strip() for line in text.strip().splitlines() if line.strip()]
    if lines and lines[0]=='合集':lines=lines[1:]
    if len(lines)<3 or duration_seconds(lines[0]) is None or parse_count(lines[1]) is None:
        return {}
    fields=search_card_fields(lines)
    end=len(lines)
    if fields.get('author'):
        end=max(i for i,line in enumerate(lines) if line==fields['author'])
    caption='\n'.join(lines[2:end]).strip()
    if not caption:return {}
    return dict(fields,title=caption[:1000],search_card_text=text,content_type='video')


def repair_search_snapshots(db):
    """Idempotently decode saved text, retaining original evidence and existing metrics."""
    timestamps={}
    for row in db.execute('''SELECT e.rowid AS rid,e.entity_id,e.payload,t.created_at FROM task_entities e
        JOIN tasks t ON t.id=e.task_id WHERE e.kind='videos' AND e.source='live' ORDER BY t.created_at''').fetchall():
        item=json.loads(row['payload']);raw=item.get('title','')
        timestamps[(row['entity_id'],raw)]=row['created_at']
        fixed=_repair_snapshot(item,row['created_at'])
        if fixed:db.execute('UPDATE task_entities SET payload=? WHERE rowid=?',(json.dumps(fixed,ensure_ascii=False),row['rid']))
    for row in db.execute("SELECT rowid AS rid,id,payload FROM entities WHERE kind='videos' AND source='live'").fetchall():
        item=json.loads(row['payload'])
        fixed=_repair_snapshot(item,timestamps.get((row['id'],item.get('title',''))))
        if fixed:db.execute('UPDATE entities SET payload=? WHERE rowid=?',(json.dumps(fixed,ensure_ascii=False),row['rid']))


def _repair_snapshot(item,task_time):
    if item.get('search_card_text'):return None
    fields=search_text_fields(item.get('title',''))
    if not fields:return None
    for metric in fields['metrics'].values():
        metric.update(observed_at=task_time,source='saved_search_card',time_basis='task_created_at' if task_time else 'unknown')
    fixed={**fields,**item,'title':fields['title'],'search_card_text':fields['search_card_text']}
    fixed['metrics']={**fields['metrics'],**item.get('metrics',{})}
    for key in ('author','duration','duration_seconds','published_text','published_at','published_precision'):
        if not fixed.get(key) and fields.get(key) is not None:fixed[key]=fields[key]
    return fixed


DETAIL_JS = r'''root => {
  const visible=e=>!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
  const excluded=e=>!!e.closest('[data-e2e="comment-list"],[data-e2e="comment-item"],[data-e2e="related-video"],[data-e2e="aweme-relate"]');
  const nodes=[root,...root.querySelectorAll('*')].filter(e=>visible(e)&&!excluded(e));
  const info=nodes.find(e=>e.matches('[data-e2e="detail-video-info"]'));
  const authorAreas=[...root.querySelectorAll('[data-e2e="user-info"]')].filter(visible);
  const author=authorAreas.length===1?[...authorAreas[0].querySelectorAll('a[href*="/user/"]')].find(e=>visible(e)&&e.innerText.trim())
    :info?.querySelector('a[data-e2e="video-author"][href*="/user/"]');
  const authorName=author?.querySelector('[data-click-from="title"] > span')||author;
  const title=info?.querySelector('h1,[data-e2e="video-desc"],[data-e2e="video-title"]');
  const published=nodes.find(e=>e.matches('[data-e2e="detail-video-publish-time"],time[datetime]'));
  const video=nodes.find(e=>e.tagName==='VIDEO');
  const candidates=nodes.filter(e=>e.children.length===0||e.matches('[aria-label],[title],[data-e2e],button'))
    .map(e=>({text:(e.innerText||'').trim(),label:e.getAttribute('aria-label')||e.getAttribute('title')||'',marker:e.getAttribute('data-e2e')||''}))
    .filter(e=>e.text.length<80 && (e.label||/点赞|评论|收藏|分享|播放|弹幕/.test(e.text)||e.marker));
  // Verified desktop toolbar: four sibling icon/counter items, share explicitly marked last.
  // Refuse positional decoding if that structure or the video identity changes.
  const share=info?.querySelector('[data-e2e="video-share-icon-container"]');
  const items=share?[...share.parentElement.children].filter(visible):[];
  const toolbar=items.length===4&&items[3]===share&&items.every(e=>e.querySelector('[data-popupid] svg')&&e.querySelector(':scope > span'))
    ?items.map(e=>e.querySelector(':scope > span').innerText.trim()):[];
  return {aweme_id:info?.getAttribute('data-e2e-aweme-id'), toolbar,title:(title?.innerText||'').trim(),author:authorName?.innerText?.trim()||'',author_url:author?.href||'',
    published:published?.getAttribute('datetime')||published?.innerText?.trim()||'',
    duration:video&&Number.isFinite(video.duration)?video.duration:null,candidates};
}'''


def read_video_detail(page, video_id):
    from .browser import check_page, current_video_id, PagePaused
    check_page(page)
    if current_video_id(page.url)!=video_id: raise PagePaused('needs_review','当前页面与所选视频不符，已停止信息读取。')
    roots=page.locator('[data-e2e="video-detail"]').all()
    roots=[root for root in roots if root.is_visible()]
    if len(roots)!=1: raise PagePaused('pending_layout','未识别唯一视频详情区域，请核对页面后再读取信息。')
    raw=roots[0].evaluate(DETAIL_JS)
    if raw.get('aweme_id') and raw['aweme_id']!=video_id:
        raise PagePaused('needs_review','视频内容尚未切换到所选对象，已暂停信息读取。')
    result=dict(id=video_id,url=f'https://www.douyin.com/video/{video_id}',metrics={},
                metadata_read_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),metadata_status='read')
    for field in ('title','author','author_url'):
        if raw.get(field): result[field]=raw[field][:1000]
    result.update(published_fields(raw.get('published','')))
    if raw.get('duration') is not None: result['duration_seconds']=round(raw['duration'],2)
    marker_names={'digg_count':['video-player-digg','video-digg','video-like'], 'comment_count':['video-player-comment','video-comment'],
                  'collect_count':['video-player-collect','video-collect'], 'share_count':['video-player-share','video-share'],
                  'play_count':['video-play-count'], 'danmaku_count':['video-danmaku-count']}
    count=r'(\d[\d,，]*(?:\.\d+)?[万亿wWkKmM]?\+?)'
    for key,label in METRICS.items():
        candidates=[]
        if len(raw.get('toolbar',[]))==4 and key in ('digg_count','comment_count','collect_count','share_count'):
            text=raw['toolbar'][('digg_count','comment_count','collect_count','share_count').index(key)]
            if parse_count(text) is not None: candidates.append(text)
        for node in raw['candidates']:
            for text in (node['label'],node['text']):
                match=re.fullmatch(r'(?:取消)?'+label+r'(?:量|数)?\s*[:：]?\s*'+count, text) or re.fullmatch(count+r'\s*(?:次|条)?\s*'+label, text)
                if match: candidates.append(match.group(1))
            if node['marker'] in marker_names[key] and parse_count(node['text']) is not None: candidates.append(node['text'])
            if node['label'] in (label,'取消'+label) and parse_count(node['text']) is not None: candidates.append(node['text'])
        # Conflicting counters mean unknown, never pick the largest or a recommendation.
        values={parse_count(t) for t in candidates}; values.discard(None)
        if len(values)==1: result['metrics'][key]=observed_metric(next(t for t in candidates if parse_count(t) in values),'video_detail')
    result['metadata_missing']=[key for key in METRICS if key not in result['metrics']]
    return result
