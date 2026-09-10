import type { Comment } from './ReplyThread'
import type { VideoInformation } from './VideoInfo'
export type View = 'tasks' | 'videos' | 'users' | 'comments'
export type SavedVideo = VideoInformation & { source: string; task_ids?: string[] }
export type SavedUser = { id: string; nickname?: string; profile_url?: string; source: string }
export type SavedComment = Comment & { video_id: string; source: string; task_ids?: string[]; create_time?: string | number; comment_rank?: number; reply_rank?: number }
export type HistoryTask = { id: string; keyword: string; source: string; status: string; note: string; created_at: string; counts: Record<string, number>; videos: SavedVideo[] }
export type Catalog = { tasks: HistoryTask[]; videos: SavedVideo[]; users: SavedUser[]; comments: SavedComment[] }
export const viewNames: Record<View, string> = { tasks: '累计任务', videos: '已存视频', users: '去重用户', comments: '已存评论' }
export const statusLabel: Record<string, string> = { running: '执行中', success: '成功', partial: '部分结果', search_exhausted: '页面已到底', search_stalled: '加载停滞', failed: '失败', cancelled: '已取消', needs_review: '需核对', waiting_login: '待登录', waiting_verification: '待验证', pending_layout: '待核对页面', blocked: '受阻', simulated: '内部样例' }
export function timeLabel(value?: string | number) {
  if (!value) return '未提供'
  const raw = /^\d+$/.test(String(value)) ? Number(value) : value
  const date = new Date(typeof raw === 'number' && raw < 1e12 ? raw * 1000 : raw)
  return Number.isNaN(date.getTime()) ? '未提供' : date.toLocaleString('zh-CN')
}
export const identity = (item: { source: string; id: string }) => JSON.stringify([item.source, item.id])
export const profileSafe = (url?: string) => !!url && /^https:\/\/www\.douyin\.com\/user\/[A-Za-z0-9_.=-]+$/.test(url)
export async function readLocal<T>(path: string): Promise<T> {
  const response = await fetch('/api/learning/' + path)
  if (!response.ok) throw new Error('读取本地记录失败，请稍后重试。')
  return response.json()
}
