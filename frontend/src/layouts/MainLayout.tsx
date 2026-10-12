import { useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import { TopNav } from '../components/TopNav'
import { startJobStore, stopJobStore } from '../stores/jobStore'

export function MainLayout() {
  // 应用级任务流：SSE 实时通知 + 兜底轮询（§二十三）
  useEffect(() => {
    startJobStore()
    return () => stopJobStore()
  }, [])

  return (
    <div className="app-shell">
      <TopNav />
      <main className="app-shell__main">
        <Outlet />
      </main>
    </div>
  )
}
