import { useEffect, useState } from 'react'
import { viewNames } from './library'

export const pageNames = { overview: '工作台概览', keyword: '新建搜索', ...viewNames, 'task-logs': '任务日志', 'account-actions': '关注与私信' }
type Page = keyof typeof pageNames
function readRoute() {
  const [path, query = ''] = window.location.hash.slice(1).split('?')
  // Keep old bookmarked section URLs usable.
  const alias = path === 'task-results' ? 'tasks' : path === 'search-workspace' ? 'keyword' : path
  const page: Page = Object.prototype.hasOwnProperty.call(pageNames, alias) ? alias as Page : 'overview'
  return { page, task: Object.prototype.hasOwnProperty.call(viewNames, page) ? new URLSearchParams(query).get('task') || '' : '' }
}

export function useWorkbenchRoute() {
  const [route, setRoute] = useState(readRoute)
  useEffect(() => {
    const update = () => setRoute(readRoute())
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
  }, [])
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' })
    document.getElementById('main-content')?.focus({ preventScroll: true })
    document.title = pageNames[route.page] + ' · 抖音学习工作台'
  }, [route.page, route.task])
  function navigate(page: Page, task = '') {
    window.location.hash = page + (task ? '?' + new URLSearchParams({ task }).toString() : '')
  }
  return { route, navigate }
}

