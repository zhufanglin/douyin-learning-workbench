"""One search task, with resumable first-comment batches for each video."""
def collect_search_comments(page,store,task,data):
    from .browser import check_page,collect_comments,current_video_id,PagePaused,BrowserTimeout
    from .video_metadata import read_video_detail
    total=len(data['videos'])
    for index,video in enumerate(data['videos']):
        if store.get_task(task['id'])['status']!='running':return
        child=store.create_task('自动评论：'+video['id'],'live')
        video['comment_task_id']=child['id']
        batch={'videos':[dict(video)],'comments':[],'users':[],
               'pagination':dict(video_id=video['id'],revision=0,target=100,exhausted=False,scope='top_level_text')}
        def cancelled():return store.get_task(task['id'])['status']!='running' or store.get_task(child['id'])['status']!='running'
        def progress():
            store.finish(child['id'],batch,'running',f"自动读取首批评论：已保存 {len(batch['comments'])}/100 条。")
            for kind in ('comments','users'):
                merged={item['id']:item for item in data[kind]};merged.update({item['id']:item for item in batch[kind]});data[kind]=list(merged.values())
            store.finish(task['id'],data,'running',f"已找到 {total} 个视频；正在读取第 {index+1}/{total} 个视频评论，当前 {len(batch['comments'])}/100 条，累计 {len(data['comments'])} 条。")
        progress()
        try:
            page.goto('https://www.douyin.com/video/'+video['id'],wait_until='domcontentloaded',timeout=30000)
            check_page(page)
            if '/note/'+video['id'] in page.url:
                video.update(content_type='note',metadata_status='unsupported_type')
                batch['videos']=[dict(video)]
                store.finish(child['id'],batch,'partial','打开后为图文，已跳过自动视频评论读取。')
                continue
            if current_video_id(page.url)!=video['id']:raise PagePaused('needs_review','页面对象不符，自动评论读取已暂停。')
            # Let the ordinary page mount; collection handles subsequent loading itself.
            page.wait_for_timeout(2000)
            check_page(page)
            if cancelled():store.cancel(child['id']);return
            try:
                info=read_video_detail(page,video['id'])
                info['metrics']={**video.get('metrics',{}),**info.get('metrics',{})};video.update(info)
                batch['videos']=[dict(video)]
            except PagePaused as exc:
                if exc.status!='pending_layout':raise
            collect_comments(page,video['id'],batch,progress,cancelled)
            if cancelled():store.cancel(child['id']);return
            progress()
            store.finish(child['id'],batch,'success','首批主评论已保存；可进入视频继续下一批100条。')
        except PagePaused as exc:
            video['comment_status']=exc.status
            progress();store.finish(child['id'],batch,exc.status,str(exc))
            if exc.status=='partial':continue
            raise
        except BrowserTimeout:
            progress();store.finish(child['id'],batch,'failed','页面超时，已停止自动评论读取。');raise
        except Exception:
            progress();store.finish(child['id'],batch,'failed','自动评论读取中断，已保留结果。');raise
    store.finish(task['id'],data,'running',f"自动评论阶段完成：{total} 个结果，已保存 {len(data['comments'])} 条评论。")
