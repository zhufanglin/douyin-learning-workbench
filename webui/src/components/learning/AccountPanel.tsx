import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

type Intent = { id: string; sender: string; target: string; kind: 'follow'|'message'; message: string; status: string; note: string; confirm_token: string; expires_at: number; updated_at: string }
const names: Record<string,string> = { checking:'正在核对', ready:'待你确认', executing:'单次执行中', verifying:'只读核对中', success:'页面已确认', already_done:'已存在，不重复执行', uncertain:'结果不确定', blocked:'受阻，未执行', waiting_login:'等待本人登录', waiting_verification:'等待本人验证' }
async function api<T>(path: string, body?: object): Promise<T> {
  const r=await fetch('/api/learning/account-actions'+path,body===undefined?undefined:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
  const data=await r.json()
  if(!r.ok) throw new Error(typeof data.detail==='string'?data.detail:'请求未完成，请核对输入与操作记录。')
  return data
}
export function AccountPanel() {
  const queries=useQueryClient()
  const [sender,setSender]=useState(()=>sessionStorage.getItem('learning-action-sender')||'')
  const [target,setTarget]=useState(()=>sessionStorage.getItem('learning-action-target')||'')
  const [kind,setKind]=useState<'follow'|'message'>('follow')
  const [message,setMessage]=useState('')
  const [authorized,setAuthorized]=useState(false)
  const [confirmed,setConfirmed]=useState(false)
  const [active,setActive]=useState(()=>sessionStorage.getItem('learning-action-active')||'')
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const [browserNote,setBrowserNote]=useState('')
  const lock=useRef(false)
  const list=useQuery({queryKey:['account-actions'],queryFn:()=>api<{items:Intent[]}>(''),refetchInterval:1500,retry:false})
  const detail=useQuery({queryKey:['account-action',active],queryFn:()=>api<Intent>('/'+active),enabled:!!active,refetchInterval:1000,retry:false})
  const action=detail.data
  const running=action && ['checking','executing','verifying'].includes(action.status)
  useEffect(()=>{sessionStorage.setItem('learning-action-sender',sender)},[sender])
  useEffect(()=>{if(active)sessionStorage.setItem('learning-action-active',active)},[active])
  useEffect(()=>{setConfirmed(false)},[active,action?.confirm_token])
  async function run(path: string, body: object) {
    if(lock.current)return
    lock.current=true;setBusy(true);setError('');setConfirmed(false)
    try {
      const result=await api<Intent>(path,body)
      queries.setQueryData(['account-action',result.id],result);setActive(result.id)
      await queries.invalidateQueries({queryKey:['account-actions']})
    } catch(e) {setError((e instanceof Error?e.message:'请求结果未确认。')+' 请先查看操作记录，不要重复提交。');void list.refetch();void detail.refetch()}
    finally {lock.current=false;setBusy(false)}
  }
  async function openBrowser() {
    if(lock.current)return
    lock.current=true;setBusy(true);setError('');setBrowserNote('正在打开独立抖音浏览器…')
    try { const result=await api<{note:string}>('/browser/open',{});setBrowserNote(result.note) }
    catch(e) {setBrowserNote('');setError(e instanceof Error?e.message:'浏览器未打开。')}
    finally {lock.current=false;setBusy(false)}
  }
  async function inspectBrowser() {
    if(lock.current)return
    lock.current=true;setBusy(true);setError('');setBrowserNote('正在读取工具浏览器的本人主页…')
    try {
      const result=await api<{sender:string;note:string}>('/browser/inspect',{})
      setBrowserNote(result.note)
      if(result.sender){setSender(result.sender);setAuthorized(false)}
    } catch(e) {setBrowserNote('');setError(e instanceof Error?e.message:'账号核对失败。')}
    finally {lock.current=false;setBusy(false)}
  }
  return <div className="account-workspace space-y-5">
    <p className="account-status-note"><ShieldCheck size={18}/>每次只操作一个获准对象。执行前核对账号、对象和内容；结果不确定时只核对，不重复执行。</p>
    <section className="account-form-panel space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-semibold">1. 指定本次测试</h2><Button variant="outline" disabled={busy||!!running} onClick={()=>void openBrowser()}>打开浏览器登录</Button></div>
      {browserNote&&<p role="status" className="text-sm">{browserNote}</p>}
      <Button variant="outline" disabled={busy||!!running} onClick={()=>void inspectBrowser()}>我已登录，读取本人账号</Button>
      <form className="space-y-4" onSubmit={e=>{e.preventDefault();void run('/prepare',{sender,target,kind,message:kind==='message'?message:'',authorized:true})}}>
        <label className="block text-sm">本人账号（主页链接或 @抖音号）<Input aria-label="本人账号主页" className="mt-2" type="text" required value={sender} onChange={e=>{setSender(e.target.value);setAuthorized(false)}} placeholder="点击上方读取账号，或填写 @抖音号"/></label>
        <label className="block text-sm">获准测试的用户主页<Input aria-label="测试用户主页" className="mt-2" type="url" required value={target} onChange={e=>{setTarget(e.target.value);setAuthorized(false)}} placeholder="https://www.douyin.com/user/…"/></label>
        <label className="block text-sm">操作类型<select className="library-select mt-2" aria-label="账号操作类型" value={kind} onChange={e=>{setKind(e.target.value as 'follow'|'message');setAuthorized(false)}}><option value="follow">关注此用户</option><option value="message">发送一条私信</option></select></label>
        {kind==='message'&&<label className="block text-sm">消息内容<textarea aria-label="待发送消息" className="account-message" required maxLength={500} rows={3} value={message} onChange={e=>{setMessage(e.target.value);setAuthorized(false)}}/><small>{message.length}/500</small></label>}
        <label className="account-consent"><input type="checkbox" checked={authorized} onChange={e=>setAuthorized(e.target.checked)}/>我有权使用上述账号，且此对象和操作属于获准测试范围。</label>
        <Button type="submit" disabled={busy||!!running||!authorized||!sender.trim()||!target.trim()||(kind==='message'&&!message.trim())}>{busy||running?<Loader2 className="learning-spinner"/>:<ShieldCheck/>}核对账号与操作条件</Button>
        <p className="text-xs text-cyber-text-secondary">这一步只打开用户主页、核对关注状态或私信入口，不会关注或发送。登录和验证码由本人完成。</p>
      </form>
    </section>
    {(error||list.isError||detail.isError)&&<p role="alert" className="feedback-error">{error||'状态读取失败，请核对本地服务和操作记录。'}</p>}
    {active&&<section className="account-preview space-y-4" aria-label="账号操作预览">
      <h2 className="text-lg font-semibold">2. 核对本次操作</h2>
      {!action?<p role="status">正在读取操作记录…</p>:<>
        <p role="status" className="font-semibold">{names[action.status]||action.status}</p>
        <dl className="account-identities"><dt>使用账号</dt><dd>{action.sender}</dd><dt>接收对象</dt><dd>{action.target}</dd><dt>操作</dt><dd>{action.kind==='follow'?'关注此用户':'发送一条私信'}</dd></dl>
        {action.kind==='message'&&<div><p className="text-xs text-cyber-text-secondary">实际发送内容</p><pre className="account-message-preview">{action.message}</pre></div>}
        <p className="text-sm leading-6">{action.note}</p>
        {action.status==='ready'&&<><p className="text-xs text-cyber-text-secondary">确认有效至 {new Date(action.expires_at*1000).toLocaleTimeString('zh-CN')}</p><label className="account-consent"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>我已核对以上账号、对象和内容，确认现在执行这一次操作。</label><Button disabled={busy||!confirmed||detail.isError} onClick={()=>void run('/'+action.id+'/confirm',{token:action.confirm_token,confirmed:true})}>{action.kind==='follow'?'确认关注此用户':'确认发送这条消息'}</Button></>}
        {action.status==='uncertain'&&<Button variant="outline" disabled={busy} onClick={()=>void run('/'+action.id+'/verify',{})}>只核对结果，不重复执行</Button>}
        {['blocked','waiting_login','waiting_verification'].includes(action.status)&&<p className="text-sm">处理浏览器中的问题后，使用上方表单重新核对条件。尚未执行，不自动继续。</p>}
      </>}
    </section>}
    <section className="account-history space-y-3"><h2 className="font-semibold">操作记录</h2><p className="text-xs text-cyber-text-secondary">保留防重复记录；删除视频或用户目录不会清除这些记录。</p>{list.data?.items.map(item=><button key={item.id} className="history-task w-full" onClick={()=>{setActive(item.id);setConfirmed(false)}}><span><strong>{item.kind==='follow'?'关注':'私信'} · {names[item.status]||item.status}</strong><small>{item.target}</small></span><small>{new Date(item.updated_at).toLocaleString('zh-CN')}</small></button>)}{!list.data?.items.length&&<p className="library-empty">尚无账号操作记录。</p>}</section>
  </div>
}
