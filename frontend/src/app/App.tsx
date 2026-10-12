import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { MainLayout } from '../layouts/MainLayout'
import { PageContainer } from '../components/layout/Page'
import GeneratePage from '../pages/Generate/GeneratePage'
import GalleryPage from '../pages/Gallery/GalleryPage'
import PromptPage from '../pages/Prompt/PromptPage'
import AssetsPage from '../pages/Assets/AssetsPage'
import SettingsPage from '../pages/Settings/SettingsPage'

function RoutedPage({ width = 'normal', fill = false, children }: { width?: 'normal' | 'wide' | 'full'; fill?: boolean; children: ReactNode }) {
  return <PageContainer width={width} fill={fill}>{children}</PageContainer>
}

export default function App() {
  return (
    <Routes>
      <Route element={<MainLayout />}>
        <Route path="/" element={<Navigate to="/generate" replace />} />
        <Route path="/generate" element={<RoutedPage width="wide" fill><GeneratePage /></RoutedPage>} />
        <Route path="/gallery" element={<RoutedPage width="wide"><GalleryPage /></RoutedPage>} />
        <Route path="/prompts" element={<RoutedPage width="normal"><PromptPage /></RoutedPage>} />
        <Route path="/assets" element={<RoutedPage width="wide"><AssetsPage /></RoutedPage>} />
        <Route path="/settings" element={<RoutedPage width="normal"><SettingsPage /></RoutedPage>} />
        <Route path="*" element={<Navigate to="/generate" replace />} />
      </Route>
    </Routes>
  )
}
