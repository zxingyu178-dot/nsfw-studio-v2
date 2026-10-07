import { Navigate, Route, Routes } from 'react-router-dom'
import { MainLayout } from '../layouts/MainLayout'
import GeneratePage from '../pages/Generate/GeneratePage'
import GalleryPage from '../pages/Gallery/GalleryPage'
import PromptPage from '../pages/Prompt/PromptPage'
import AssetsPage from '../pages/Assets/AssetsPage'
import SettingsPage from '../pages/Settings/SettingsPage'

export default function App() {
  return (
    <Routes>
      <Route element={<MainLayout />}>
        <Route path="/" element={<Navigate to="/generate" replace />} />
        <Route path="/generate" element={<GeneratePage />} />
        <Route path="/gallery" element={<GalleryPage />} />
        <Route path="/prompts" element={<PromptPage />} />
        <Route path="/assets" element={<AssetsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/generate" replace />} />
      </Route>
    </Routes>
  )
}
