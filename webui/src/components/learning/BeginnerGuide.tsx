import * as Dialog from '@radix-ui/react-dialog'
import { BookOpen, Monitor, ExternalLink, X } from 'lucide-react'
import { Button } from '@/components/ui/button'

const chapters = [
  { title: '第一次启动', steps: [
    'Windows 电脑先安装 Python 3.12，再双击项目中的 start.cmd。首次启动会安装依赖，请等待窗口提示。',
    '在项目目录用 PowerShell 执行 ./install-browser.ps1，安装网页读取所需的 Chromium（首次需要）。',
    '打开 http://127.0.0.1:8765。看到“本地服务已连接”表示工作台服务正常，不代表已登录抖音。结束使用可双击 stop.cmd。',
  ] },
  { title: '登录抖音：先认准窗口', steps: [
    '首次使用，进入左侧“关注与私信”，点“打开浏览器登录”。这一步只打开抖音，不会关注或发送消息。',
    '在弹出的独立抖音浏览器中，用你自己的账号完成扫码或其他登录验证。不要在工作台右侧的同步画面上扫码操作或点击输入。',
    '回到工作台，点“我已登录，读取本人账号”，核对显示的抖音号。若仍要求登录，请回独立窗口检查是否真正完成。',
    '已有执行画面时，也可点画面下方“操作浏览器”切回原窗口。平时 Chrome、Edge 的登录与本工具独立；登录状态保存在本机，过期后需重新登录。',
  ] },
  { title: '第一次搜索与验证码', steps: [
    '进入“新建搜索”，输入关键词，点“开始网页读取”。正常会出现读取状态、数量进度，右侧显示浏览器同步画面。',
    '看到登录或验证码时先暂停任务，点“操作浏览器”，本人完成页面要求。不要连续点击开始，也不要新建重复任务。',
    '处理完成后，展开“辅助读取与导入”，点“继续读取当前搜索页”；工作台关键词须与抖音搜索页一致。',
    '完成后点“查看本次搜索结果”。每次最多 100 个视频，数量不足时会保留已取得的结果；平台可能不再提供更多或返回弱相关内容。',
  ] },
  { title: '查看视频、评论与用户', steps: [
    '点击视频行进入详情，有已存评论时先展示历史记录；没有时点“读取此视频评论”。长标题悬停可看全文。',
    '主评论每批最多 100 条；“下一批 100 条”继续读取，“上一页／下一页”只翻看已保存内容。受阻时处理页面后继续本批。',
    '评论下的“读取回复”单独读取该讨论。主评论已到底不等于全部回复已读完；图片可能仅有标识。',
    '点击评论作者查看用户详情；长评论点“展开全文”。已存视频、去重用户、已存评论可分别按任务或视频筛选。',
  ] },
  { title: '选择、导出、下载与删除', steps: [
    '先点列表上方“选择”，再勾选记录或全选；点“取消选择”清空并隐藏勾选框，切换筛选或分页也会退出选择模式。',
    '导出 CSV／JSON 保存已选数据。视频列表还可“批量下载视频”，在“视频下载”中查看逐条状态；真实抖音下载仍待验证，没有正常下载入口时会显示原因。',
    '删除前核对确认窗口中的记录和影响范围。运行中的任务需先暂停，删除功能没有回收站，重要数据先导出。',
  ] },
  { title: '关注与私信', steps: [
    '先读取本人账号，再填写获准测试的用户主页，选择关注或私信；私信要填写完整消息。',
    '点“核对账号与操作条件”仅预检查。仔细核对后，再在确认区执行一次；登录成功不代表目标允许接收私信。',
    '到“操作记录”查看结果。遇到结果不确定，先只读核对，避免重复关注或重复发送。同事需要自己的测试授权，不能沿用别人的授权。',
  ] },
]

export function BeginnerGuide() {
  return <Dialog.Root>
    <Dialog.Trigger asChild><Button variant="ghost" size="sm" className="guide-trigger"><BookOpen size={15} /><span>新手指南</span></Button></Dialog.Trigger>
    <Dialog.Portal>
      <Dialog.Overlay className="guide-overlay" />
      <Dialog.Content className="learning-shell beginner-guide">
        <header className="guide-heading"><div><Dialog.Title>新手指南</Dialog.Title><Dialog.Description>先登录自己的抖音账号，再开始第一次搜索。</Dialog.Description></div><Dialog.Close asChild><Button variant="ghost" size="icon" aria-label="关闭新手指南"><X size={18} /></Button></Dialog.Close></header>
        <div className="guide-body">
          <div className="guide-window-map" aria-label="两个窗口的区别（示意）">
            <div><Monitor size={20} /><strong>工作台</strong><p>发起任务、看进度、管理数据</p><small>右侧是同步画面，不可直接操作</small></div>
            <div><ExternalLink size={20} /><strong>独立抖音浏览器</strong><p>登录、输入、完成验证码</p><small>点“打开浏览器登录”或“操作浏览器”进入</small></div>
          </div>
          <p className="guide-tip">“本地服务已连接” ≠ “抖音已登录”。查看本指南不会启动任何任务。</p>
          {chapters.map((chapter, index) => <details key={chapter.title} className="guide-chapter" open={index === 1 ? true : undefined}><summary>{index + 1}. {chapter.title}</summary><ol>{chapter.steps.map(step => <li key={step}>{step}</li>)}</ol></details>)}
          <details className="guide-chapter"><summary>常见问题</summary><dl className="guide-faq">
            <dt>“操作浏览器”灰色或没有画面？</dt><dd>先到“关注与私信”点击“打开浏览器登录”。如果缺少浏览器，运行项目的 install-browser.ps1；画面延迟时以独立浏览器和任务日志为准。</dd>
            <dt>关闭后还要重新登录吗？</dt><dd>正常停止会保留本机数据与登录目录。账号过期、主动退出或清除登录目录后，需要重新登录。</dd>
            <dt>同事下载项目后为什么看不到我的数据？</dt><dd>交付包不带你的任务数据库和登录会话。同事首次使用应自行登录，不要把 learning_data、登录目录或验证码截图上传到 GitHub。</dd>
            <dt>失败了能一直点重试吗？</dt><dd>先看“任务日志”和独立浏览器，确认登录、验证或页面加载问题。关注、私信结果不确定时只核对记录，不重复执行。</dd>
          </dl></details>
        </div>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>
}
