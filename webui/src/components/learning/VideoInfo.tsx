import { useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { timeLabel, profileSafe } from './library'

export type Metric = { value: number; text?: string; approximate?: boolean; observed_at?: string; source?: string; time_basis?: string }
export type VideoInformation = { id: string; title?: string; author?: string; author_url?: string; source?: string; url?: string; search_rank?: number; metrics?: Record<string, Metric>; duration?: string; duration_seconds?: number; published_at?: string; published_text?: string; published_precision?: string; metadata_read_at?: string; metadata_status?: string; comment_task_id?: string }
export const videoMetrics = [['digg_count','点赞'],['comment_count','评论'],['collect_count','收藏'],['share_count','分享'],['play_count','播放'],['danmaku_count','弹幕']] as const
const sorts = [['search_rank','搜索顺序'], ...videoMetrics, ['published_at','发布时间'], ['duration_seconds','视频时长'], ['metadata_read_at','信息读取时间'], ['title','标题'], ['author','作者']]
function value(video: VideoInformation, field: string): number | string | undefined {
  if (field==='title'||field==='author') return video[field]?.trim() || undefined
  if (field==='published_at'||field==='metadata_read_at') { const date=Date.parse(video[field]||''); return Number.isFinite(date)?date:undefined }
  if (field==='search_rank') return video.search_rank
  const n=field==='duration_seconds'?video.duration_seconds:video.metrics?.[field]?.value
  return typeof n==='number'&&Number.isFinite(n)&&n>=0?n:undefined
}
export function sortVideos<T extends VideoInformation>(videos: T[], field: string, direction: string): T[] {
  return videos.map((v,index)=>({v,index})).sort((a,b)=>{
    const av=value(a.v,field), bv=value(b.v,field)
    if(av===undefined||bv===undefined) return av===bv?a.index-b.index:av===undefined?1:-1
    const cmp=typeof av==='string'&&typeof bv==='string'?av.localeCompare(bv,'zh-CN'):Number(av)-Number(bv)
    return (direction==='desc'?-cmp:cmp)||a.index-b.index
  }).map(x=>x.v)
}
export function useVideoSort<T extends VideoInformation>(videos: T[]) {
  const [field,setField]=useState('search_rank')
  const [direction,setDirection]=useState('asc')
  const known=videos.filter(v=>value(v,field)!==undefined).length
  const controls=<div className="video-sort-bar">
    <label>排序<select aria-label="视频排序方式" value={field} onChange={e=>{setField(e.target.value);setDirection(e.target.value==='search_rank'?'asc':'desc')}}>{sorts.map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label>
    <select aria-label="视频排序方向" value={direction} onChange={e=>setDirection(e.target.value)}><option value="desc">降序</option><option value="asc">升序</option></select>
    <span>当前列表 {videos.length} 条{field!=='search_rank'?` · ${known} 条有此指标 · 未提供排末尾`:''}</span>
  </div>
  return {ordered:sortVideos(videos,field,direction),controls}
}
export function VideoStats({video}: {video:VideoInformation}) {
  if(video.metadata_status==='unsupported_type') return <span className="video-stats">图文内容 · 不适用视频指标读取</span>
  if(video.metadata_status==='blocked') return <span className="video-stats">未完成 · 上一批页面超时，搜索信息已保留</span>
  return <span className="video-stats">{videoMetrics.map(([key,label])=>{const m=video.metrics?.[key];return <span key={key} title={m?`${label}：${m.text||m.value}；${m.approximate?'页面约数；':''}${m.time_basis==='task_created_at'?'原任务时间（历史文字补全）':m.time_basis==='unknown'?'采集时间未知':'采集于'} ${timeLabel(m.observed_at)}`:`${label}：页面未提供或尚未读取`}><span>{label}</span> <b>{m&&Number.isFinite(m.value)?(m.approximate?'≈':'')+m.value.toLocaleString('zh-CN'):'—'}</b></span>})}</span>
}
export function VideoInfo({video}: {video:VideoInformation}) {
  return <section className="video-information" aria-label="视频信息">
    <VideoStats video={video}/>
    <dl><dt>作者</dt><dd>{profileSafe(video.author_url)?<a href={video.author_url} target="_blank" rel="noreferrer">{video.author||'查看作者主页'}</a>:video.author||'未提供'}</dd>
      <dt>发布时间</dt><dd>{video.published_text||timeLabel(video.published_at)}{video.published_precision==='day'?'（日期精度）':''}</dd>
      <dt>时长</dt><dd>{video.duration||(video.duration_seconds!==undefined?`${video.duration_seconds} 秒`:'未提供')}</dd>
      <dt>视频编号</dt><dd>{video.id}</dd><dt>信息读取</dt><dd>{video.metadata_status==='unsupported_type'?'已跳过：打开后为图文页':video.metadata_status==='pending'?'等待读取':timeLabel(video.metadata_read_at)}</dd>
    </dl><p>— 表示未提供或尚未读取；≈ 为页面约数。指标是采集时的快照，播放量等可能不公开。</p>
  </section>
}
export function MetadataReadButton({taskId,videoIds,disabled=false,label='补充视频信息'}: {taskId:string;videoIds:string[];disabled?:boolean;label?:string}) {
  const lock=useRef(false);const [busy,setBusy]=useState(false);const [error,setError]=useState('')
  async function run(){
    if(lock.current)return;lock.current=true;setBusy(true);setError('')
    try{const r=await fetch(`/api/learning/tasks/${taskId}/video-metadata`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({video_ids:videoIds})});const data=await r.json();if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'请求失败，请核对任务记录。');window.location.hash='videos?task='+encodeURIComponent(data.id)}
    catch(e){setError(e instanceof Error?e.message:'请求失败，请查看任务记录。')}finally{lock.current=false;setBusy(false)}
  }
  return <span className="metadata-read"><Button size="sm" variant="outline" disabled={disabled||busy||!videoIds.length||videoIds.length>100} onClick={()=>void run()}>{busy?'正在创建任务…':label}</Button>{error&&<span role="alert">{error}</span>}</span>
}
