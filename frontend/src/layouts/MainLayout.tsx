import { useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { NavigationRail, TopNav } from '../components/TopNav'
import { ResumeInterruptedPrompt } from '../components/ResumeInterruptedPrompt'
import { startJobStore, stopJobStore } from '../stores/jobStore'

export function MainLayout() {
  useEffect(() => {
    startJobStore()
    return () => stopJobStore()
  }, [])

  const { pathname } = useLocation()
  const isWorkspace = pathname.startsWith('/generate')

  return (
    <div className="app-shell">
      <ResumeInterruptedPrompt />
      <NavigationRail />
      <div className="app-shell__body">
        <TopNav />
        <main className={'app-shell__main' + (isWorkspace ? ' app-shell__main--workspace' : '')}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}
