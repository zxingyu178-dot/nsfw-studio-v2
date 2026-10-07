import { Outlet } from 'react-router-dom'
import { TopNav } from '../components/TopNav'

export function MainLayout() {
  return (
    <div className="app-shell">
      <TopNav />
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  )
}
