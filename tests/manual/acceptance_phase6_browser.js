/**
 * Phase 6 Task11：浏览器人工验收（Playwright + 系统 Edge，复用 art-museum 已装依赖，零下载）。
 *
 * 真实 UI 全链路（对真实后端 8000 + 真实 DataRoot + 真实 ComfyUI）：
 *   文生图 → 图片生成（图库导入外部照片 → 图库选择）→ Img2Img(+高清) → Gallery
 *   → History → 从 processed/upscaled 恢复工作台 → Recipe 保存/重开 → 切回文生图
 *
 * 每步截图存 docs/evidence/phase6-img2img/screenshots/，结果汇总到 acceptance_browser.json
 *
 * 用法（项目根目录；需后端 8000 + 前端 5173 已运行）：
 *   node tests/manual/acceptance_phase6_browser.js
 */
const fs = require('fs')
const path = require('path')
const { chromium } = require('D:/AIHome_2.0_L1_L2/projects/art-museum/node_modules/playwright')

const BASE = 'http://localhost:5173'
const OUT_DIR = path.resolve('docs/evidence/phase6-img2img')
const SHOTS = path.join(OUT_DIR, 'screenshots')
const PHOTO = path.join(OUT_DIR, 'inputs', 'real_photo_768x1024.png')

const results = []
const consoleErrors = []

function record(step, ok, detail = {}) {
  results.push({ step, ok, detail })
  console.log(`[${ok ? 'OK' : 'FAIL'}] ${step}${ok ? '' : ' :: ' + JSON.stringify(detail)}`)
}

async function shot(page, name) {
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true })
}

async function apiJson(page, url) {
  return page.evaluate(async (u) => {
    const res = await fetch(u)
    return res.ok ? res.json() : { __status: res.status }
  }, url)
}

async function waitJobDone(page, jobId, timeoutMs = 2700000) {
  const deadline = Date.now() + timeoutMs
  let last = {}
  while (Date.now() < deadline) {
    last = await apiJson(page, `/api/v1/jobs/${jobId}`)
    if (['COMPLETED', 'FAILED', 'CANCELLED', 'INTERRUPTED'].includes(last.status)) return last
    await page.waitForTimeout(4000)
  }
  return last
}

async function latestJob(page) {
  const page1 = await apiJson(page, '/api/v1/jobs?limit=1')
  return page1.items && page1.items[0] ? page1.items[0] : null
}

;(async () => {
  fs.mkdirSync(SHOTS, { recursive: true })
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  const context = await browser.newContext({ viewport: { width: 1500, height: 1000 }, locale: 'zh-CN' })
  const page = await context.newPage()
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text().slice(0, 300))
  })
  page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${String(err).slice(0, 300)}`))

  try {
    // ===== 1) 文生图 =====
    await page.goto(`${BASE}/generate`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('section.workbench', { timeout: 20000 })
    const textTabActive = await page.locator('.workbench__modebar button.segmented__item', { hasText: '文生图' })
      .evaluate((el) => el.getAttribute('aria-selected'))
    const sizeVisible = await page.locator('#size-width').isVisible()
    record('① 初始：文生图 + 显式宽高', textTabActive === 'true' && sizeVisible,
      { textTabActive, sizeVisible })
    await shot(page, '01_generate_text_mode')

    await page.fill('#field-style', 'photorealistic photo, cinematic')
    await page.fill('#field-scene', 'quiet library interior, warm lamp light')
    await page.fill('#negative-prompt', 'blurry, low quality, text, watermark')
    await page.fill('#size-width', '512')
    await page.locator('#size-height').click()
    await page.fill('#size-height', '512')
    await page.locator('#gen-count').click() // 触发 blur 提交尺寸
    await page.locator('.generate-actions__main').click()
    await page.waitForSelector('.notice--ok', { timeout: 20000 })
    const textNotice = await page.locator('.notice--ok').first().textContent()
    const textJob = await latestJob(page)
    record('① 文生图提交', Boolean(textJob && textJob.id), { notice: textNotice, job: textJob && textJob.id })
    await shot(page, '02_text_submitted')

    const textFinal = await waitJobDone(page, textJob.id)
    record('① 文生图完成', textFinal.status === 'COMPLETED',
      { status: textFinal.status, error: textFinal.error_message })
    await page.reload({ waitUntil: 'domcontentloaded' })
    await shot(page, '03_text_completed')

    // ===== 2) 图库导入外部照片 =====
    await page.goto(`${BASE}/gallery`, { waitUntil: 'domcontentloaded' })
    await page.locator('button', { hasText: /^导入$/ }).first().click()
    await page.locator('input[type=file]').setInputFiles(PHOTO)
    await page.waitForTimeout(2500)
    await shot(page, '04_gallery_import')

    // ===== 3) 图片生成：从图库选择照片（图生图） =====
    await page.goto(`${BASE}/generate`, { waitUntil: 'domcontentloaded' })
    await page.locator('.workbench__modebar button.segmented__item', { hasText: '图片生成' }).click()
    await page.locator('button', { hasText: '从图库选择' }).click()
    await page.waitForTimeout(1200)
    await shot(page, '05_image_picker')
    // 选择器中的第一张卡片（最新导入的照片）
    await page.locator('.drawer .gallery-card, .drawer button:has(img)').first().click()
    await page.waitForTimeout(1200)

    const imgMode = await page.locator('.workbench__modebar button.segmented__item', { hasText: '图片生成' })
      .evaluate((el) => el.getAttribute('aria-selected'))
    const thumbVisible = await page.locator('.input-image__thumb').isVisible().catch(() => false)
    const followsInput = await page.getByText('跟随输入图（无需设置宽高）').isVisible().catch(() => false)
    const denoise = await page.locator('#param-denoise').inputValue().catch(() => null)
    const widthHidden = !(await page.locator('#size-width').isVisible().catch(() => false))
    record('② 图片模式：输入图 + 跟随输入图 + denoise 滑杆 + 无假宽高',
      imgMode === 'true' && thumbVisible && followsInput && denoise === '0.8' && widthHidden,
      { imgMode, thumbVisible, followsInput, denoise, widthHidden })
    await shot(page, '06_img2img_mode')

    // 填写图片生成 Prompt（外部导入图 → Prompt 为空的第一版语义）
    await page.fill('#field-style', 'photorealistic photo, cinematic')
    await page.fill('#field-scene', 'sunlit cafe by the window, blurred city street behind glass')
    await page.fill('#negative-prompt', 'blurry, low quality, text, watermark')

    // 开启高清 → 提交
    await page.locator('.workflow-modules input[type=checkbox]').check()
    await shot(page, '07_upscale_on')
    await page.locator('.generate-actions__main').click()
    await page.waitForSelector('.notice--ok', { timeout: 20000 })
    const imgJob = await latestJob(page)
    record('② Img2Img(+高清) 提交', Boolean(imgJob && imgJob.id),
      { job: imgJob && imgJob.id, modules: imgJob && imgJob.workflow_snapshot.modules.map((m) => m.module_id) })
    await shot(page, '08_img2img_submitted')

    const imgFinal = await waitJobDone(page, imgJob.id)
    record('② Img2Img(+高清) 完成', imgFinal.status === 'COMPLETED',
      { status: imgFinal.status, error: imgFinal.error_message })

    // ===== 4) Gallery：查看 processed / upscaled =====
    await page.goto(`${BASE}/gallery?job=${imgJob.id}`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(1500)
    const kinds = await page.locator('.gallery-card__badges').allTextContents()
    record('③ Gallery 产出（processed + HD）', kinds.length >= 2, { badges: kinds })
    await shot(page, '09_gallery_job')

    // ===== 5) History → 打开工作台（从 upscaled 恢复 img2img 上下文） =====
    await page.goto(`${BASE}/prompts`, { waitUntil: 'domcontentloaded' })
    await page.locator('button', { hasText: '历史' }).first().click()
    await page.waitForTimeout(1500)
    await shot(page, '10_history')
    await page.locator('.history-card').first().click()
    await page.waitForTimeout(1000)
    await page.locator('button', { hasText: '在生成工作台打开' }).click()
    await page.waitForTimeout(1500)
    const restoredMode = await page.locator('.workbench__modebar button.segmented__item', { hasText: '图片生成' })
      .evaluate((el) => el.getAttribute('aria-selected'))
    const restoredDenoise = await page.locator('#param-denoise').inputValue().catch(() => null)
    const restoredPrompt = await page.locator('#field-scene').inputValue().catch(() => '')
    record('④ 从 History 恢复：图片模式 + denoise + Prompt',
      restoredMode === 'true' && restoredDenoise === '0.8' && restoredPrompt.includes('cafe'),
      { restoredMode, restoredDenoise, restoredPrompt })
    await shot(page, '11_restored_workbench')

    // ===== 6) 从 upscaled 图直接恢复（Gallery → 在生成工作台中打开） =====
    const jobImages = await apiJson(page, `/api/v1/images?job_id=${imgJob.id}&limit=50`)
    const upscaledImg = (jobImages.items || []).find((im) => im.kind === 'upscaled')
    let upscaledRestore = { ok: false, reason: 'no upscaled image' }
    if (upscaledImg) {
      await page.goto(`${BASE}/gallery?job=${imgJob.id}`, { waitUntil: 'domcontentloaded' })
      await page.waitForSelector('button.gallery-card', { timeout: 15000 })
      await page.waitForTimeout(800)
      // 按 image_id 精确定位高清图卡片（避免抽屉遮挡后循环点击失败）
      await page.locator(`button.gallery-card:has(img[src*="${upscaledImg.id}/content"])`).click()
      await page.waitForTimeout(1000)
      await page.locator('button', { hasText: '在生成工作台中打开' }).click({ timeout: 15000 })
      await page.waitForTimeout(1500)
      const mode = await page.locator('.workbench__modebar button.segmented__item', { hasText: '图片生成' })
        .evaluate((el) => el.getAttribute('aria-selected'))
      const denoiseVal = await page.locator('#param-denoise').inputValue().catch(() => null)
      const inputThumb = await page.locator('.input-image__thumb').isVisible().catch(() => false)
      upscaledRestore = {
        ok: mode === 'true' && denoiseVal === '0.8' && inputThumb,
        mode, denoiseVal, inputThumb, imageId: upscaledImg.id,
      }
    }
    record('④ 从高清图恢复工作台（Task1：恢复 Img2Img 而非导入图）', upscaledRestore.ok, upscaledRestore)
    await shot(page, '12_restored_from_upscaled')

    // ===== 7) Recipe 保存 / 重开 =====
    await page.locator('button', { hasText: '保存为配方' }).click()
    await page.fill('#save-name', 'Phase6 浏览器验收配方')
    await page.locator('.modal button', { hasText: /^保存$/ }).click()
    await page.waitForSelector('.notice--ok', { timeout: 15000 })
    await shot(page, '13_recipe_saved')
    await page.goto(`${BASE}/prompts`, { waitUntil: 'domcontentloaded' })
    await page.locator('button', { hasText: '配方' }).first().click()
    await page.waitForTimeout(1200)
    await page.locator('.card--clickable', { hasText: 'Phase6 浏览器验收配方' }).first().click()
    await page.waitForTimeout(1200)
    await shot(page, '14_recipe_reopen')

    // ===== 8) 切回文生图 =====
    await page.goto(`${BASE}/generate`, { waitUntil: 'domcontentloaded' })
    await page.locator('.workbench__modebar button.segmented__item', { hasText: '文生图' }).click()
    await page.waitForTimeout(800)
    const backText = await page.locator('.workbench__modebar button.segmented__item', { hasText: '文生图' })
      .evaluate((el) => el.getAttribute('aria-selected'))
    const backSize = await page.locator('#size-width').isVisible()
    record('⑤ 切回文生图：基础生成 + 宽高回归', backText === 'true' && backSize, { backText, backSize })
    await shot(page, '15_back_to_text')
  } catch (error) {
    record('执行异常', false, { error: String(error && error.message ? error.message : error) })
    await shot(page, '99_error').catch(() => {})
  } finally {
    fs.writeFileSync(path.join(OUT_DIR, 'acceptance_browser.json'), JSON.stringify({
      generated_at: new Date().toISOString(),
      console_errors: consoleErrors,
      results,
    }, null, 2), 'utf-8')
    await browser.close()
  }

  const failed = results.filter((r) => !r.ok).map((r) => r.step)
  console.log(`\n${failed.length === 0 ? 'ALL PASS' : 'FAILED: ' + failed.join(' | ')}`)
  console.log(`console errors: ${consoleErrors.length}`)
  process.exit(failed.length === 0 ? 0 : 1)
})()