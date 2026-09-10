import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { VideoExplorer } from './VideoExplorer'
import { VideoStats, useVideoSort } from './VideoInfo'
import { CommentContent } from './ReplyThread'
import { BatchToolbar, RowSelection, useBatchSelection } from './BatchSelection'
import { DownloadPanel } from './DownloadPanel'
import { UserDrawer } from './UserDrawer'
import { readLocal, identity, timeLabel, viewNames, statusLabel, type Catalog, type View, type SavedUser, type SavedComment, type SavedVideo, type HistoryTask } from './library'

type Detail = { task: HistoryTask; videos: SavedVideo[]; comments: SavedComment[]; users: SavedUser[]; pagination?: object; screenshot_url?: string }
export function LibraryPanel({ view, selected, select }: { view: View; selected: string; select: (id: string) => void }) {
  const [saved] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem('learning-filters-' + view) || '{}') || {} }
    catch { return {} }
  })
  const [keyword, setKeyword] = useState<string>(() => typeof saved.keyword === 'string' ? saved.keyword : '')
  const [date, setDate] = useState<string>(() => typeof saved.date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(saved.date) && !Number.isNaN(Date.parse(saved.date)) ? saved.date : '')
  const [taskFilter, setTaskFilter] = useState<string>(() => typeof saved.taskFilter === 'string' ? saved.taskFilter : '')
  const [videoFilter, setVideoFilter] = useState<string>(() => typeof saved.videoFilter === 'string' ? saved.videoFilter : '')
  const [page, setPage] = useState<number>(() => Number.isInteger(saved.page) && saved.page >= 0 ? saved.page : 0)
  useEffect(() => { sessionStorage.setItem('learning-filters-' + view, JSON.stringify({ keyword, date, taskFilter, videoFilter, page })) }, [view, keyword, date, taskFilter, videoFilter, page])
  const [initialVideo, setInitialVideo] = useState('')
  const [drawer, setDrawer] = useState<{ user: SavedUser; videoId?: string }>()
  const [stopping, setStopping] = useState(false)
  const [stopError, setStopError] = useState('')
  const catalog = useQuery({ queryKey: ['learning-catalog'], queryFn: () => readLocal<Catalog>('catalog'), refetchInterval: 5000 })
  useEffect(() => {
    if (!catalog.data) return
    if (taskFilter && !catalog.data.tasks.some(t => t.id === taskFilter)) setTaskFilter('')
    if (videoFilter && !catalog.data.videos.some(v => identity(v) === videoFilter)) setVideoFilter('')
  }, [catalog.data, taskFilter, videoFilter])
  const bounds = date ? { start: new Date(date + 'T00:00:00').toISOString(), end: new Date(new Date(date + 'T00:00:00').getTime() + 86400000).toISOString() } : null
  const params = new URLSearchParams()
  if (keyword.trim()) params.set('keyword', keyword.trim())
  if (taskFilter) params.set('task_id', taskFilter)
  if (bounds) { params.set('start', bounds.start); params.set('end', bounds.end) }
  const filterQuery = params.toString()
  const filtered = useQuery({ queryKey: ['learning-catalog-filter', filterQuery], queryFn: () => readLocal<Catalog>('catalog?' + filterQuery), enabled: !!filterQuery, refetchInterval: 5000 })
  const current = filterQuery ? filtered : catalog
  const detail = useQuery({ queryKey: ['learning-task', selected], queryFn: () => readLocal<Detail>('tasks/' + selected), enabled: !!selected, refetchInterval: 1500 })
  const data = current.data
  const tasks = data?.tasks || []
  const videos = data?.videos || []
  const comments = (data?.comments || []).filter(c => !videoFilter || JSON.stringify([c.source, c.video_id]) === videoFilter)
  const userFor = (c: SavedComment) => data?.users.find(u => u.source === c.source && u.id === c.user_id) || { id: c.user_id, source: c.source, nickname: '未展示昵称' }
  const videoFor = (source: string, id: string) => videos.find(v => v.source === source && v.id === id)
  const groups = new Map<string, { video: SavedVideo; comments: SavedComment[]; users: SavedUser[] }>()
  for (const c of comments) {
    const v = videoFor(c.source, c.video_id) || { id: c.video_id || '未提供视频编号', source: c.source }
    const key = identity(v)
    if (!groups.has(key)) groups.set(key, { video: v, comments: [], users: [] })
    const g = groups.get(key)!
    g.comments.push(c)
    if (!g.users.some(u => u.id === c.user_id)) g.users.push(userFor(c))
  }
  const groupRows = [...groups.values()]
  for (const g of groupRows) g.comments.sort((a, b) => Number(!!a.parent_comment_id) - Number(!!b.parent_comment_id) || (a.comment_rank ?? a.reply_rank ?? 1000000) - (b.comment_rank ?? b.reply_rank ?? 1000000))
  const visibleTasks = tasks.filter(t => (view !== 'videos' || t.videos.length > 0) && (!videoFilter || t.videos.some(v => identity(v) === videoFilter)))
  const total = view === 'tasks' || view === 'videos' ? visibleTasks.length : groupRows.length
  const effectivePage = Math.min(page, Math.max(0, Math.ceil(total / 20) - 1))
  const pageSlice = <T,>(rows: T[]) => rows.slice(effectivePage * 20, (effectivePage + 1) * 20)
  const selectionScope = [view,filterQuery,videoFilter,effectivePage,selected].join('|')
  const taskSelection = useBatchSelection(pageSlice(visibleTasks).map(t => ({ target: { kind: 'tasks', source: t.source, id: t.id }, label: t.keyword, disabled: ['running','queued'].includes(t.status) })), selectionScope)
  function openTask(id: string, video = '') { setInitialVideo(video); select(id) }
  function openSavedVideo(video: SavedVideo) {
    const containingTasks = new Set((catalog.data?.comments || []).filter(c => c.source === video.source && c.video_id === video.id).flatMap(c => c.task_ids || []))
    const saved = (catalog.data?.tasks || []).find(t => t.source === video.source && containingTasks.has(t.id))
      || (catalog.data?.tasks || []).find(t => t.source === video.source && t.videos.some(v => v.id === video.id))
    if (saved) openTask(saved.id, video.id)
  }
  return <div key={selected || 'directory'} className="library-panel learning-detail-enter">
    <div className="flex items-center justify-between gap-3 mb-4"><h2 className="text-xl font-semibold">{selected ? '任务详情' : viewNames[view]}</h2>{selected && <Button size="sm" variant="outline" onClick={() => { select(''); setInitialVideo('') }}>返回{viewNames[view]}</Button>}</div>
    {!selected ? <>
      {view === 'videos' && <DownloadPanel />}
      <div className="library-filters">
        <label>搜索任务关键词<Input aria-label="搜索历史任务关键词" value={keyword} onChange={e => { setKeyword(e.target.value); setPage(0) }} placeholder="按任务名称或关键词查找" /></label>
        <label>任务执行日期<Input type="date" aria-label="任务执行日期" value={date} onChange={e => { setDate(e.target.value); setPage(0) }} /></label>
        <label>来源任务<select className="library-select" aria-label="筛选来源任务" value={taskFilter} onChange={e => { setTaskFilter(e.target.value); setVideoFilter(''); setPage(0) }}><option value="">全部任务</option>{catalog.data?.tasks.map(t => <option key={t.id} value={t.id}>{timeLabel(t.created_at)} · {t.keyword}</option>)}</select></label>
        {view !== 'tasks' && <label>视频<select className="library-select" aria-label="筛选视频" value={videoFilter} onChange={e => { setVideoFilter(e.target.value); setPage(0) }}><option value="">全部视频</option>{videos.map(v => <option key={identity(v)} value={identity(v)}>{v.title || v.id} · {v.source === 'live' ? '网页' : '导入'}</option>)}</select></label>}
      </div>
      {(keyword || date || taskFilter || videoFilter) && <Button variant="ghost" size="sm" onClick={() => { setKeyword(''); setDate(''); setTaskFilter(''); setVideoFilter(''); setPage(0) }}>清空筛选</Button>}
      {current.isError ? <div role="alert">数据目录读取失败。<Button size="sm" variant="outline" onClick={() => void current.refetch()}>重试</Button></div> : current.isLoading ? <p className="library-empty">正在加载历史记录…</p> : <>
        <p className="text-xs text-cyber-text-secondary my-4">{view === 'tasks' ? `共 ${visibleTasks.length} 个任务 · 按执行时间倒序` : view === 'videos' ? `共 ${videos.length} 个去重视频 · 按任务展示，同一视频可属于多个任务` : view === 'users' ? `${new Set(comments.map(c => JSON.stringify([c.source, c.user_id]))).size} 位去重评论用户 · 按视频分组，同一用户可出现在多个分组` : `${comments.length} 条已存评论（含回复） · 按视频分组`}。筛选任务时展示当次记录；未提供的发表时间不以读取时间替代。</p>
        {!total && <p className="library-empty">该范围暂无已保存记录。</p>}
        {view === 'tasks' && <BatchToolbar selection={taskSelection} />}
        {view === 'tasks' && <div className="history-task-list">{pageSlice(visibleTasks).map(t => <div key={t.id} className="record-with-delete"><RowSelection selection={taskSelection} row={{ target: { kind: 'tasks', source: t.source, id: t.id }, label: t.keyword, disabled: ['running','queued'].includes(t.status) }} /><button className="history-task" onClick={() => openTask(t.id)}><span><strong className="record-title" title={t.keyword}>{t.keyword}</strong><small>执行时间：{timeLabel(t.created_at)} · {t.source === 'live' ? '网页读取' : '本地导入'}</small></span><span className="task-counts">视频 {t.counts.videos} · 评论 {t.counts.comments} · 用户 {t.counts.users}<small>{statusLabel[t.status] || t.status} → 查看任务</small></span></button></div>)}</div>}
        {view === 'videos' && pageSlice(visibleTasks).map(t => <details key={t.id} className="library-group"><summary><strong className="record-title" title={t.keyword}>{t.keyword}</strong><span>{timeLabel(t.created_at)} · {t.counts.videos} 个视频 · {statusLabel[t.status] || t.status}</span></summary><Button variant="ghost" size="sm" onClick={() => openTask(t.id)}>查看任务详情</Button><VideoBatchList taskId={t.id} videos={t.videos.filter(v => !videoFilter || identity(v) === videoFilter)} scope={selectionScope + t.id} open={video => openTask(t.id,video.id)} /></details>)}
        {(view === 'users' || view === 'comments') && pageSlice(groupRows).map(group => <details className="library-group" key={identity(group.video)}><summary><strong className="record-title" title={group.video.title || group.video.id}>{group.video.title || group.video.id}</strong><span>{group.users.length} 位用户 · {group.comments.length} 条评论</span></summary><div className="p-3"><Button size="sm" variant="outline" onClick={() => openSavedVideo(group.video)}>打开视频评论详情</Button><p className="text-xs text-cyber-text-secondary mt-2">{[...new Set(group.comments.flatMap(c => c.task_ids || []))].map(id => tasks.find(t => t.id === id)).filter(Boolean).map(t => `${timeLabel(t!.created_at)} · ${t!.keyword}`).join('；') || '见任务详情中的执行时间'}</p></div><GroupContent key={view} scope={selectionScope} kind={view} group={group} showUser={user => setDrawer({ user, videoId: group.video.id })} /></details>)}
        {total > 20 && <div className="library-pager"><Button size="sm" variant="outline" disabled={!effectivePage} onClick={() => setPage(effectivePage - 1)}>上一页</Button><span>第 {effectivePage + 1} / {Math.ceil(total / 20)} 页</span><Button size="sm" variant="outline" disabled={(effectivePage + 1) * 20 >= total} onClick={() => setPage(effectivePage + 1)}>下一页</Button></div>}
      </>}
    </> : detail.isError ? <p role="alert">任务读取失败。<Button size="sm" variant="outline" onClick={() => void detail.refetch()}>重试</Button></p> : !detail.data ? <p>正在加载任务…</p> : <>
      <div className="history-detail-heading"><h3>{detail.data.task.keyword}</h3><p>执行时间：{timeLabel(detail.data.task.created_at)} · {statusLabel[detail.data.task.status] || detail.data.task.status} · {detail.data.task.source === 'live' ? '网页读取' : '本地导入'}</p><p>{detail.data.task.note}</p><a href={'/api/learning/export/' + selected} className="text-cyan-700 underline">导出结果</a>{detail.data.screenshot_url && <a className="text-cyan-700 underline ml-4" href={detail.data.screenshot_url} target="_blank" rel="noreferrer">查看暂停截图</a>}</div>
      {detail.data.task.status === 'running' && <Button size="sm" variant="outline" disabled={stopping} onClick={async () => {
        setStopping(true); setStopError('')
        try { const r = await fetch('/api/learning/tasks/' + selected + '/cancel', { method: 'POST' }); if (!r.ok) throw new Error('暂停失败，请核对任务状态。'); await detail.refetch() }
        catch (e) { setStopError(e instanceof Error ? e.message : '暂停失败') } finally { setStopping(false) }
      }}>暂停任务</Button>}
      {stopError && <p role="alert">{stopError}</p>}
      <VideoExplorer key={selected + initialVideo} taskId={selected} videos={detail.data.videos} searching={detail.data.task.status === 'running'} commentTaskId={detail.data.pagination || detail.data.comments.length ? selected : undefined} initialVideoId={initialVideo} source={detail.data.task.source} />
    </>}
    {drawer && <UserDrawer key={identity(drawer.user)} user={drawer.user} videoId={drawer.videoId} close={() => setDrawer(undefined)} />}
  </div>
}

function GroupContent({ kind, group, showUser, scope }: { scope: string; kind: 'users' | 'comments'; group: { comments: SavedComment[]; users: SavedUser[] }; showUser: (user: SavedUser) => void }) {
  const [page, setPage] = useState(0)
  const rows = kind === 'users' ? group.users : group.comments
  useEffect(() => { setPage(p => Math.min(p, Math.max(0, Math.ceil(rows.length / 100) - 1))) }, [rows.length])
  const selection = useBatchSelection(rows.slice(page * 100, (page + 1) * 100).map(row => ({ target: { kind, source: row.source, id: row.id }, label: 'nickname' in row ? row.nickname || row.id : 'content' in row ? (row.content || '图片评论').slice(0,40) : row.id })), scope + '|' + page)

  return <div className="p-3 space-y-3"><BatchToolbar selection={selection} scopeLabel="本组当前页" />{kind === 'users' ? group.users.slice(page * 100, (page + 1) * 100).map(user => <div className="record-with-delete" key={identity(user)}><RowSelection selection={selection} row={{ target: { kind: 'users', source: user.source, id: user.id }, label: user.nickname || user.id }} /><button className="history-task w-full" onClick={() => showUser(user)}><strong className="record-title" title={user.nickname || user.id}>{user.nickname || '未展示昵称'}</strong><span>{group.comments.filter(c => c.user_id === user.id).length} 条评论 → 查看用户</span></button></div>) : group.comments.slice(page * 100, (page + 1) * 100).map(c => { const user = group.users.find(u => u.id === c.user_id)!; return <article className="library-comment" key={identity(c)}><RowSelection selection={selection} row={{ target: { kind: 'comments', source: c.source, id: c.id }, label: (c.content || '图片评论').slice(0,40) }} /><button className="author-button" onClick={() => showUser(user)}>{user.nickname || '未展示昵称'}</button><CommentContent comment={c} /><p className="text-xs text-cyber-text-secondary">{c.parent_comment_id ? '回复' : '主评论'} · 发表时间：{timeLabel(c.create_time)}</p>{c.parent_comment_id && <p className="text-xs text-cyber-text-secondary">所属主评论：{group.comments.find(p => p.id === c.parent_comment_id)?.content || '此范围未保存主评论正文'}</p>}</article> })}<div className="library-pager"><Button size="sm" variant="outline" disabled={!page} onClick={() => setPage(p => p - 1)}>分组上一页</Button><span>第 {page + 1} 页 · 本页 {rows.slice(page * 100, (page + 1) * 100).length} 条</span><Button size="sm" variant="outline" disabled={(page + 1) * 100 >= rows.length} onClick={() => setPage(p => p + 1)}>分组下一页</Button></div></div>
}


function VideoBatchList({ videos, scope, open, taskId }: { taskId: string; videos: SavedVideo[]; scope: string; open: (video: SavedVideo) => void }) {
  const {ordered,controls}=useVideoSort(videos)
  const selection = useBatchSelection(videos.map(v => ({ target: { kind: 'videos', source: v.source, id: v.id }, label: v.title || v.id })), scope)
  return <>{controls}<BatchToolbar selection={selection} scopeLabel="本组视频" exportTaskId={taskId} /><div className="history-video-grid">{ordered.map((v) => <div key={identity(v)} className="video-with-delete">{selection.selecting && <div className="video-selection"><RowSelection selection={selection} row={{ target: { kind: 'videos', source: v.source, id: v.id }, label: v.title || v.id }} /></div>}<button className="history-video" onClick={() => open(v)}><span className="video-row-rank">第 {v.search_rank || videos.indexOf(v) + 1} 条</span><span className="video-row-body"><strong className="record-title" title={v.title || v.id}>{v.title || v.id}</strong><small className="record-meta" title={v.author}>{v.author || '未提供作者'} → 查看评论</small><VideoStats video={v}/></span></button></div>)}</div></>
}
