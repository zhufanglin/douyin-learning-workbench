import {CommentSource} from './CommentSource'
import {matchesCommentDate} from './leadFilters'
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { DecisionEditor, judgmentNames, analysisRequest, type Assessment, type AnalysisResult } from './DecisionEditor'
import { CommentContent } from './ReplyThread'
import { identity, profileSafe, readLocal, timeLabel, type Catalog, type SavedComment } from './library'

export function LeadsPanel() {
  const query = useQuery({ queryKey: ['lead-catalog'], queryFn: () => readLocal<Catalog>('catalog'), refetchInterval: 10000 })
  const [sourceVideo, setSourceVideo] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [analysisBusiness,setAnalysisBusiness]=useState('')
  const [category,setCategory]=useState('')
  const [field,setField]=useState(''),[fieldValue,setFieldValue]=useState(''),[fieldMode,setFieldMode]=useState('any')
  const [start,setStart]=useState(''),[end,setEnd]=useState(''),[timeMode,setTimeMode]=useState('all')
  const invalidDates=timeMode!=='missing'&&!!start&&!!end&&start>end
  const [analyzing,setAnalyzing]=useState(false)
  const [error,setError]=useState('')
  const configs=useQuery({queryKey:['business-profiles'],queryFn:()=>readLocal<{items:{id:string;name:string}[]}>('business-profiles')})
  const analysis=useQuery({queryKey:['analysis',analysisBusiness],queryFn:()=>readLocal<AnalysisResult>('analysis/'+analysisBusiness),enabled:!!analysisBusiness})
  const assessments=useMemo(()=>new Map((analysis.data?.items||[]).map(x=>[identity({source:x.source,id:x.comment_id}),x])),[analysis.data])
  async function run(){setAnalyzing(true);setError('');try{await analysisRequest(analysisBusiness,'POST');await analysis.refetch()}catch(e){setError(e instanceof Error?e.message:'分析失败')}finally{setAnalyzing(false)}}
  const data = query.data
  const sourceVideos=useMemo(()=>{
    if(!data)return []
    const known=new Map(data.videos.map(v=>[identity(v),v]))
    return [...new Map(data.comments.filter(c=>c.video_id).map(c=>{const key=identity({source:c.source,id:c.video_id});return [key,{key,title:known.get(key)?.title||'标题未读取 · '+c.video_id}]})).values()]
  },[data])
  const hasFields=!!analysisBusiness&&!!analysis.data?.profile?.fields?.length
  const rows = useMemo(() => {
    if (!data) return []
    const users = new Map(data.users.map(u => [identity(u), u]))
    const grouped = new Map<string, { user: Catalog['users'][number]; comments: SavedComment[] }>()
    for (const comment of data.comments) {
      if (!comment.user_id || invalidDates || !matchesCommentDate(comment.create_time,start,end,timeMode)) continue
      if(sourceVideo&&identity({source:comment.source,id:comment.video_id})!==sourceVideo)continue
      const assessment=assessments.get(identity(comment))
      if(analysisBusiness&&field){
        const values=assessment&&!assessment.stale?(assessment.fields?.[field]||[]):[]
        if((fieldMode==='present'&&!values.length)||(fieldMode==='missing'&&values.length))continue
        if(fieldValue.trim()&&!values.some(v=>v.toLocaleLowerCase().includes(fieldValue.trim().toLocaleLowerCase())))continue
      }
      const judgment=assessment&&!assessment.stale?(assessment.manual?.status||assessment.automatic):'pending'
      if(analysisBusiness&&category&&judgment!==category)continue
      const key = identity({ source: comment.source, id: comment.user_id })
      const user = users.get(key) || { id: comment.user_id, source: comment.source, nickname: '未提供昵称' }
      if (search.trim() && ![user.nickname, comment.content].some(v => v?.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()))) continue
      if (!grouped.has(key)) grouped.set(key, { user, comments: [] })
      grouped.get(key)!.comments.push(comment)
    }
    return [...grouped.values()]
  }, [data, sourceVideo, search, assessments, analysisBusiness, category, field, fieldValue, fieldMode, start, end, timeMode, invalidDates])
  const current = Math.min(page, Math.max(0, Math.ceil(rows.length / 20) - 1))
  return <section className="library-panel space-y-4" aria-label="需求用户列表">
    <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold">需求用户</h2><Button size="sm" variant="outline" onClick={() => {void query.refetch();if(analysisBusiness)void analysis.refetch()}}>刷新</Button></div>
    <p className="text-sm text-cyber-text-secondary">选择分析业务，对已存评论做本地规则初判；明确需求需人工确认。不会自动联系用户。</p>
    <div className="flex flex-wrap gap-3"><label className="min-w-0 flex-1">来源视频<select className="library-select" value={sourceVideo} onChange={e=>{setSourceVideo(e.target.value);setPage(0)}}><option value="">全部视频</option>{sourceVideos.map(v=><option key={v.key} value={v.key}>{v.title}</option>)}</select></label><label>昵称或评论<input className="library-select" value={search} onChange={e => {setSearch(e.target.value);setPage(0)}} placeholder="搜索已保存的原话" /></label></div>
    <div className="flex flex-wrap gap-3 items-end"><label>分析业务<select className="library-select" value={analysisBusiness} disabled={analyzing} onChange={e=>{setAnalysisBusiness(e.target.value);setCategory('');setField('');setFieldValue('');setFieldMode('any');setPage(0);setError('')}}><option value="">选择已保存配置</option>{configs.data?.items.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><Button size="sm" disabled={!analysisBusiness||analyzing} onClick={()=>void run()}>{analyzing?'正在分析…':'分析已存评论'}</Button><label>判断类别<select className="library-select" disabled={!analysisBusiness} value={category} onChange={e=>{setCategory(e.target.value);setPage(0)}}><option value="">全部类别</option>{Object.entries(judgmentNames).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label></div>
    {!analysisBusiness&&<p className="text-xs text-cyber-text-secondary">查看用户和按视频、评论时间筛选不需要分析配置。需要分类时，先选择“分析业务”。{!configs.isLoading&&!configs.data?.items.length&&<> 还没有配置，<a className="underline" href="#keyword">去新建搜索添加业务配置</a>。</>}</p>}
    <details className="border rounded-xl p-3"><summary>字段与评论时间筛选</summary><div className="flex flex-wrap gap-3 mt-3">
      {hasFields?<><label>需求字段<select className="library-select" value={field} disabled={!analysisBusiness} onChange={e=>{setField(e.target.value);setFieldValue('');setFieldMode('any');setPage(0)}}><option value="">全部字段</option>{analysis.data?.profile?.fields?.map(f=><option key={f.name} value={f.name}>{f.name}</option>)}</select></label>
      <label>字段状态<select className="library-select" disabled={!field||!analysisBusiness} value={fieldMode} onChange={e=>{setFieldMode(e.target.value);setFieldValue('');setPage(0)}}><option value="any">不限</option><option value="present">有提及</option><option value="missing">未提及或未分析</option></select></label>
      <label>字段包含<input className="library-select" disabled={!field||!analysisBusiness||fieldMode==='missing'} value={fieldValue} onChange={e=>{setFieldValue(e.target.value);setPage(0)}} placeholder="筛选原文中的值"/></label>
      {!field&&<p className="text-xs w-full">先选“需求字段”，再筛选字段状态或包含的值。</p>}
      {fieldMode==='missing'&&field&&<p className="text-xs w-full">当前查看未提及或未分析的记录，无字段值可筛选。</p>}
      </>:<p className="text-xs w-full">{!analysisBusiness?'字段筛选需先选择分析业务。':analysis.isLoading?'正在读取字段配置…':'此业务尚未配置需求字段。'} <a className="underline" href="#keyword">设置业务与需求字段</a></p>}
      <label>评论时间状态<select className="library-select" value={timeMode} onChange={e=>{setTimeMode(e.target.value);setPage(0)}}><option value="all">不限</option><option value="known">时间已提供</option><option value="missing">时间未提供</option></select></label>
      <label>评论开始日期<input className="library-select" type="date" disabled={timeMode==='missing'} value={start} onChange={e=>{setStart(e.target.value);setPage(0)}}/></label>
      <label>评论结束日期<input className="library-select" type="date" disabled={timeMode==='missing'} value={end} onChange={e=>{setEnd(e.target.value);setPage(0)}}/></label>
      <Button size="sm" variant="outline" onClick={()=>{setField('');setFieldValue('');setFieldMode('any');setStart('');setEnd('');setTimeMode('all');setPage(0)}}>清除字段与时间筛选</Button>
    </div><p className="text-xs mt-2">日期按本机时区，包含结束日；设置日期范围会排除缺失时间的评论，不用采集时间代替评论时间。</p></details>
    {invalidDates&&<p role="alert">开始日期不能晚于结束日期。</p>}
    <p className="text-xs text-cyber-text-secondary">分析范围为全部已存评论，页面筛选仅影响展示。业务目标、条件文本供人工参考；自动初判只使用配置中的需求词、广告词、排除词，不做语义理解。</p>
    {analysisBusiness&&analysis.data&&<p role="status" className="text-xs">已分析 {analysis.data.items.filter(x=>!x.stale).length}/{analysis.data.total_comments} 条 · 条件变更或新增评论后请重新分析</p>}
    {(error||analysis.isError||configs.isError)&&<p role="alert">{error||'分析或配置读取失败，请刷新重试。'}</p>}

    {query.isLoading && <p role="status">正在整理用户与评论…</p>}
    {query.isError && <p role="alert">读取失败，请点击刷新重试。</p>}
    {data && <p role="status" className="text-sm">{rows.length} 位用户 · 第 {current + 1} 页 · 每页 20 位</p>}
    {data && !rows.length && <p>暂无符合筛选条件的已存评论用户。</p>}
    {rows.slice(current * 20, (current + 1) * 20).map(row => <article key={identity(row.user)} className="rounded-xl border p-3 min-w-0 space-y-2">
      <div className="flex flex-wrap justify-between gap-2"><strong className="break-all">{row.user.nickname || '未提供昵称'}</strong><span className="text-xs text-cyber-text-secondary">留言 · {row.comments.length} 条留言</span></div>
      {profileSafe(row.user.profile_url) && <a className="text-sm underline" href={row.user.profile_url} target="_blank" rel="noreferrer">用户主页</a>}
      <Evidence key={sourceVideo + search + analysisBusiness + category + field + fieldValue + fieldMode + start + end + timeMode} comments={row.comments} data={data!} business="" analysisBusiness={analysisBusiness} assessments={assessments} refresh={()=>void analysis.refetch()} />
    </article>)}
    <div className="flex gap-2"><Button size="sm" variant="outline" disabled={!current} onClick={() => setPage(current - 1)}>用户上一页</Button><Button size="sm" variant="outline" disabled={(current + 1) * 20 >= rows.length} onClick={() => setPage(current + 1)}>用户下一页</Button></div>
  </section>
}
function Evidence({ comments, data, business, analysisBusiness, assessments, refresh }: {comments: SavedComment[]; data: Catalog; business: string;analysisBusiness:string;assessments:Map<string,Assessment>;refresh:()=>void}) {
  const [count, setCount] = useState(3)
  return <div className="space-y-3">{comments.slice(0, count).map(c => <div key={identity(c)} className="border-t pt-2 text-sm min-w-0">
    <CommentContent comment={c} /><DecisionEditor item={assessments.get(identity(c))} business={analysisBusiness} refresh={refresh}/><p className="text-xs text-cyber-text-secondary">评论时间：{timeLabel(c.create_time)}</p>
    <CommentSource comment={c} data={data} business={business}/>
  </div>)}{count < comments.length && <Button size="sm" variant="outline" onClick={() => setCount(count + 20)}>展开更多留言（剩余 {comments.length - count} 条）</Button>}</div>
}
