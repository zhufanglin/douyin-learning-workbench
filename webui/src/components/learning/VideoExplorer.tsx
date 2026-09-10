import {taskLabel} from './taskLabel'
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { ReplyThread, CommentContent, type Comment } from './ReplyThread'
import { UserDrawer } from './UserDrawer'
import { readLocal, timeLabel, type Catalog, type SavedUser } from './library'
import { VideoStats, VideoInfo, MetadataReadButton, useVideoSort, type VideoInformation } from './VideoInfo'

type Video = VideoInformation
type Detail = {
  task: { id: string; status: string; note: string; keyword?: string; created_at?: string }
  comments: Comment[]
  users: { id: string; nickname: string; profile_url: string }[]
  videos?: Video[]
  pagination?: { revision: number; target: number; exhausted: boolean; active_reply?: string; replies?: Record<string, { target: number; exhausted: boolean; end_state?: string; unsupported_count?: number; reader_version?: number; image_placeholder_count?: number }> } | null
}

async function request<T>(path: string, post = false, body?: object): Promise<T> {
  const response = await fetch('/api/learning/' + path, post ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined } : undefined)
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '读取失败，请查看任务日志。')
  return data
}

export function VideoExplorer({ taskId, videos, searching, commentTaskId, initialVideoId, source = 'live' }: { taskId: string; videos: Video[]; searching: boolean; commentTaskId?: string; initialVideoId?: string; source?: string }) {
  const cacheKey = 'learning-video-cache-' + taskId
  const pickedKey = 'learning-picked-video-' + taskId
  const [cache, setCache] = useState<Record<string, string>>(() => {
    try { const saved = JSON.parse(localStorage.getItem(cacheKey) || '{}'); return saved && typeof saved === 'object' ? saved : {} }
    catch { return {} }
  })
  const [picked, setPicked] = useState<Video | undefined>(() => videos.find(v => v.id === initialVideoId) || (commentTaskId && videos.length === 1 ? videos[0] : videos.find(v => v.id === localStorage.getItem(pickedKey))))
  const [detailId, setDetailId] = useState(() => commentTaskId || (picked ? picked.comment_task_id || cache[picked.id] || '' : ''))
  useEffect(() => { localStorage.setItem(cacheKey, JSON.stringify(cache)) }, [cache, cacheKey])
  useEffect(() => { if (picked) localStorage.setItem(pickedKey, picked.id) }, [picked, pickedKey])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [page, setPage] = useState(0)
  const [drawer, setDrawer] = useState<SavedUser>()
  const {ordered,controls}=useVideoSort(videos)
  const catalog = useQuery({ queryKey: ['learning-catalog'], queryFn: () => readLocal<Catalog>('catalog'), staleTime: 3000 })
  useEffect(() => {
    if (!picked || detailId || busy || !catalog.data) return
    const containingTasks = new Set(catalog.data.comments.filter(c => c.source === source && c.video_id === picked.id).flatMap(c => c.task_ids || []))
    const saved = catalog.data.tasks.find(t => t.source === source && containingTasks.has(t.id))
    if (saved) setDetailId(saved.id)
    else if (source === 'import') setDetailId(taskId)
  }, [picked, detailId, busy, catalog.data, source, taskId])
  const detail = useQuery({ queryKey: ['video-detail', detailId], queryFn: () => request<Detail>('tasks/' + detailId), enabled: !!detailId, refetchInterval: 1500 })
  const reading = busy || (!!detailId && !detail.data) || detail.data?.task.status === 'running'
  const videoComments = detail.data?.comments.filter(c => !('video_id' in c) || c.video_id === picked?.id) || []
  const videoUsers = detail.data?.users.filter(u => videoComments.some(c => c.user_id === u.id)) || []
  const mainComments = videoComments.filter(c => !c.parent_comment_id)
  const activeReply = detail.data?.pagination?.active_reply
  const progressCount = activeReply ? detail.data?.comments.filter(c => c.parent_comment_id === activeReply).length || 0 : mainComments.length
  const progressTarget = activeReply ? detail.data?.pagination?.replies?.[activeReply]?.target || 100 : detail.data?.pagination?.target || 100

  async function readReply(parentId: string) {
    if (!detail.data?.pagination || reading) return
    setBusy(true); setError('')
    try {
      await request(`tasks/${detailId}/comments/${encodeURIComponent(parentId)}/replies`, true, { revision: detail.data.pagination.revision })
      await detail.refetch()
    } catch (e) { setError(e instanceof Error ? e.message : '读取回复失败'); await detail.refetch() }
    finally { setBusy(false) }
  }

  async function choose(video: Video, fresh = false) {
    setPicked(video); setError(''); setPage(0)
    if (commentTaskId) { setDetailId(commentTaskId); return }
    if(video.comment_task_id && !fresh) { setDetailId(video.comment_task_id); return }
    if (cache[video.id] && !fresh) { setDetailId(cache[video.id]); return }
    if (!fresh) { setDetailId(''); return }
    setBusy(true); setDetailId('')
    try {
      const task = await request<{ id: string }>(`tasks/${taskId}/videos/${encodeURIComponent(video.id)}/comments`, true)
      setDetailId(task.id); setCache(previous => ({ ...previous, [video.id]: task.id }))
    } catch (e) { setError(e instanceof Error ? e.message : '读取失败') }
    finally { setBusy(false) }
  }

  async function nextBatch() {
    if (!detail.data?.pagination || reading) return
    setBusy(true); setError('')
    try {
      await request(`tasks/${detailId}/comments/next`, true, { revision: detail.data.pagination.revision })
      setPage(Math.floor(mainComments.length / 100))
      await detail.refetch()
    } catch (e) { setError(e instanceof Error ? e.message : '读取失败'); await detail.refetch() }
    finally { setBusy(false) }
  }

  return <div className="space-y-3">
    {!picked && <><p className="text-sm text-cyber-text-secondary">已找到 {videos.length} 个视频。{searching ? '正在收集，请稍候再选视频。' : '点击视频查看信息与评论。'}</p>{controls}{source==='live'&&<MetadataReadButton taskId={taskId} videoIds={videos.map(v=>v.id)} disabled={searching} label="补充本任务视频信息"/>}</>}
    {picked && <Button size="sm" variant="outline" onClick={() => { setPicked(undefined); setDetailId(''); localStorage.removeItem(pickedKey) }}>返回视频列表</Button>}
    <div className="space-y-4">
      {!picked && <div aria-label="视频列表" className="history-video-grid max-h-[620px] overflow-y-auto">
        {ordered.map((video) => <button key={video.id} disabled={searching || reading} onClick={() => void choose(video)} className="text-left w-full p-3 border rounded-lg disabled:opacity-60 border-cyber-border-subtle hover:bg-cyber-bg-secondary">
          <span className="video-row-rank">第 {video.search_rank || videos.indexOf(video) + 1} 条</span><span className="video-row-body"><span className="record-title" title={video.title || video.id}>{video.title || '视频 ' + video.id}</span>{video.author && <span className="record-meta" title={video.author}>{video.author}</span>}<VideoStats video={video}/></span>
        </button>)}
        {!videos.length && <p className="text-sm text-cyber-text-secondary py-6">等待视频结果。</p>}
      </div>}
      {picked && <div aria-label="所选视频评论" className="border border-cyber-border-subtle rounded-lg p-4 min-w-0">
        {!picked ? <p className="text-sm text-cyber-text-secondary py-8">先从视频列表选择一个视频。</p> : <>
          <h3 className="font-medium text-sm break-words">{picked.title || picked.id}</h3>
          <VideoInfo video={detail.data?.videos?.find(v=>v.id===picked.id)||videos.find(v=>v.id===picked.id)||picked}/>
          {source==='live'&&<MetadataReadButton taskId={taskId} videoIds={[picked.id]} disabled={searching||reading}/>}
          {source === 'live' && /^\d+$/.test(picked.id) && <a href={'https://www.douyin.com/video/' + picked.id} target="_blank" rel="noreferrer" className="text-sm text-cyan-700 underline">打开抖音原视频</a>}
          {detail.data && <p className="text-xs text-cyber-text-secondary mt-2">评论来源：{taskLabel({...detail.data.task,videos:detail.data.videos})} · 读取任务时间：{timeLabel(detail.data.task.created_at)}{detailId !== taskId ? '（此视频的独立读取记录）' : ''}</p>}
          {(error || detail.isError) && <p role="alert" className="text-red-600 text-sm mt-2">{error || '读取结果失败'}</p>}
          <p role="status" className="text-xs text-cyber-text-secondary my-3">{busy ? '正在提交读取请求…' : detail.data?.task.note || (detailId || catalog.isLoading ? '正在加载已保存记录…' : '此视频尚无已保存评论。')}</p>
          {!detailId && catalog.isError && <p role="alert" className="text-sm text-red-600">无法核对已保存评论，请先重试。<Button size="sm" variant="outline" onClick={() => void catalog.refetch()}>核对已有记录</Button></p>}
          {!detailId && !busy && catalog.isSuccess && <Button disabled={searching} onClick={() => void choose(picked, true)}>读取此视频评论</Button>}
          {detail.data && <><p className="text-sm mb-3">本视频：{videoComments.length} 条评论 · {videoUsers.length} 位用户</p>
            <p className="text-xs text-cyber-text-secondary mb-2">主评论 {mainComments.length} · 回复 {videoComments.length - mainComments.length} · 每页 100 条主评论</p>
            <a className="text-sm text-cyan-700 underline inline-block mb-3" href={`/api/learning/export/${detailId}`}>导出本视频评论（含已存回复）</a>
            {reading && <div className="mb-3"><p className="text-xs">本批{activeReply ? '回复' : '主评论'}累计目标：{progressCount}/{progressTarget}，不是平台总数</p><progress className="w-full" aria-label="本批读取进度" max={progressTarget} value={Math.min(progressCount, progressTarget)} /></div>}
            <div className="flex flex-wrap items-center gap-2 mb-3">
              {detail.data.task.status === 'running' && <Button size="sm" variant="outline" disabled={busy} onClick={() => {
                void request(`tasks/${detailId}/cancel`, true).then(() => detail.refetch()).catch(e => setError(e.message))
              }}>暂停读取</Button>}
              <Button size="sm" variant="outline" disabled={page === 0} onClick={() => setPage(p => p - 1)}>上一页</Button>
              <span className="text-xs">第 {page + 1} 页 · 本页 {mainComments.slice(page * 100, (page + 1) * 100).length} 条</span>
              {(page + 1) * 100 < mainComments.length ? <Button size="sm" variant="outline" onClick={() => setPage(p => p + 1)}>下一页</Button> : detail.data.pagination ?
                <Button size="sm" variant="outline" disabled={reading || detail.data.pagination.exhausted} onClick={() => void nextBatch()}>{reading ? '正在读取…' : detail.data.pagination.exhausted ? '主评论已到底' : detail.data.task.status === 'success' ? '下一批 100 条' : '处理页面后继续本批'}</Button> :
                ['pending_layout', 'waiting_login', 'waiting_verification', 'failed', 'blocked', 'partial'].includes(detail.data.task.status) && <Button size="sm" variant="outline" disabled={reading} onClick={() => void choose(picked, true)}>重新读取所选视频</Button>}
            </div>
            <div key={page} className="max-h-[440px] overflow-y-auto space-y-3">{mainComments.slice(page * 100, (page + 1) * 100).map(comment => {
              const user = detail.data.users.find(u => u.id === comment.user_id)
              return <article key={comment.id} className="border-t border-cyber-border-subtle pt-3">
                <button className="author-button" onClick={() => setDrawer({ id: comment.user_id, nickname: user?.nickname, profile_url: user?.profile_url, source })}>{user?.nickname || '未展示昵称'}</button><div className="text-sm mt-1"><CommentContent comment={comment} /></div>
                <p className="text-xs text-cyber-text-secondary">发表时间：{timeLabel('create_time' in comment ? comment.create_time as string : undefined)}</p>
                {user?.profile_url && /^https:\/\/www\.douyin\.com\/user\/[A-Za-z0-9_.=-]+$/.test(user.profile_url) && <a className="text-xs text-cyan-700 underline" href={user.profile_url} target="_blank" rel="noreferrer">查看评论用户主页</a>}
                <details className="text-xs text-cyber-text-secondary mt-1"><summary>用户标识</summary><p className="break-all">{comment.user_id}</p></details>
                <ReplyThread replies={detail.data.comments.filter(c => c.parent_comment_id === comment.id)} users={detail.data.users}
                  showUser={user => setDrawer({ ...user, source })}
                  endState={detail.data.pagination?.replies?.[comment.id]?.end_state} unsupportedCount={detail.data.pagination?.replies?.[comment.id]?.unsupported_count}
                  readerVersion={detail.data.pagination?.replies?.[comment.id]?.reader_version}
                  imagePlaceholderCount={detail.data.pagination?.replies?.[comment.id]?.image_placeholder_count}
                  enabled={!!detail.data.pagination} reading={reading} exhausted={!!detail.data.pagination?.replies?.[comment.id]?.exhausted} load={() => void readReply(comment.id)} />
              </article>
            })}</div></>}
        </>}
      </div>}
    </div>
    {drawer && <UserDrawer user={drawer} videoId={picked?.id} close={() => setDrawer(undefined)} />}
  </div>
}
