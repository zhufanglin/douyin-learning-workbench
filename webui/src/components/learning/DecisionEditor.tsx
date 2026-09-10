import { useState } from 'react'
import { Button } from '@/components/ui/button'
export const judgmentNames = { clear:'明确需求', possible:'可能需求', advertising:'推广广告', irrelevant:'无关', pending:'待判断' }
export type Judgment = keyof typeof judgmentNames
export type Assessment = {fields?:Record<string,string[]>;source:string;comment_id:string;revision:string;automatic:Judgment;evidence:string[];reason:string;stale:boolean;manual:{status:Judgment;reason:string;updated_at:string}|null}
export type AnalysisResult = {profile?:{fields?:{name:string;terms:string[]}[]};items:Assessment[];total_comments:number}
export async function analysisRequest(path:string,method:string,body?:unknown) {
 const r=await fetch('/api/learning/analysis/'+path,{method,headers:{'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})})
 const value=await r.json();if(!r.ok)throw Error(typeof value.detail==='string'?value.detail:'操作失败，请刷新重试');return value
}
export function DecisionEditor({item,business,refresh}:{item?:Assessment;business:string;refresh:()=>void}) {
 const [open,setOpen]=useState(false),[status,setStatus]=useState<Judgment>('pending'),[reason,setReason]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('')
 if(!business)return null
 if(!item||item.stale)return <p className="text-xs text-amber-700">{item?.stale?'条件或原话已变化，请重新分析':'尚未分析'} · 待判断</p>
 async function save(reset=false){setBusy(true);setError('');try{await analysisRequest(business+'/decision','PUT',{source:item!.source,comment_id:item!.comment_id,revision:item!.revision,status:reset?null:status,reason});refresh();setOpen(false)}catch(e){setError(e instanceof Error?e.message:'保存失败')}finally{setBusy(false)}}
 return <div className="space-y-2 text-xs">
 <p><strong>{judgmentNames[item.manual?.status||item.automatic]}</strong> · {item.manual?'人工判断':'规则初判'}：{item.manual?.reason||item.reason}</p>
 {item.evidence.length>0&&<p>命中原文：{item.evidence.map(x=>'“'+x+'”').join('、')}</p>}
 {item.fields&&Object.keys(item.fields).length>0&&<dl className="grid gap-1" aria-label="原文提及字段">{Object.entries(item.fields).map(([name,values])=><div key={name} className="flex flex-wrap gap-2"><dt>{name}：</dt><dd className="break-all">{values.length?values.join('、'):'—'}</dd></div>)}<p className="text-cyber-text-secondary">字段仅表示原文提及，不代表肯定意愿；— 表示未匹配到。</p></dl>}
 {item.manual&&<p className="text-cyber-text-secondary">规则原判：{judgmentNames[item.automatic]} · {item.reason}</p>}
 <Button size="sm" variant="ghost" onClick={()=>{setOpen(!open);setStatus(item.manual?.status||item.automatic);setReason(item.manual?.reason||'')}}>人工判断</Button>
 {open&&<div className="space-y-2"><label>判断类别<select className="library-select" value={status} disabled={busy} onChange={e=>setStatus(e.target.value as Judgment)}>{Object.entries(judgmentNames).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label><label className="block">判断依据<textarea className="library-select w-full" maxLength={1000} value={reason} disabled={busy} onChange={e=>setReason(e.target.value)}/></label><div className="flex flex-wrap gap-2"><Button size="sm" disabled={busy||!reason.trim()} onClick={()=>void save()}>{busy?'保存中…':'保存判断'}</Button>{item.manual&&<Button size="sm" variant="outline" disabled={busy} onClick={()=>void save(true)}>恢复规则初判</Button>}</div></div>}
 {error&&<p role="alert">{error}</p>}
 </div>
}
