// Reuses MediaCrawler's React/Tailwind UI components under its learning license.
import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Play, MessageSquare, Loader2, Upload, Search, Database, Users, FlaskConical, LayoutDashboard, Video, ScrollText, Plus, ArrowUpRight, ChevronRight, Monitor } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { LibraryPanel } from './LibraryPanel'
import { viewNames, type View } from './library'
import { useWorkbenchRoute, pageNames } from './navigation'
import { AccountPanel } from './AccountPanel'
import { LogList } from './LogList'
import { SearchFeedback, type SearchResult } from './SearchFeedback'
import './workbench.css'
import { BrowserPreview } from './BrowserPreview'
import { BeginnerGuide } from './BeginnerGuide'

type Source = 'demo' | 'live' | 'import'
type Task = { id: string; keyword: string; source: Source; status: string; note: string; created_at: string }
type State = { tasks: Task[];  logs: Record<string, unknown>[]; counts: Record<string, number>; capabilities?: { video_url_read?: boolean } }
async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch('/api/learning/' + path, body === undefined ? undefined : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
  const data = await response.json()
  if (!response.ok) {
    const detail = data.detail
    throw new Error(typeof detail === 'string' ? detail : detail?.message || (Array.isArray(detail) ? detail.map((d: { msg: string }) => d.msg).join('；') : '请求失败'))
  }
  return data
}

export function LearningPanel() {
  const queryClient = useQueryClient()
  const [keyword, setKeyword] = useState(() => sessionStorage.getItem('learning-search-keyword') || '露营')
  useEffect(() => { sessionStorage.setItem('learning-search-keyword', keyword) }, [keyword])
  const [videoUrl, setVideoUrl] = useState('')
  const source = 'live'
  const { route, navigate } = useWorkbenchRoute()
  const page = route.page
  const [previewOpen,setPreviewOpen]=useState(()=>sessionStorage.getItem('learning-browser-panel')!=='closed')
  const showPreview=previewOpen&&page!=='overview'
  function togglePreview(value:boolean){setPreviewOpen(value);sessionStorage.setItem('learning-browser-panel',value?'open':'closed')}
  const view: View = page in viewNames ? page as View : 'tasks'
  const selected = route.task
  function setSelected(id: string) { navigate(view, id) }
  const [searchTask, setSearchTask] = useState(() => sessionStorage.getItem('learning-search-task') || '')
  useEffect(() => { if (searchTask) sessionStorage.setItem('learning-search-task', searchTask); else sessionStorage.removeItem('learning-search-task') }, [searchTask])
  useEffect(() => {
    const onDelete = (event: Event) => {
      const ids: string[] = (event as CustomEvent).detail.deleted_task_ids || []
      if (ids.includes(searchTask)) setSearchTask('')
      if (ids.includes(selected)) setSelected('')
    }
    window.addEventListener('learning-records-deleted', onDelete)
    return () => window.removeEventListener('learning-records-deleted', onDelete)
  }, [searchTask, selected, view])
  const [busy, setBusy] = useState(false)
  const requestLock = useRef(false)
  const [submitting, setSubmitting] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const state = useQuery({ queryKey: ['learning-state'], queryFn: () => api<State>('state?include_demo=false'), refetchInterval: 1500 })

  async function run<T>(fn: () => Promise<T>, done?: (value: T) => void) {
    if (requestLock.current) return
    requestLock.current = true
    setBusy(true); setError(''); setNotice('')
    try {
      const value = await fn()
      done?.(value)
      await queryClient.invalidateQueries({ queryKey: ['learning-state'] })
      await queryClient.invalidateQueries({ queryKey: ['learning-task'] })
      await queryClient.invalidateQueries({ queryKey: ['learning-catalog'] })
    } catch (e) { setError(e instanceof Error ? e.message : '操作失败') }
    finally { setBusy(false); requestLock.current = false }
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    void startSearch('tasks')
  }

  async function startSearch(path: 'tasks' | 'browser/search-current') {
    if (requestLock.current || reading || statusUnknown) return
    setSubmitting(true)
    try {
      await run(() => api<Task>(path, { keyword, source, limit: 100 }), task => {
        // Seed the status immediately, before the first polling response arrives.
        queryClient.setQueryData(['learning-task', task.id], { task, videos: [] })
        setSearchTask(task.id)
      })
    } finally { setSubmitting(false) }
  }
  async function pauseSearch() {
    setStopping(true)
    try { await run(() => api<Task>('tasks/' + searchTask + '/cancel', {}), task => {
      queryClient.setQueryData<SearchResult>(['learning-task', searchTask], old => ({ ...old, task }))
    }) } finally { setStopping(false) }
  }

  async function importFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    await run(async () => {
      if (file.size > 2_000_000) throw new Error('请选择小于 2 MB 的 JSON 文件。')
      const records: unknown = JSON.parse(await file.text())
      if (!Array.isArray(records)) throw new Error('需要 MediaCrawler 导出的 JSON 数组，最多 500 条。')
      return api<Task>('import', { records })
    }, task => { navigate('users', task.id); setNotice('已导入本地记录；来源标记为“本地导入”。') })
  }

  const activeSearch = useQuery({ queryKey: ['learning-task', searchTask], queryFn: () => api<SearchResult>('tasks/' + searchTask), enabled: !!searchTask, refetchInterval: 1500, retry: false })
  const reading = activeSearch.data?.task.status === 'running'
  const otherRunning = state.data?.tasks.some(t => t.status === 'running' && t.id !== searchTask)
  const statusUnknown = !!searchTask && (!activeSearch.data || activeSearch.isError)
  const readDisabled = busy || reading || statusUnknown || !!otherRunning
  const counts = state.data?.counts || {}

  return <div className="learning-shell min-h-screen bg-cyber-bg-primary text-cyber-text-primary">
    <a className="skip-link" href="#main-content" onClick={e => { e.preventDefault(); document.getElementById('main-content')?.focus() }}>跳到当前页面内容</a>
    <aside className="workbench-sidebar">
      <a href="#overview" className="workbench-brand"><span className="brand-symbol"><FlaskConical size={23} /></span><span><strong>抖音 Agent</strong><small>内容探索 · 学习工作台</small></span></a>
      <div className="sidebar-environment"><span />本地学习空间<Badge variant="outline">原型</Badge></div>
      <nav aria-label="工作台导航">
        <p className="nav-caption">工作空间</p>
        <a href="#overview" className={page === 'overview' ? 'is-active' : ''} aria-current={page === 'overview' ? 'page' : undefined}><LayoutDashboard />工作台概览</a>
        <a href="#keyword" className={page === 'keyword' ? 'is-active' : ''} aria-current={page === 'keyword' ? 'page' : undefined}><Plus />新建搜索</a>
        <p className="nav-caption">数据与任务</p>
        {([['tasks', Search], ['videos', Video], ['users', Users], ['comments', Database]] as const).map(([key, Icon]) => <a key={key} href={'#' + key} className={page === key ? 'is-active' : ''} aria-current={page === key ? 'page' : undefined}><Icon />{viewNames[key]}<ChevronRight /></a>)}
        <a href="#account-actions" className={page === 'account-actions' ? 'is-active' : ''} aria-current={page === 'account-actions' ? 'page' : undefined}><MessageSquare />关注与私信</a>
        <a href="#task-logs" className={page === 'task-logs' ? 'is-active' : ''} aria-current={page === 'task-logs' ? 'page' : undefined}><ScrollText />任务日志</a>
      </nav>
      <div className="sidebar-bottom"><div className="sidebar-profile"><span>学</span><div><strong>个人学习空间</strong><small>数据保存在本机</small></div></div></div>
    </aside>
    <div className="workbench-body">
    <header className="workbench-topbar">
      <div className="topbar-breadcrumb"><LayoutDashboard size={17} /><span>工作空间</span><ChevronRight size={14} /><strong>{pageNames[page]}</strong></div>
      <div className="workbench-topbar-actions"><BeginnerGuide /><Badge variant={state.isError ? 'destructive' : state.data ? 'success' : 'secondary'}>{state.isError ? '服务未连接' : state.data ? '本地服务已连接' : '连接中'}</Badge><ThemeToggle /></div>
    </header>
    <main key={page} className="workbench-main space-y-5 learning-page-enter" id="main-content" tabIndex={-1} data-page={page}>
      <div className="workbench-heading"><h1>{pageNames[page]}</h1><div className="workbench-heading-actions">{page!=='overview'&&<Button size="sm" variant="outline" aria-expanded={showPreview} onClick={()=>togglePreview(!previewOpen)}><Monitor size={15}/>{showPreview?'收起浏览器':'浏览器画面'}</Button>}{page!=='keyword'&&<a href="#keyword" className="quick-create"><Plus size={15} />新建搜索</a>}</div></div>
      <div className={'workbench-content-grid'+(showPreview?' with-preview':'')}><div className="workbench-primary space-y-4">
      {page === 'overview' && <>
      <section className="workspace-banner" aria-label="探索流程"><div><span className="banner-label">内容探索</span><h2>发现内容，读懂讨论。</h2><p>搜索视频 → 选择视频 → 分批读取评论 → 保存结果</p></div><a href="#tasks">查看任务结果<ArrowUpRight size={18} /></a></section>
      <div className="workspace-stats grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[['tasks', '累计任务', Search], ['videos', '已存视频', Video], ['users', '去重用户', Users], ['comments', '已存评论', Database]].map(([key, label, Icon]) => {
          const StatIcon = Icon as typeof Search
          return <button key={String(key)} aria-label={'查看' + String(label)}  className="stat-card stat-entry bg-cyber-bg-panel" onClick={() => navigate(key as View)}><span><span className="text-xs text-cyber-text-secondary">{String(label)}</span><strong className="block text-3xl font-semibold mt-1">{state.data ? counts[String(key)] || 0 : '—'}</strong></span><span className="stat-icon"><StatIcon className="w-5 h-5" /></span></button>
        })}
      </div>
          <Card className="capabilities-card bg-cyber-bg-panel"><CardContent className="p-5"><h2 className="font-semibold mb-3">能力状态</h2><div className="space-y-3 text-xs">
            <div className="flex justify-between gap-2"><span>去重 / 数据保存</span><span className="text-emerald-600">已验证</span></div>
            <div className="flex justify-between gap-2"><span>指定视频评论读取</span><span className="text-emerald-600">单视频已验证</span></div>
            <div className="flex justify-between gap-2"><span>真实关键词视频列表</span><span className="text-emerald-600">已验证 · 最多 100 条</span></div>
            <div className="flex justify-between gap-2"><span>真实关注 / 私信</span><span className="text-emerald-600">单对象已验证</span></div>
          </div></CardContent></Card>
      </>}
      {(error || state.isError) && <div role="alert" className="rounded-lg border border-red-300 bg-red-50 text-red-800 p-3 text-sm">{error || '连接失败，请确认本地服务正在运行。'}</div>}
      {notice && <div role="status" className="rounded-lg border border-cyan-300 bg-cyan-50 text-cyan-900 p-3 text-sm">{notice}</div>}
      {page === 'keyword' && <section className="search-page space-y-5">

          <Card id="search-workspace" className="search-card bg-cyber-bg-panel"><CardContent className="p-5 space-y-4">
            <form onSubmit={submit} className="search-form">
              <div><label htmlFor="keyword" className="text-sm">关键词</label><Input id="keyword" className="mt-2" value={keyword} disabled={readDisabled} onChange={e => setKeyword(e.target.value)} maxLength={80} required placeholder="例如：露营、咖啡、广州租房" /></div>
              <Button className="w-full search-submit" disabled={readDisabled || !keyword.trim()} type="submit" aria-busy={submitting || reading}>{submitting || reading ? <Loader2 className="learning-spinner" /> : <Play />}{submitting ? '正在提交…' : reading ? '正在读取…' : '开始网页读取'}</Button>
              <p className="search-hint text-xs leading-5 text-cyber-text-secondary">最多 100 个视频 · 遇登录或验证暂停</p>
            </form>
            {(submitting || searchTask) && <SearchFeedback pending={submitting} keyword={keyword} result={activeSearch.data} error={activeSearch.isError} stopping={stopping} stop={() => void pauseSearch()} retry={() => void activeSearch.refetch()} view={() => navigate('videos', searchTask)} />}
            {otherRunning && !submitting && <p role="status" className="feedback-error">另一个网页任务正在运行，请等它结束后再开始。<a href="#tasks" className="underline ml-2">查看任务</a></p>}
            <details className="search-advanced"><summary>辅助读取与导入<span>当前页面、视频链接、本地文件</span></summary><div className="space-y-3 pt-4">
            {source === 'live' && <Button className="w-full text-xs" variant="outline" disabled={readDisabled} onClick={() => void startSearch('browser/search-current')}>继续读取当前搜索页</Button>}
            {source === 'live' && <Button className="w-full text-xs" variant="outline" disabled={readDisabled} onClick={() => void run(() => api<Task>('browser/read-current', {}), t => navigate('videos', t.id))}>读取当前视频评论</Button>}
            {source === 'live' && state.data?.capabilities?.video_url_read && <div className="space-y-2"><label htmlFor="video-url" className="text-sm">测试视频链接</label><Input id="video-url" value={videoUrl} onChange={e => setVideoUrl(e.target.value)} maxLength={2000} placeholder="粘贴视频或搜索弹窗网址" /><Button className="w-full text-xs" variant="outline" disabled={readDisabled || !videoUrl.trim()} onClick={() => void run(() => api<Task>('browser/open-video', { url: videoUrl }), t => navigate('videos', t.id))}>按视频链接读取</Button><p className="text-xs text-cyber-text-secondary">仅打开指定视频。出现验证后请本人处理，再读取当前页面。</p></div>}
            <div className="border-t border-cyber-border-subtle pt-4"><label className="flex gap-2 items-center text-sm cursor-pointer"><Upload className="w-4 h-4" />导入 MediaCrawler JSON<input aria-label="导入 JSON" className="sr-only" type="file" accept=".json,application/json" disabled={busy} onChange={importFile} /></label><p className="text-xs text-cyber-text-secondary mt-2">最多 500 条、2 MB；只导入有权使用的数据。</p></div>
            </div></details>
          </CardContent></Card>

      </section>}

      {page === 'account-actions' && <AccountPanel />}
      {page in viewNames && <Card id="task-results" className="results-card bg-cyber-bg-panel"><CardContent className="p-5"><LibraryPanel key={view} view={view} selected={selected} select={setSelected} /></CardContent></Card>}
      {page === 'task-logs' && <Card id="task-logs" className="logs-card bg-cyber-bg-panel"><CardContent className="p-5"><h2 className="font-semibold mb-3">最近日志</h2><LogList logs={state.data?.logs || []} runningIds={(state.data?.tasks || []).filter(t => ['running','queued'].includes(t.status)).map(t => t.id)} /></CardContent></Card>}
      </div>{showPreview&&<BrowserPreview close={()=>togglePreview(false)}/>}</div>
      <footer className="text-xs text-cyber-text-secondary border-t border-cyber-border-subtle pt-3">MediaCrawler © 2024 relakkes@gmail.com · <a href="/license" target="_blank" rel="noreferrer" className="underline">NON-COMMERCIAL LEARNING LICENSE 1.1</a> · 仅供非商业学习</footer>
    </main>
    </div>
  </div>
}
