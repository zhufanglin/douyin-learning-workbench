import { useEffect, useRef, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { Monitor, Maximize2, ExternalLink, X, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'

type Frame = { status: string; image: string|null; url: string; sequence: number; age_ms: number|null; busy: boolean }

export function BrowserPreview({ close }: { close: () => void }) {
  const [frame,setFrame]=useState<Frame>()
  const [offline,setOffline]=useState(false)
  const [expanded,setExpanded]=useState(false)
  const [note,setNote]=useState('')
  const [focusing,setFocusing]=useState(false)
  const expandButton=useRef<HTMLButtonElement>(null)
  useEffect(()=>{
    let disposed=false, generation=0, timer: ReturnType<typeof setTimeout>, controller: AbortController|undefined
    async function refresh() {
      if(disposed||document.hidden)return
      const current=++generation
      const request=new AbortController();controller=request
      const timeout=setTimeout(()=>request.abort(),5000)
      try {
        const r=await fetch('/api/learning/browser/preview',{cache:'no-store',signal:controller.signal})
        if(!r.ok)throw new Error('preview')
        const value=await r.json() as Frame
        if(!disposed&&current===generation){setFrame(value);setOffline(false)}
      } catch {if(!disposed&&!document.hidden&&current===generation)setOffline(true)}
      finally {clearTimeout(timeout);if(!disposed&&!document.hidden&&current===generation)timer=setTimeout(refresh,1500)}
    }
    const visible=()=>{generation++;clearTimeout(timer);controller?.abort();if(!document.hidden)timer=setTimeout(refresh,100)}
    void refresh();document.addEventListener('visibilitychange',visible)
    return ()=>{disposed=true;clearTimeout(timer);controller?.abort();document.removeEventListener('visibilitychange',visible)}
  },[])
  async function focusBrowser() {
    setFocusing(true);setNote('')
    try {
      const r=await fetch('/api/learning/browser/focus',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})
      const data=await r.json();if(!r.ok)throw new Error(data.detail||'切换失败')
      setNote(data.note)
    } catch(e) {setNote(e instanceof Error?e.message:'切换失败')}
    finally {setFocusing(false)}
  }
  const delayed=!!frame?.image&&(frame.age_ms??0)>6000
  const waiting=frame?.status==='waiting'
  const label=offline?'连接中断':frame?.status==='closed'?'浏览器已关闭':waiting?'等待画面':frame?.image?(delayed?'画面更新延迟':frame.busy?'执行中':'已同步'):frame?.status==='idle'?'等待任务':'连接画面中'
  const viewport=(large=false)=><div className={'browser-viewport'+(large?' is-large':'')}>
    {frame?.image?<img src={frame.image} alt="当前执行浏览器画面" draggable={false}/>:<div className="browser-placeholder"><Monitor size={36}/><strong>{label}</strong><span>开始网页任务后，执行画面会显示在这里</span></div>}
    {frame?.image&&(offline||delayed||waiting)&&<span className="browser-stale">{offline?'连接中断 · 保留最后画面':`最后更新于 ${Math.floor((frame.age_ms??0)/1000)} 秒前`}</span>}
  </div>
  return <aside className="browser-preview" aria-label="执行浏览器">
    <div className="browser-toolbar"><strong><Monitor size={16}/>执行浏览器</strong><span className={'browser-status'+(frame?.busy&&!offline&&!delayed?' is-running':'')}><i/>{label}</span><Button size="icon" variant="ghost" aria-label="收起浏览器画面" onClick={close}><X size={15}/></Button></div>
    <div className="browser-address" title={frame?.url}>{frame?.url||'当前工具浏览器 · 同步预览'}</div>
    {viewport()}
    <div className="browser-controls"><span>同步画面 · 约 1–2 秒更新</span><div><Button ref={expandButton} size="sm" variant="ghost" disabled={!frame?.image} onClick={()=>setExpanded(true)}><Maximize2 size={14}/>放大</Button><Button size="sm" variant="outline" disabled={focusing||!frame?.image} onClick={()=>void focusBrowser()}>{focusing?<Loader2 size={14} className="learning-spinner"/>:<ExternalLink size={14}/>}操作浏览器</Button></div></div>
    <p className="browser-helper">登录或验证时，点“操作浏览器”。此处画面不可直接点击。</p>
    {note&&<p role="status" className="browser-helper">{note}</p>}
    <Dialog.Root open={expanded} onOpenChange={setExpanded}><Dialog.Portal><Dialog.Overlay className="browser-overlay"/><Dialog.Content className="learning-shell browser-expanded" onCloseAutoFocus={e=>{e.preventDefault();expandButton.current?.focus()}}><div className="browser-toolbar"><Dialog.Title>执行浏览器</Dialog.Title><Dialog.Close asChild><Button size="icon" variant="ghost" aria-label="关闭放大画面"><X size={18}/></Button></Dialog.Close></div><Dialog.Description className="sr-only">当前工具浏览器的同步画面，按 Escape 关闭。</Dialog.Description>{viewport(true)}</Dialog.Content></Dialog.Portal></Dialog.Root>
  </aside>
}
