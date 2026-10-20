/**
 * 仓库卫生守卫：关键 JSON / YAML 文件不得带 UTF-8 BOM。
 *
 * 背景：Windows 工具链（PowerShell Set-Content -Encoding UTF8 等）容易写入 BOM；
 * Vite 读取 frontend/package.json 作为 PostCSS 配置入口，BOM 会导致
 * "Failed to load PostCSS config: Unexpected token '﻿'" 并让前端 CI 直接失败。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const BOM = [0xef, 0xbb, 0xbf]

function startsWithBom(path: string): boolean {
  const bytes = readFileSync(path)
  return bytes.length >= 3 && bytes[0] === BOM[0] && bytes[1] === BOM[1] && bytes[2] === BOM[2]
}

describe('仓库卫生：无 BOM', () => {
  it('frontend/package.json 不带 BOM（Vite/PostCSS 配置入口）', () => {
    expect(startsWithBom(resolve(process.cwd(), 'package.json'))).toBe(false)
  })

  it('configs/app.yaml 不带 BOM（后端配置解析）', () => {
    expect(startsWithBom(resolve(process.cwd(), '..', 'configs', 'app.yaml'))).toBe(false)
  })

  it('backend/app/__init__.py 不带 BOM', () => {
    expect(startsWithBom(resolve(process.cwd(), '..', 'backend', 'app', '__init__.py'))).toBe(false)
  })
})
