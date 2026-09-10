import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { CompactText } from './CompactText'

export type Comment = { id: string; content: string; user_id: string; parent_comment_id?: string; kind?: string; content_type?: string; content_status?: string; image_count?: number }
export function CommentContent({ comment }: { comment: Comment }) {
  return <><CompactText text={comment.content} />
    {comment.content_status === 'image_not_read' && <p className="text-xs mt-1 text-amber-700">{comment.content_type === 'image_placeholder' ? `仅记录 ${comment.image_count || 1} 张图片标识` : `图片内容未读取（${comment.image_count || 1} 张）`}</p>}
  </>
}
export type CommentUser = { id: string; nickname: string; profile_url: string }
export function ReplyThread({ replies, users, enabled, exhausted, reading, load, endState, unsupportedCount = 0, readerVersion = 1, imagePlaceholderCount = 0, showUser }: {
  replies: Comment[]; users: CommentUser[]; enabled: boolean; exhausted: boolean; reading: boolean; load: () => void
  endState?: string; unsupportedCount?: number; readerVersion?: number; imagePlaceholderCount?: number
  showUser?: (user: CommentUser) => void
}) {
  const [open, setOpen] = useState(false)
  const [page, setPage] = useState(0)
  const unsupported = endState === 'unsupported'
  const upgrade = unsupported && readerVersion < 4
  if (!enabled && !replies.length) return null
  return <div className="mt-2">
    <div className="flex flex-wrap gap-2 items-center">
      <Button size="sm" variant="outline" onClick={() => setOpen(v => !v)}>{open ? '收起已存回复' : `查看已存回复（${replies.length}）`}</Button>
      {enabled && <Button size="sm" variant="outline" disabled={reading || exhausted || (unsupported && !upgrade)} onClick={() => {
        setOpen(true); setPage(Math.floor(replies.length / 100)); load()
      }}>{upgrade ? (readerVersion < 2 ? '补读表情与图片标识' : '补读图片标识') : unsupported ? '已到页尾 · 有未支持内容' : exhausted ? '该评论回复已读完' : endState === 'blocked' ? '核对页面后继续回复' : replies.length ? '继续读取回复（最多 100 条）' : '读取回复'}</Button>}
    </div>
    {unsupported && unsupportedCount > 0 && <p role="status" className="text-xs mt-2 text-amber-700">另有 {unsupportedCount} 条未识别内容未保存。</p>}
    {imagePlaceholderCount > 0 && <p role="status" className="text-xs mt-2 text-amber-700">已保存 {imagePlaceholderCount} 条含图片的回复标识，图片内容未读取。</p>}
    {upgrade && <p className="text-xs mt-2">已支持带名称的表情和图片标识，可补读旧任务；已有文字回复不会重复保存。</p>}
    {endState === 'blocked' && !reading && <p role="status" className="text-xs mt-2 text-amber-700">加载受阻或结束状态未确认，请核对页面后继续。</p>}
    {open && <div aria-label="此评论的回复" className="ml-3 mt-3 pl-3 border-l-2 border-cyan-500/30 space-y-3">
      <p className="text-xs text-cyber-text-secondary">回复第 {page + 1} 页 · 已保存 {replies.length} 条</p>
      {!replies.length && <p className="text-xs">暂无已保存回复；不代表页面没有回复。</p>}
      {replies.slice(page * 100, (page + 1) * 100).map(reply => {
        const user = users.find(u => u.id === reply.user_id)
        return <div key={reply.id} className="text-sm">{showUser ? <button className="author-button" onClick={() => showUser(user || { id: reply.user_id, nickname: '未展示昵称', profile_url: '' })}>回复 · {user?.nickname || '未展示昵称'}</button> : <p className="font-medium">回复 · {user?.nickname || '未展示昵称'}</p>}
          <CommentContent comment={reply} />
          {user?.profile_url && /^https:\/\/www\.douyin\.com\/user\/[A-Za-z0-9_.=-]+$/.test(user.profile_url) && <a className="text-xs underline text-cyan-700" href={user.profile_url} target="_blank" rel="noreferrer">查看回复用户主页</a>}
        </div>
      })}
      <div className="flex gap-2">
        <Button size="sm" variant="outline" disabled={!page} onClick={() => setPage(p => p - 1)}>回复上一页</Button>
        <Button size="sm" variant="outline" disabled={(page + 1) * 100 >= replies.length} onClick={() => setPage(p => p + 1)}>回复下一页</Button>
      </div>
    </div>}
  </div>
}
