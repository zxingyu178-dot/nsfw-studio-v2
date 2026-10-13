/**
 * ImageLightbox.overscroll（Task 9 / §14.4）：
 * - .lb-overlay / .lb-stage 的 overscroll-behavior = none；
 * - .lb-side-wrap 的 overscroll-behavior = contain（信息栏可自己滚，但到顶/底不传导）；
 * - 信息栏上继续 wheel 不改变底层 .app-shell__main 的 scrollTop。
 * vitest 下 css:false（不真实加载样式），故同时读 CSS 源文本断言规则存在。
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { cleanup, render } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { ImageLightbox } from '../ImageLightbox'
import type { ImageDTO } from '../../types/workbench'

const images: Pick<ImageDTO, 'id' | 'width' | 'height' | 'kind'>[] = [
  { id: 'img_a', width: 800, height: 600, kind: 'original' },
]

// vitest 以 frontend/ 为 cwd 运行
const css = readFileSync('src/components/ImageLightbox.css', 'utf-8')

function block(selector: string): string {
  const re = new RegExp(`${selector.replace('.', '\\.')}\\s*\\{([^}]*)\\}`)
  const m = css.match(re)
  return m ? m[1] : ''
}

function getMain(): HTMLElement {
  return document.querySelector<HTMLElement>('.app-shell__main') as HTMLElement
}

beforeEach(() => {
  const main = document.createElement('div')
  main.className = 'app-shell__main'
  document.body.appendChild(main)
  main.scrollTop = 500
})

afterEach(() => {
  cleanup()
  document.querySelector('.app-shell__main')?.remove()
})

describe('ImageLightbox overscroll-behavior', () => {
  it('CSS：.lb-overlay 与 .lb-stage 为 none，.lb-side-wrap 为 contain', () => {
    expect(block('.lb-overlay')).toMatch(/overscroll-behavior:\s*none/)
    expect(block('.lb-stage')).toMatch(/overscroll-behavior:\s*none/)
    expect(block('.lb-side-wrap')).toMatch(/overscroll-behavior:\s*contain/)
  })

  it('信息栏渲染为 .lb-side-wrap，且其上 wheel 不传导到底层 scrollTop', () => {
    const { container } = render(
      <ImageLightbox
        images={images}
        index={0}
        onClose={() => {}}
        onNavigate={() => {}}
        renderSidePanel={() => <div data-testid="side-panel">PANEL</div>}
      />,
    )
    const sideWrap = container.querySelector('.lb-side-wrap') as HTMLElement
    expect(sideWrap).toBeTruthy()

    for (let i = 0; i < 5; i += 1) {
      sideWrap.dispatchEvent(
        new WheelEvent('wheel', { bubbles: true, cancelable: true, deltaY: 100 }),
      )
    }
    expect(getMain().scrollTop).toBe(500)
  })
})
