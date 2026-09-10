import {useState} from 'react'
import {useQuery,useQueryClient} from '@tanstack/react-query'
import {FieldConfig,type FieldDraft} from './FieldConfig'
import {Button} from '@/components/ui/button'
type Profile={id:string;name:string;goal:string;keywords:string[];include:string;exclude:string;demand_terms?:string[];ad_terms?:string[];exclude_terms?:string[];fields?:{name:string;terms:string[]}[]}
const blank={name:'',goal:'',keywords:'',include:'',exclude:'',demand_terms:'',ad_terms:'',exclude_terms:'',fields:[] as FieldDraft[]}
export function BusinessProfiles({selected,onSelect,disabled}:{selected:string;onSelect:(id:string,keyword?:string)=>void;disabled:boolean}){
 const q=useQueryClient();const [draft,setDraft]=useState(blank);const [editing,setEditing]=useState('');const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [confirm,setConfirm]=useState(false)
 const profiles=useQuery({queryKey:['business-profiles'],queryFn:async()=>{const r=await fetch('/api/learning/business-profiles');if(!r.ok)throw Error('配置读取失败');return r.json() as Promise<{items:Profile[]}>}})
 function choose(id:string){const p=profiles.data?.items.find(x=>x.id===id);setEditing(id);setDraft(p?{...p,keywords:p.keywords.join('\n'),demand_terms:(p.demand_terms||[]).join('\n'),ad_terms:(p.ad_terms||[]).join('\n'),exclude_terms:(p.exclude_terms||[]).join('\n'),fields:(p.fields||[]).map(f=>({name:f.name,terms:f.terms.join('\n')}))}:blank);setConfirm(false);setError('');onSelect(id,p?.keywords[0])}
 async function save(remove=false){if(busy)return;setBusy(true);setError('');try{
  const r=await fetch('/api/learning/business-profiles'+(editing?'/'+editing:''),{method:remove?'DELETE':editing?'PUT':'POST',headers:{'Content-Type':'application/json'},...(!remove?{body:JSON.stringify({name:draft.name,goal:draft.goal,keywords:draft.keywords.split('\n').filter(x=>x.trim()),demand_terms:draft.demand_terms.split('\n').filter(x=>x.trim()),ad_terms:draft.ad_terms.split('\n').filter(x=>x.trim()),exclude_terms:draft.exclude_terms.split('\n').filter(x=>x.trim()),include:draft.include,exclude:draft.exclude,fields:draft.fields.map(f=>({name:f.name,terms:f.terms.split('\n').filter(x=>x.trim())}))})}:{})});const data=await r.json();if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'请检查必填项、字段重名及长度：关键词最多20个，字段最多10个，各类短语最多50个，每条80字。');await q.invalidateQueries({queryKey:['business-profiles']});if(remove){setEditing('');setDraft(blank);onSelect('')}else{setEditing(data.id);onSelect(data.id,data.keywords[0])}setConfirm(false)
 }catch(e){setError(e instanceof Error?e.message:'保存失败')}finally{setBusy(false)}}
 return <section className="library-panel" aria-label="业务目标配置"><h2 className="font-semibold mb-3">业务目标</h2>
 <label>使用配置<select className="library-select" aria-label="业务目标配置" disabled={disabled||busy} value={selected} onChange={e=>choose(e.target.value)}><option value="">不使用配置</option>{profiles.data?.items.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
 {selected&&<p className="text-sm my-2">{profiles.data?.items.find(p=>p.id===selected)?.goal}</p>}
 {profiles.isError&&<p role="alert">配置读取失败，请刷新重试。</p>}
 <details className="mt-3"><summary>新建或编辑配置</summary><div className="space-y-3 mt-3">
 <Button size="sm" variant="outline" disabled={disabled||busy} onClick={()=>choose('')}>新建配置</Button>
 {([['name','配置名称'],['goal','想找到什么需求的用户'],['keywords','搜索关键词（每行一个）'],['include','纳入条件'],['exclude','排除条件'],['demand_terms','需求词（每行一个）'],['ad_terms','广告词（每行一个）'],['exclude_terms','排除词（每行一个）']] as const).map(([key,label])=><label key={key} className="block text-sm">{label}<textarea className="library-select w-full" aria-label={label} rows={key==='name'?1:2} maxLength={key==='name'?80:key==='goal'?2000:4000} value={draft[key]} disabled={disabled||busy} onChange={e=>{setDraft({...draft,[key]:e.target.value});onSelect('');setConfirm(false)}}/></label>)}
 <FieldConfig value={draft.fields} disabled={disabled||busy} onChange={fields=>{setDraft({...draft,fields});onSelect('');setConfirm(false)}}/>
 <div className="flex gap-2"><Button size="sm" disabled={disabled||busy||!draft.name.trim()||!draft.goal.trim()||!draft.keywords.trim()} onClick={()=>void save()}>{busy?'处理中…':'保存并使用'}</Button>{editing&&<Button size="sm" variant="outline" disabled={disabled||busy} onClick={()=>setConfirm(true)}>删除配置</Button>}</div>
 {confirm&&<div role="alert">删除此配置？旧任务的条件快照会保留。<Button size="sm" disabled={busy} onClick={()=>void save(true)}>确认删除配置</Button><Button size="sm" variant="ghost" onClick={()=>setConfirm(false)}>取消</Button></div>}
 <p className="text-xs text-cyber-text-secondary">保存后使用第一条关键词，可在下方修改；不会自动批量搜索。编辑未保存时不应用配置。需求用户页可按配置词做本地初判：每类最多50个短语，按原文包含匹配。目标和纳入/排除条件保留为人工参考，不自动解释自然语言。</p>
 {error&&<p role="alert">{error}</p>}
 </div></details></section>
}
