"""Fixed demo data and a narrow MediaCrawler JSON import adapter."""

DEMO_VIDEOS = [
    {'id': 'demo-video-1', 'title': '周末露营：帐篷与营地准备', 'url': '', 'author': '示例创作者A'},
    {'id': 'demo-video-2', 'title': '露营野餐的一天', 'url': '', 'author': '示例创作者B'},
    {'id': 'demo-video-3', 'title': '在家做咖啡', 'url': '', 'author': '示例创作者C'},
]
DEMO_USERS = [
    {'id': 'demo-user-1', 'nickname': '模拟用户 · 小林', 'profile_url': ''},
    {'id': 'demo-user-2', 'nickname': '模拟用户 · 阿青', 'profile_url': ''},
]
DEMO_COMMENTS = [
    {'id': 'demo-comment-1', 'video_id': 'demo-video-1', 'user_id': 'demo-user-1', 'content': '想了解帐篷怎么选（模拟评论）'},
    {'id': 'demo-comment-2', 'video_id': 'demo-video-1', 'user_id': 'demo-user-2', 'content': '周末也想去试试（模拟评论）'},
    {'id': 'demo-comment-3', 'video_id': 'demo-video-2', 'user_id': 'demo-user-1', 'content': '这个营地看起来不错（模拟评论）'},
]


def demo_search(keyword):
    videos = [v for v in DEMO_VIDEOS if keyword.casefold() in v['title'].casefold()]
    ids = {v['id'] for v in videos}
    comments = [c for c in DEMO_COMMENTS if c['video_id'] in ids]
    user_ids = {c['user_id'] for c in comments}
    return dict(videos=videos, comments=comments, users=[u for u in DEMO_USERS if u['id'] in user_ids])


def safe_text(value, limit=2000):
    if value is None:
        return ''
    if not isinstance(value, (str, int, float)):
        raise ValueError('字段必须是文字或数字。')
    text = str(value).strip()
    if len(text) > limit:
        raise ValueError(f'字段超过 {limit} 字符。')
    return text


def import_records(records):
    data = dict(videos=[], comments=[], users=[])
    for row in records:
        video_id = safe_text(row.get('aweme_id'), 200)
        comment_id = safe_text(row.get('comment_id'), 200)
        user_id = safe_text(row.get('user_id') or row.get('sec_uid'), 200)
        if not video_id or (comment_id and not user_id):
            raise ValueError('每条记录需要 aweme_id；评论还需要 comment_id 和 user_id（或 sec_uid）。')
        if comment_id:
            data['comments'].append(dict(id=comment_id, video_id=video_id, user_id=user_id, content=safe_text(row.get('content'))))
        else:
            title = safe_text(row.get('title') or row.get('desc'))
            if not title:
                raise ValueError('视频记录需要 title 或 desc；未提供 comment_id 的记录按视频处理。')
            from .video_metadata import METRICS, observed_metric
            metrics={}
            for key in METRICS:
                metric=observed_metric(row.get(key),'import')
                if metric: metrics[key]=metric
            data['videos'].append(dict(id=video_id, title=title, url='', author=safe_text(row.get('nickname')), metrics=metrics))
        if user_id:
            data['users'].append(dict(id=user_id, nickname=safe_text(row.get('nickname')) or '未提供昵称', profile_url=''))
    return data
