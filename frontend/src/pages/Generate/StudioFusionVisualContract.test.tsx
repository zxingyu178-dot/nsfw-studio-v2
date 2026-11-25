import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import GeneratePage from './GeneratePage'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('no backend'))))
})

describe('Studio 原型融合视觉契约', () => {
  it('为创作工作区、画布与任务控制台提供稳定的语义表面', () => {
    const { container } = render(
      <MemoryRouter>
        <GeneratePage />
      </MemoryRouter>,
    )

    expect(container.querySelector('.generate--studio-fusion')).not.toBeNull()
    expect(container.querySelector('[aria-label="创作工作区"]')).not.toBeNull()
    expect(container.querySelector('[aria-label="创作画布"]')).not.toBeNull()
    expect(container.querySelector('[aria-label="任务控制台"]')).not.toBeNull()
  })

  it('以画布为焦点，并用紧凑平面承载两侧控制与真实队列', () => {
    const css = readFileSync(resolve(process.cwd(), 'src/pages/Generate/generate.css'), 'utf8')

    expect(css).toMatch(/\.generate--studio-fusion\s*\{[^}]*background:\s*var\(--bg\)/)
    expect(css).toMatch(/\.generate--studio-fusion\s+\.wb4-center\s*\{[^}]*padding:/)
    expect(css).toMatch(/\.generate--studio-fusion\s+\.wb4-stage\s*\{[^}]*border-radius:/)
    expect(css).toMatch(/\.generate--studio-fusion\s+\.wb4-dock__body\s*\{[^}]*grid-template-columns:/)
  })
})
