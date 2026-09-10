import { useRef, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useQueryClient } from '@tanstack/react-query'
import { Loader2, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'

export type DeleteTarget = { kind: 'tasks' | 'videos' | 'users' | 'comments' | 'logs'; source: string; id: string }
type Preview = { token: string; counts: Record<string, number>; affected_tasks: number; selected_count?: number }
const descriptions = {
  tasks: '删除该任务、日志及独有数据；其他任务共用的数据保留。',
  videos: '从所有本地任务中删除这个视频、关联评论及不再被引用的用户。',
  users: '从所有本地任务中删除这个用户、其评论及关联回复。',
  comments: '从所有本地任务中删除这条评论；如果有已保存回复，一并删除。',
  logs: '只删除这条本地日志，保留任务及采集结果。',
}
export function DeleteRecord({ target, targets, itemLabels, label, disabled, done }: { target?: DeleteTarget; targets?: DeleteTarget[]; itemLabels?: string[]; label: string; disabled?: boolean; done?: () => void }) {
  const targetList = targets || (target ? [target] : [])
  const checked = useRef<DeleteTarget[]>([])
  const [checkedLabels, setCheckedLabels] = useState<string[]>([])
  const kind = checked.current[0]?.kind || targetList[0]?.kind || 'tasks'
  const batch = !!targets
  const queries = useQueryClient()
  const [open, setOpen] = useState(false)
  const [preview, setPreview] = useState<Preview>()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const lock = useRef(false)
  const trigger = useRef<HTMLButtonElement>(null)
  async function request(path: string, body: object) {
    const response = await fetch('/api/learning/deletion/' + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    const data = await response.json()
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '请求失败，请重新核对。')
    return data
  }
  async function check() {
    if (lock.current) return
    lock.current = true; setBusy(true); setError(''); setPreview(undefined)
    checked.current = [...targetList]
    setCheckedLabels(itemLabels || [])
    try { setPreview(await request(batch ? 'batch-preview' : 'preview', batch ? { targets: checked.current } : checked.current[0])) }
    catch(e) { setError(e instanceof Error ? e.message : '无法核对删除范围。') }
    finally { lock.current = false; setBusy(false) }
  }
  async function commit() {
    if (lock.current || !preview) return
    lock.current = true; setBusy(true); setError('')
    try {
      const result = await request(batch ? 'batch-commit' : 'commit', { ...(batch ? { targets: checked.current } : checked.current[0]), token: preview.token })
      for (const id of result.deleted_task_ids || []) {
        for (const key of Object.keys(localStorage)) {
          if (key.startsWith('learning-video-cache-')) {
            try { const cache = JSON.parse(localStorage.getItem(key) || '{}'); for (const video of Object.keys(cache)) if (cache[video] === id) delete cache[video]; localStorage.setItem(key, JSON.stringify(cache)) } catch { localStorage.removeItem(key) }
          }
        }
        localStorage.removeItem('learning-video-cache-' + id)
        localStorage.removeItem('learning-picked-video-' + id)
        if (sessionStorage.getItem('learning-search-task') === id) sessionStorage.removeItem('learning-search-task')
      }
      window.dispatchEvent(new CustomEvent('learning-records-deleted', { detail: result }))
      setOpen(false); done?.()
      await Promise.all(['learning-state','learning-catalog','learning-catalog-filter','learning-task'].map(key => queries.invalidateQueries({ queryKey: [key] })))
    } catch(e) {
      setPreview(undefined)
      setError((e instanceof Error ? e.message : '删除结果未确认。') + ' 请重新核对列表和删除范围，不要重复提交。')
    } finally { lock.current = false; setBusy(false) }
  }
  return <Dialog.Root open={open} onOpenChange={value => { if (!busy) setOpen(value) }}>
    <Button ref={trigger} type="button" size="sm" variant="ghost" className="delete-record" aria-label={batch ? '批量删除所选记录' : '删除' + label} disabled={disabled || !targetList.length} onClick={e => { e.stopPropagation(); setOpen(true); void check() }}><Trash2 size={15} /><span>{batch ? '批量删除' : '删除'}</span></Button>
    <Dialog.Portal><Dialog.Overlay className="delete-overlay" /><Dialog.Content className="learning-shell delete-dialog" onCloseAutoFocus={e => { e.preventDefault(); trigger.current?.focus() }}>
      <Dialog.Title className="text-lg font-semibold">删除本地记录</Dialog.Title>
      <Dialog.Description className="text-sm text-cyber-text-secondary">{batch ? descriptions[kind].replace('该任务', '所选任务').replace('这个视频', '所选视频').replace('这个用户', '所选用户').replace('这条评论', '所选评论').replace('这条本地日志', '所选本地日志') : descriptions[kind]}不会删除抖音平台上的内容。此操作无法撤销。</Dialog.Description>
      <p className="delete-label">{batch && preview ? `已选 ${preview.selected_count} 条记录` : label}</p>{batch && <ul className="delete-selected-list">{checkedLabels.map((text,i) => <li key={i}>{text}</li>)}</ul>}
      {busy && !preview && <p role="status">正在核对删除范围…</p>}
      {preview && <div className="delete-impact"><strong>将删除</strong><p>{Object.entries({ tasks:'任务', videos:'视频', users:'用户', comments:'评论', logs:'日志' }).map(([key,name]) => `${name} ${preview.counts[key] || 0}`).join(' · ')}</p><p>涉及 {preview.affected_tasks} 个任务。{kind !== 'logs' && '受影响的旧评论批次将停止续读，可新建任务重新读取。'}</p></div>}
      {error && <p role="alert" className="text-red-600 text-sm">{error}</p>}
      <div className="flex flex-wrap justify-end gap-2">
        <Dialog.Close asChild><Button variant="outline" disabled={busy} autoFocus>取消</Button></Dialog.Close>
        {!preview && !busy && <Button variant="outline" onClick={() => void check()}>重新核对范围</Button>}
        <Button variant="destructive" disabled={busy || !preview} onClick={() => void commit()}>{busy && preview ? <Loader2 className="learning-spinner" /> : <Trash2 size={15} />}{busy && preview ? '正在删除…' : '确认删除'}</Button>
      </div>
    </Dialog.Content></Dialog.Portal>
  </Dialog.Root>
}
