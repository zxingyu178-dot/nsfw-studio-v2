import { describe, expect, it } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import SettingsPage from './SettingsPage'
import { ThemeProvider } from '../../themes/ThemeProvider'

function renderPage() {
  return render(
    <ThemeProvider>
      <SettingsPage />
    </ThemeProvider>
  )
}

describe('SettingsPage 设置', () => {
  it('渲染外观主题选择与关于面板', () => {
    renderPage()
    expect(screen.getByText('外观')).toBeInTheDocument()
    expect(screen.getByText('关于')).toBeInTheDocument()
    expect(screen.getByLabelText('深色')).toBeInTheDocument()
    expect(screen.getByLabelText('浅色')).toBeInTheDocument()
  })

  it('点击浅色主题可切换选中', () => {
    renderPage()
    const light = screen.getByLabelText('浅色') as HTMLInputElement
    fireEvent.click(light)
    expect(light.checked).toBe(true)
  })
})
