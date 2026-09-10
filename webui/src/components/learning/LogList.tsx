import { BatchToolbar, RowSelection, useBatchSelection } from './BatchSelection'
import { CompactText } from './CompactText'

export function LogList({ logs, runningIds }: { logs: Record<string, unknown>[]; runningIds: string[] }) {
  const rows = logs.map(log => ({ target: { kind: 'logs' as const, source: String(log.source || 'live'), id: String(log.id) }, label: '日志：' + String(log.message).slice(0,30), disabled: runningIds.includes(String(log.task_id)) }))
  const selection = useBatchSelection(rows, 'logs')
  return <><BatchToolbar selection={selection} /><div className="space-y-3 text-xs font-mono" aria-label="执行日志">{logs.length ? logs.map((log,index) => <div key={String(log.id)} className="log-select-row border-b border-cyber-border-subtle pb-2"><RowSelection selection={selection} row={rows[index]} /><div><span className="text-cyber-text-secondary mr-2">{new Date(String(log.created_at)).toLocaleString('zh-CN')}</span><CompactText text={String(log.message)} /></div></div>) : <p className="text-cyber-text-secondary">运行后在这里查看过程。</p>}</div></>
}
