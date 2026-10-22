import { useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { TopNav } from '../components/TopNav'
import { ResumeInterruptedPrompt } from '../components/ResumeInterruptedPrompt'
import { startJobStore, stopJobStore } from '../stores/jobStore'

export function MainLayout() {
  // 应用级任务流：SSE 实时通知 + 兜底轮询（§二十三）
  useEffect(() => {
    startJobStore()
    return () => stopJobStore()
  }, [])

  const location = useLocation()
  // Generate 工作台：从根上禁止 main 撑长（overflow:hidden），整页不滚动，
  // 三栏/单栏在 body 内各自滚动。其它路由保持 main 默认纵向文档滚动。
  const isWorkspace = location.pathname.startsWith('/generate')

  return (
    <div className="app-shell">
      <ResumeInterruptedPrompt />
      <TopNav />
      <main
        className={`app-shell__main${isWorkspace ? ' app-shell__main--workspace' : ''}`.trim()}
      >
        <Outlet />
      </main>
    </div>
  )
}
