import { AlertCircle, ArrowRight, CheckCircle2, Loader2, Pause, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { DeleteRecord } from './DeleteRecord'
import { statusLabel } from './library'

export type SearchTask = { id: string; keyword: string; source: string; status: string; note: string; created_at: string }
export type SearchResult = { task: SearchTask; videos?: unknown[]; logs?: { id: number; message: string; created_at: string }[] }
const titles: Record<string, string> = {
  running: '正在读取视频', success: '本次读取完成', partial: '已保存部分结果',
  search_exhausted: '视频搜索页已到底', search_stalled: '等待新结果超时，已保留数据',
  waiting_login: '需要你完成登录', waiting_verification: '需要你完成验证',
  failed: '读取失败', cancelled: '已暂停读取', blocked: '读取受阻',
  needs_review: '需要核对页面', pending_layout: '需要核对页面',
}

export function SearchFeedback({ pending, keyword, result, error, stopping, stop, retry, view }: {
  pending: boolean; keyword: string; result?: SearchResult; error: boolean; stopping: boolean;
  stop: () => void; retry: () => void; view: () => void;
}) {
  const task = pending ? undefined : result?.task
  const running = task?.status === 'running'
  const count = pending ? 0 : result?.videos?.length || 0
  const complete = ['success','search_exhausted'].includes(task?.status || '')
  const tone = pending || running ? 'working' : complete ? 'done' : 'attention'
  const Icon = pending || running ? Loader2 : complete ? CheckCircle2 : AlertCircle
  return <section className={'search-feedback feedback-' + tone} aria-label="本次搜索进度">
    <div className="feedback-heading" role="status" aria-live="polite">
      <span className="feedback-symbol"><Icon size={21} className={pending || running ? 'learning-spinner' : ''} /></span>
      <div><h3>{pending ? '正在提交搜索请求' : task ? titles[task.status] || statusLabel[task.status] || task.status : '正在核对任务状态'}</h3><p>{task?.keyword || keyword}</p></div>
      {!pending && task && <span className="feedback-count">已保存 {count} / 100 个视频</span>}
    </div>
    {task && <><div className="feedback-track" role="progressbar" aria-label="视频收集数量（最多 100 个）" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.min(count, 100)}><span style={{ width: Math.min(count, 100) + '%' }} /></div><p className="feedback-note">{task.note}</p></>}
    {pending && <p className="feedback-note">请求已发出，正在等待本地服务确认。请勿重复点击。</p>}
    {error && !pending && <div role="alert" className="feedback-error"><span>状态更新中断，请先核对任务；不要重复提交。</span><Button size="sm" variant="outline" onClick={retry}><RefreshCw size={14} />重新核对状态</Button></div>}
    <div className="feedback-actions">
      {task && <Button size="sm" variant={task.status === 'success' ? 'default' : 'outline'} onClick={view}>查看本次搜索结果<ArrowRight size={15} /></Button>}
      {running && <Button size="sm" variant="outline" disabled={stopping} onClick={stop}>{stopping ? <Loader2 className="learning-spinner" /> : <Pause size={15} />}{stopping ? '正在暂停…' : '暂停读取'}</Button>}
      {task && !running && <DeleteRecord target={{ kind: 'tasks', source: task.source, id: task.id }} label="本次搜索任务" />}
      {running && <span className="feedback-hint">自动更新 · 可以随时查看已保存结果</span>}
      {task && !running && count < 100 && <span className="feedback-hint">最多收集 100 个；当前数量以实际保存为准。</span>}
    </div>
  </section>
}
