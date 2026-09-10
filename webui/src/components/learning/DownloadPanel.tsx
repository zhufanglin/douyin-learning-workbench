import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { readLocal, timeLabel } from './library'

type Item = {id:string; title:string; status:string; note:string; bytes?:number; attempted?:boolean}
type Job = {id:string;created_at:string; status:string; note:string; ready:boolean; cancel_requested:boolean; items:Item[]}
const labels:Record<string,string> = {queued:'等待中',running:'下载中',success:'已下载',unavailable:'不可下载',failed:'失败',paused:'验证受阻',cancelled:'已停止',interrupted:'已中断',blocked:'受阻',completed:'已处理'}
export function DownloadPanel() {
  const jobs = useQuery({queryKey:['learning-downloads'],queryFn:() => readLocal<{items:Job[]}>('downloads'),refetchInterval:1500})
  const [busy,setBusy] = useState('')
  const [error,setError] = useState('')
  async function cancel(id:string) {
    setBusy(id); setError('')
    try { const r = await fetch(`/api/learning/downloads/${id}/cancel`,{method:'POST'}); if (!r.ok) throw new Error('停止失败，请核对当前下载状态。'); await jobs.refetch() }
    catch(e) { setError(e instanceof Error ? e.message : '请求失败') } finally {setBusy('')}
  }
  return <section className="download-panel" aria-label="视频下载">
    <h3>视频下载</h3><p className="text-xs text-cyber-text-secondary">勾选下方视频后批量下载。使用页面正常下载入口；没有入口或需要验证时会显示原因。真实抖音下载效果待验证。</p>
    {jobs.isError && <p role="alert">下载记录读取失败。<Button size="sm" variant="ghost" onClick={() => void jobs.refetch()}>重试</Button></p>}
    {error && <p role="alert">{error}</p>}
    {(jobs.data?.items || []).map((job,index) => {
      const active = ['queued','running'].includes(job.status)
      const success = job.items.filter(i => i.status === 'success').length
      const processed = job.items.filter(i => i.attempted && !['queued','running'].includes(i.status)).length
      return <details className="download-job" key={job.id} open={index === 0 ? true : undefined}>
        <summary>{timeLabel(job.created_at)} · {labels[job.status] || job.status} · 已下载 {success} / {job.items.length} 条</summary>
        <progress max={job.items.length} value={processed} aria-label="下载处理进度" />
        <p role="status">{job.note}</p><div className="batch-actions">{active && <Button size="sm" variant="outline" disabled={busy === job.id || job.cancel_requested} onClick={() => void cancel(job.id)}>{job.cancel_requested ? '正在停止…' : '停止下载'}</Button>}{job.ready && <a className="download-link" href={`/api/learning/downloads/${job.id}/file`}>保存视频 ZIP（{success} 条）</a>}</div>
        <ul>{job.items.map((item,i) => <li key={i}><strong>{item.title}</strong><span>{labels[item.status] || item.status} · {item.note}</span>{/^\d{5,30}$/.test(item.id) && <a href={'https://www.douyin.com/video/'+item.id} target="_blank" rel="noreferrer">打开原视频</a>}</li>)}</ul>
      </details>
    })}
  </section>
}
