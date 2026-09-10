import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { CommentContent } from './ReplyThread'
import { readLocal, identity, profileSafe, timeLabel, type Catalog, type SavedUser } from './library'

export function UserDrawer({ user, videoId, close }: { user: SavedUser; videoId?: string; close: () => void }) {
  const [filter, setFilter] = useState(videoId || '')
  const [page, setPage] = useState(0)
  const data = useQuery({ queryKey: ['learning-catalog'], queryFn: () => readLocal<Catalog>('catalog'), staleTime: 3000 })
  const comments = (data.data?.comments || []).filter(c => c.source === user.source && c.user_id === user.id)
  const videos = [...new Set(comments.map(c => c.video_id))]
  const shown = comments.filter(c => !filter || c.video_id === filter)
  return <Dialog.Root open onOpenChange={open => { if (!open) close() }}><Dialog.Portal>
    <Dialog.Overlay className="user-drawer-overlay" />
    <Dialog.Content className="learning-shell user-drawer">
      <Dialog.Close aria-label="关闭用户详情" className="drawer-close"><X size={20} /></Dialog.Close>
      <Dialog.Title className="text-xl font-semibold pr-8">{user.nickname || '未展示昵称'}</Dialog.Title>
      <Dialog.Description className="text-sm text-cyber-text-secondary">用户详情 · {user.source === 'live' ? '网页读取' : '本地导入'} · 汇总最新已存评论</Dialog.Description>
      <p className="text-xs break-all text-cyber-text-secondary">{user.id}</p>
      {profileSafe(user.profile_url) && <a className="text-cyan-700 underline text-sm" href={user.profile_url} target="_blank" rel="noreferrer">打开抖音用户主页</a>}
      {profileSafe(user.profile_url) && <Button variant="outline" onClick={() => { sessionStorage.setItem('learning-action-target',user.profile_url!); window.location.hash='account-actions'; close() }}>以此用户填写关注／私信预览</Button>}
      <p className="text-sm">已存 {comments.length} 条评论 · 涉及 {videos.length} 个视频</p>
      <label className="text-sm">查看范围<select aria-label="用户评论视频范围" value={filter} onChange={e => { setFilter(e.target.value); setPage(0) }} className="library-select mt-2"><option value="">所有涉及的视频</option>{videos.map(id => <option key={id} value={id}>{data.data?.videos.find(v => v.source === user.source && v.id === id)?.title || id}</option>)}</select></label>
      {data.isError ? <p role="alert">用户记录加载失败。<Button variant="outline" size="sm" onClick={() => void data.refetch()}>重试</Button></p> : data.isLoading ? <p>正在加载用户记录…</p> : <div className="space-y-4">{shown.slice(page * 100, (page + 1) * 100).map(c => <article key={identity(c)} className="library-comment"><p className="text-xs text-cyber-text-secondary">{data.data?.videos.find(v => v.source === c.source && v.id === c.video_id)?.title || c.video_id}</p><CommentContent comment={c} /><p className="text-xs text-cyber-text-secondary">{c.parent_comment_id ? '回复' : '主评论'} · 发表时间：{timeLabel(c.create_time)}</p></article>)}{!shown.length && <p>该范围没有已保存评论。</p>}</div>}
      <div className="flex gap-2 items-center"><Button size="sm" variant="outline" disabled={!page} onClick={() => setPage(p => p - 1)}>上一页</Button><span className="text-xs">第 {page + 1} 页</span><Button size="sm" variant="outline" disabled={(page + 1) * 100 >= shown.length} onClick={() => setPage(p => p + 1)}>下一页</Button></div>
    </Dialog.Content>
  </Dialog.Portal></Dialog.Root>
}
