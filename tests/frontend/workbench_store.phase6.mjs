#!/usr/bin/env node
/**
 * Phase 6 前端 store 回归（零新增依赖）。
 *
 * 用 frontend 已安装的 vite 以 SSR 方式加载**真实** workbenchStore.ts，
 * 锁定运行时行为（类型正确性由 npm run build 的 tsc 承担）：
 *
 * - Task2：pinned upscale / img2img 完整身份 hydrate → setModuleCatalog → snapshot
 *   双 hash / config 完全不丢；normalizeModules 不再重建裸 {module_id:'upscale'}；
 * - Task7：generation_mode 明确恢复（无该字段时按 input_images 推断）。
 *
 * 运行：frontend 目录 `npm run test:store`（或任意目录 node tests/frontend/workbench_store.phase6.mjs）。
 */
import assert from 'node:assert/strict'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../frontend')
const { createServer } = await import(
  pathToFileURL(path.join(frontendDir, 'node_modules/vite/dist/node/index.js')).href
)

const server = await createServer({
  root: frontendDir,
  logLevel: 'error',
  server: { middlewareMode: true },
  appType: 'custom',
})

let passed = 0
const failures = []

async function run(name, fn) {
  try {
    await fn()
    passed += 1
    console.log(`  ok - ${name}`)
  } catch (error) {
    failures.push({ name, error })
    console.error(`  FAIL - ${name}\n    ${error?.message ?? error}`)
  }
}

/** 测试用能力目录（只含 store 需要的字段） */
const CATALOG = [
  { module_id: 'basic_generate', available: true, input_required: false, output_kind: 'original' },
  { module_id: 'img2img', available: true, input_required: true, output_kind: 'processed' },
  { module_id: 'upscale', available: true, input_required: false, output_kind: 'upscaled' },
]

const PINNED_BASIC = {
  module_id: 'basic_generate',
  module_version: 'v1',
  provider: 'mock',
  binding_version: 'v1',
  workflow_hash: 'wfh_basic',
  binding_hash: 'bnh_basic',
  config: {},
}
const PINNED_IMG2IMG = {
  module_id: 'img2img',
  module_version: 'v1',
  provider: 'comfyui',
  binding_version: 'v1',
  workflow_hash: 'wfh_img2img',
  binding_hash: 'bnh_img2img',
  config: { denoise: 0.55 },
}
const PINNED_UPSCALE = {
  module_id: 'upscale',
  module_version: 'v1',
  provider: 'comfyui',
  binding_version: 'v1',
  workflow_hash: 'wfh_upscale',
  binding_hash: 'bnh_upscale',
  config: {},
}

function makeSnapshot(overrides = {}) {
  return {
    prompt_mode: 'structured',
    structured_prompt: { style: 'anime', scene: 'cafe' },
    full_prompt: '',
    negative_prompt: 'blurry',
    selected_assets: {},
    input_images: [],
    width: 512,
    height: 768,
    count: 1,
    seed_mode: 'random',
    seed: null,
    workflow_modules: [],
    source_prompt_id: null,
    source_prompt_version_id: null,
    ...overrides,
  }
}

try {
  const store = await server.ssrLoadModule('/src/stores/workbenchStore.ts')

  console.log('Phase 6 frontend store regression:')

  // ===== Task2：pinned upscale 完整身份（文生图恢复）不丢 =====
  await run('hydrate(text) 保留 pinned basic + pinned upscale 完整身份', () => {
    store.resetWorkbench()
    store.hydrateWorkbench(makeSnapshot({
      workflow_modules: [PINNED_BASIC, PINNED_UPSCALE],
    }))
    const state = store.getWorkbenchState()
    assert.equal(state.mode, 'text')
    assert.equal(state.workflowModules.length, 2)
    assert.deepEqual(state.workflowModules[1], PINNED_UPSCALE,
      'Task2：禁止重建裸 {module_id:"upscale"}，双 hash / config 必须原样保留')
    assert.deepEqual(state.workflowModules[0], PINNED_BASIC)
  })

  await run('setModuleCatalog 后身份仍不丢；snapshot 双 hash / config 完全一致', () => {
    store.setModuleCatalog(CATALOG)
    let state = store.getWorkbenchState()
    assert.deepEqual(state.workflowModules[1], PINNED_UPSCALE,
      'Task2：目录到达后 normalizeModules 不得破坏 pinned upscale')
    const snapshot = store.snapshotFromState()
    assert.deepEqual(snapshot.workflow_modules, [PINNED_BASIC, PINNED_UPSCALE])
    assert.deepEqual(snapshot.workflow_modules[1].config, {})
    assert.equal(snapshot.workflow_modules[1].workflow_hash, 'wfh_upscale')
    assert.equal(snapshot.workflow_modules[1].binding_hash, 'bnh_upscale')
    state = store.getWorkbenchState()
    assert.equal(state.mode, 'text')
  })

  // ===== Task2：图片生成恢复（img2img + pinned upscale）身份不丢 =====
  await run('hydrate(image) 保留 pinned img2img（含 denoise）+ pinned upscale', () => {
    store.resetWorkbench()
    store.setModuleCatalog(CATALOG)
    store.hydrateWorkbench(makeSnapshot({
      input_images: [{ role: 'source', image_id: 'img_0001' }],
      workflow_modules: [PINNED_IMG2IMG, PINNED_UPSCALE],
    }))
    const state = store.getWorkbenchState()
    assert.equal(state.mode, 'image')
    assert.deepEqual(state.workflowModules[0], PINNED_IMG2IMG)
    assert.deepEqual(state.workflowModules[1], PINNED_UPSCALE)
    const snapshot = store.snapshotFromState()
    assert.deepEqual(snapshot.input_images, [{ role: 'source', image_id: 'img_0001' }])
    assert.deepEqual(snapshot.workflow_modules[0].config, { denoise: 0.55 })
    assert.equal(snapshot.workflow_modules[0].binding_hash, 'bnh_img2img')
    assert.equal(snapshot.workflow_modules[1].binding_hash, 'bnh_upscale')
    assert.equal(state.workflowModules[0].module_version, 'v1')
  })

  await run('模块不可用（目录未就绪）时也绝不静默丢身份 / 降级', () => {
    store.resetWorkbench()
    store.setModuleCatalog([]) // 模拟 /modules 尚未加载或全部不可用
    store.hydrateWorkbench(makeSnapshot({
      input_images: [{ role: 'source', image_id: 'img_0001' }],
      workflow_modules: [PINNED_IMG2IMG, PINNED_UPSCALE],
    }))
    const state = store.getWorkbenchState()
    // catalog 为空：无法确认可用性 → 保留现状（Gate 阻止提交，而不是换成 basic_generate）
    assert.deepEqual(state.workflowModules[0], PINNED_IMG2IMG)
    assert.deepEqual(state.workflowModules[1], PINNED_UPSCALE)
    assert.equal(store.isImageCapablePrimary(state), false, 'Gate：目录未就绪时不得判定可提交')
  })

  // ===== Task2：只有用户手动开启高清才创建裸 upscale =====
  await run('手动开启/关闭高清：仅裸 {module_id:"upscale"}，其余模块身份保留', () => {
    store.resetWorkbench()
    store.setModuleCatalog(CATALOG)
    store.hydrateWorkbench(makeSnapshot({ workflow_modules: [PINNED_BASIC] }))
    store.setUpscaleEnabled(true)
    let state = store.getWorkbenchState()
    assert.deepEqual(state.workflowModules.map((m) => m.module_id), ['basic_generate', 'upscale'])
    assert.deepEqual(state.workflowModules[1], { module_id: 'upscale' }, '首次手动开启 = 裸模块，由后端解析身份')
    assert.deepEqual(state.workflowModules[0], PINNED_BASIC)
    store.setUpscaleEnabled(false)
    state = store.getWorkbenchState()
    assert.deepEqual(state.workflowModules.map((m) => m.module_id), ['basic_generate'])
    assert.deepEqual(state.workflowModules[0], PINNED_BASIC)
  })

  // ===== Task7：generation_mode 以显式字段为准（无字段时向后兼容推断）=====
  await run('generation_mode=image 且暂无输入图 → 仍保持图片模式（不回落文生图）', () => {
    store.resetWorkbench()
    store.setModuleCatalog(CATALOG)
    store.hydrateWorkbench(makeSnapshot({
      generation_mode: 'image',
      input_images: [],
      workflow_modules: [PINNED_IMG2IMG],
    }))
    const state = store.getWorkbenchState()
    assert.equal(state.mode, 'image', '显式 generation_mode 优先于 input_images 推断')
    assert.deepEqual(state.workflowModules[0], PINNED_IMG2IMG)
    assert.equal(store.snapshotFromState().generation_mode, 'image')
  })

  await run('generation_mode=text 携带（历史）输入图 → 保持文生图', () => {
    store.resetWorkbench()
    store.setModuleCatalog(CATALOG)
    store.hydrateWorkbench(makeSnapshot({
      generation_mode: 'text',
      input_images: [{ role: 'source', image_id: 'img_stale' }],
      workflow_modules: [PINNED_BASIC],
    }))
    const state = store.getWorkbenchState()
    assert.equal(state.mode, 'text')
    assert.equal(store.snapshotFromState().generation_mode, 'text')
  })

  await run('旧快照（无 generation_mode）+ 输入图 → 仍按 input_images 推断 image', () => {
    store.resetWorkbench()
    store.setModuleCatalog(CATALOG)
    store.hydrateWorkbench(makeSnapshot({
      input_images: [{ role: 'source', image_id: 'img_legacy' }],
      workflow_modules: [PINNED_IMG2IMG],
    }))
    assert.equal(store.getWorkbenchState().mode, 'image')
  })
} finally {
  await server.close()
}

console.log(`\n${passed} passed, ${failures.length} failed`)
if (failures.length > 0) {
  process.exit(1)
}