import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { DeleteRecord, type DeleteTarget } from './DeleteRecord'
import { useQueryClient } from '@tanstack/react-query'
import { Download, FileDown, Loader2 } from 'lucide-react'
import { MetadataReadButton } from './VideoInfo'

export type SelectableRow = { target: DeleteTarget; label: string; disabled?: boolean }
const keyOf = (target: DeleteTarget) => JSON.stringify([target.kind,target.source,target.id])
export function useBatchSelection(rows: SelectableRow[], scope: string) {
  const [selection, setSelection] = useState<{ scope: string; keys: string[]; active: boolean }>({ scope, keys: [], active: false })
  const available = [...new Map(rows.filter(r => !r.disabled).map(r => [keyOf(r.target), r])).values()]
  const signature = JSON.stringify(available.map(r => keyOf(r.target)))
  const keys = selection.scope === scope ? selection.keys : []
  const selecting = selection.scope === scope && selection.active
  const chosen = available.filter(r => keys.includes(keyOf(r.target)))
  useEffect(() => {
    const valid: string[] = JSON.parse(signature)
    setSelection(old => {
      const next = old.scope === scope ? old.keys.filter(k => valid.includes(k)) : []
      return old.scope === scope && next.length === old.keys.length ? old : { scope, keys: next, active: old.scope === scope && old.active }
    })
  }, [scope, signature])
  return {
    available, chosen, selecting,
    start: () => setSelection({ scope, keys: [], active: true }),
    cancel: () => setSelection({ scope, keys: [], active: false }),
    has: (target: DeleteTarget) => chosen.some(r => keyOf(r.target) === keyOf(target)),
    toggle: (target: DeleteTarget) => {
      const key = keyOf(target)
      if (!selecting || !available.some(r => keyOf(r.target) === key)) return
      setSelection({ scope, keys: keys.includes(key) ? keys.filter(k => k !== key) : [...keys,key], active: true })
    },
    all: () => { if (selecting) setSelection({ scope, keys: chosen.length === available.length ? [] : available.map(r => keyOf(r.target)), active: true }) },
    clear: () => setSelection({ scope, keys: [], active: selecting }),
  }
}
export type BatchSelection = ReturnType<typeof useBatchSelection>
export function RowSelection({ selection, row }: { selection: BatchSelection; row: SelectableRow }) {
  if (!selection.selecting) return null
  return <input className="record-checkbox" type="checkbox" aria-label={'选择' + row.label} title={row.disabled ? '运行中，请先暂停任务' : '选择本地记录'} disabled={row.disabled} checked={selection.has(row.target)} onClick={e => e.stopPropagation()} onChange={() => selection.toggle(row.target)} />
}
export function BatchToolbar({ selection, scopeLabel = '当前页', exportTaskId = '' }: { selection: BatchSelection; scopeLabel?: string; exportTaskId?: string }) {
  const checkbox = useRef<HTMLInputElement>(null)
  const lock = useRef(false)
  const attempt = useRef({ keys: '', id: '' })
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const queries = useQueryClient()
  const { chosen, available } = selection
  async function perform(format: 'json' | 'csv' | 'video') {
    if (lock.current) return
    lock.current = true; setBusy(format); setError(''); setNotice('')
    const targets = chosen.map(r => r.target)
    try {
      const keys = JSON.stringify(targets)
      if (attempt.current.keys !== keys || !attempt.current.id) attempt.current = { keys, id: crypto.randomUUID().replace(/-/g,'') }
      const response = await fetch('/api/learning/' + (format === 'video' ? 'downloads' : 'export-selected'), { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(format === 'video' ? { targets, request_id:attempt.current.id } : { targets, format, task_id:exportTaskId }) })
      if (!response.ok) { const data = await response.json(); throw new Error(typeof data.detail === 'string' ? data.detail : '操作失败，请检查所选记录。') }
      if (format === 'video') {
        await response.json(); attempt.current.id = ''
        await queries.invalidateQueries({queryKey:['learning-downloads']})
        setNotice('下载请求已记录，请在上方“视频下载”中查看逐条结果。')
      } else {
        const url = URL.createObjectURL(await response.blob())
        const link = document.createElement('a'); link.href = url; link.download = `selected-${targets[0].kind}.${format}`
        document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 60000)
        setNotice(`已导出所选 ${targets.length} 条记录。`)
      }
    } catch(e) { setError(e instanceof Error ? e.message : '请求结果未确认，请重试核对同一次下载请求。') }
    finally { lock.current = false; setBusy('') }
  }
  useEffect(() => { if (checkbox.current) checkbox.current.indeterminate = chosen.length > 0 && chosen.length < available.length }, [chosen.length,available.length,selection.selecting])
  return <div className="batch-toolbar" role="group" aria-label={scopeLabel + '批量操作'}>
    {!selection.selecting ? <Button size="sm" variant="outline" disabled={!available.length} onClick={() => { setNotice(''); setError(''); selection.start() }}>选择</Button> : <>
    <label><input ref={checkbox} type="checkbox" checked={available.length > 0 && chosen.length === available.length} disabled={!available.length} onChange={selection.all} />全选{scopeLabel}</label>
    <span role="status">已选 {chosen.length} 条</span>
    <Button size="sm" variant="ghost" disabled={!!busy} onClick={() => { selection.cancel(); setNotice(''); setError('') }}>取消选择</Button>
    {!!exportTaskId && !!chosen.length && chosen.every(r=>r.target.kind==='videos'&&r.target.source==='live') && <MetadataReadButton taskId={exportTaskId} videoIds={chosen.map(r=>r.target.id)} disabled={!!busy}/>}
    {!!chosen.length && <div className="batch-actions"><Button size="sm" variant="outline" disabled={!!busy} onClick={() => void perform('csv')}><FileDown size={14} />导出 CSV</Button><Button size="sm" variant="outline" disabled={!!busy} onClick={() => void perform('json')}>导出 JSON</Button>{chosen.every(r => r.target.kind === 'videos') && <Button size="sm" variant="outline" disabled={!!busy || chosen.length > 100} onClick={() => void perform('video')}><Download size={14} />批量下载视频</Button>}<DeleteRecord disabled={!!busy} targets={chosen.map(r => r.target)} itemLabels={chosen.map(r => r.label)} label={`选中的 ${chosen.length} 条记录`} done={selection.clear} /></div>}
    </>}
    {!!busy && <span role="status" className="batch-message"><Loader2 size={14} className="animate-spin" />{busy === 'video' ? '正在创建下载任务…' : '正在生成所选数据文件…'}</span>}
    {!!notice && <p role="status" className="batch-message">{notice}</p>}
    {!!error && <p role="alert" className="batch-message">{error}</p>}
  </div>
}
