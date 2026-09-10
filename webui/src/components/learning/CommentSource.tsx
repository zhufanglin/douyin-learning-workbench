import {taskLabel} from './taskLabel'
import { type Catalog, type SavedComment, timeLabel } from './library'
export function CommentSource({comment,data,business}:{comment:SavedComment;data:Catalog;business:string}) {
 const tasks=data.tasks.filter(t=>comment.task_ids?.includes(t.id)&&t.source===comment.source)
 const candidates=[...data.videos.filter(v=>v.source===comment.source&&v.id===comment.video_id),...tasks.flatMap(t=>t.videos.filter(v=>v.id===comment.video_id))]
 const video=candidates.find(v=>v.title?.trim()&&v.title.trim()!==comment.video_id)||candidates[0]
 const title=video?.title?.trim()||'标题未读取 · '+(comment.video_id||'视频编号未提供')
 return <div className="text-xs min-w-0 space-y-1">
 <div className="flex min-w-0 gap-1"><span className="shrink-0">来源视频：</span>{/^\d+$/.test(comment.video_id)?<a className="underline truncate min-w-0" title={title} target="_blank" rel="noreferrer" href={'https://www.douyin.com/video/'+comment.video_id}>{title}</a>:<span className="truncate" title={title}>{title}</span>}</div>
 {video?.author&&<p className="truncate text-cyber-text-secondary" title={video.author}>视频作者：{video.author}</p>}
 <details><summary>采集记录</summary><div className="space-y-1 mt-1">{tasks.filter(t=>!business||t.business_profile?.id===business).map(t=><a key={t.id} className="block underline" href={'#tasks?task='+encodeURIComponent(t.id)}>{taskLabel(t,data.videos)} · {timeLabel(t.created_at)}{t.business_profile?' · '+t.business_profile.name:''}</a>)}</div></details>
 </div>
}
