import type { VideoInformation } from './VideoInfo'
// Legacy task keywords remain intact in storage; presentation uses their video evidence.
export function taskLabel(task:{keyword?:string;source?:string;videos?:VideoInformation[]}, saved:VideoInformation[] = []) {
 const keyword=task.keyword||'已保存任务'
 const metadata=keyword.startsWith('视频信息：')
 const comment=keyword.startsWith('自动评论：')
 if(!metadata&&!comment)return keyword
 const id=keyword.match(/自动评论：[\s]*(\d+)/)?.[1]
 const own=task.videos||[]
 const videos=own.filter(v=>!id||v.id===id)
 const fallback=saved.filter(v=>(!task.source||v.source===task.source)&&(id?v.id===id:videos.some(x=>x.id===v.id)))
 const candidates=[...videos,...fallback]
 const video=candidates.find(v=>v.title?.trim()&&v.title.trim()!==v.id&&!/^(自动评论|视频信息)：/.test(v.title))
 const name=video?.title?.trim()||(id?'视频 '+id+'（标题未读取）':videos[0]?'视频 '+videos[0].id+'（标题未读取）':'视频标题未读取')
 return (metadata?'补充视频信息':'读取评论')+' · '+(metadata&&own.length>1?`${name} 等 ${own.length} 个视频`:name)
}
