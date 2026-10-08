// Phase 5.1 Task6 前端工作台 store 逻辑验证（无测试框架依赖，esbuild 打包后由 node 执行）。
// 运行方式见 temp/experimental/frontend_store_check/run.ps1（或手工两条命令）。
import {
  availableImageModuleIds,
  getWorkbenchState,
  hydrateWorkbench,
  isImageCapablePrimary,
  resetWorkbench,
  setInputImage,
  setModuleCatalog,
  setPrimaryModuleConfig,
  setUpscaleEnabled,
  setWorkbenchMode,
  snapshotFromState,
} from '../../../frontend/src/stores/workbenchStore'
import type { ModuleCapabilitiesDTO } from '../../../frontend/src/types/workbench'

function capabilities(
  module_id: string,
  overrides: Partial<ModuleCapabilitiesDTO> = {},
): ModuleCapabilitiesDTO {
  return {
    module_id,
    module_version: 'v1',
    title: module_id,
    description: '',
    uses_seed: true,
    input_kind: 'none',
    input_required: false,
    input_role: 'source',
    output_kind: 'original',
    parent_policy: 'none',
    output_cardinality: 1,
    registered: true,
    available: true,
    provider: 'mock',
    binding_version: 'v1',
    unavailable_reason: null,
    ...overrides,
  }
}

const catalog: ModuleCapabilitiesDTO[] = [
  capabilities('basic_generate'),
  capabilities('img2img', {
    title: '图生图', input_kind: 'image', input_required: true,
    output_kind: 'processed', parent_policy: 'input_image',
  }),
  capabilities('upscale', {
    uses_seed: false, input_kind: 'image', input_required: true, output_kind: 'upscaled',
  }),
]

let failures = 0
function check(name: string, condition: boolean): void {
  console.log(`${condition ? 'PASS' : 'FAIL'} ${name}`)
  if (!condition) failures += 1
}

// 1) 初始：文生图 primary = basic_generate
resetWorkbench()
setModuleCatalog(catalog)
check('初始为文生图 + basic_generate',
  getWorkbenchState().mode === 'text' &&
  getWorkbenchState().workflowModules[0].module_id === 'basic_generate')

// 2) 切到图片生成 → primary 自动切到可用图片模块 img2img
setWorkbenchMode('image')
check('图片模式 primary=img2img',
  getWorkbenchState().workflowModules[0].module_id === 'img2img')

// 3) 切回文生图 → primary 切回 basic_generate，且 upscale 状态保留
setUpscaleEnabled(true)
setWorkbenchMode('text')
check('文生图切回 basic_generate + upscale 保留',
  getWorkbenchState().workflowModules.map((m) => m.module_id).join(',') === 'basic_generate,upscale')

// 4) 选择输入图片 → 自动进入图片生成模式 + img2img
setInputImage('img_source_1')
check('选择输入图 → mode=image + primary=img2img',
  getWorkbenchState().mode === 'image' &&
  getWorkbenchState().workflowModules[0].module_id === 'img2img' &&
  snapshotFromState().input_images?.length === 1)

// 5) denoise 写入 Primary Module config → 进入快照
setPrimaryModuleConfig({ denoise: 0.55 })
check('primary config(denoise) 进入快照',
  snapshotFromState().workflow_modules[0].config?.denoise === 0.55)

// 6) 历史/配方恢复：img2img 完整执行身份（双指纹）在可用时 100% 保留
resetWorkbench()
setModuleCatalog(catalog)
hydrateWorkbench({
  prompt_mode: 'structured',
  structured_prompt: { style: '', face: '', clothing: '', pose: '', scene: '', composition: '', lighting: '', extra: '' },
  full_prompt: '', negative_prompt: '', selected_assets: {},
  width: 1024, height: 1024, count: 1, seed_mode: 'random',
  input_images: [{ role: 'source', image_id: 'img_source_1' }],
  workflow_modules: [{
    module_id: 'img2img', module_version: 'v1', provider: 'comfyui',
    binding_version: 'v1', workflow_hash: 'wfh_1', binding_hash: 'bnh_1',
    config: { denoise: 0.7 },
  }],
})
const restored = getWorkbenchState().workflowModules[0]
check('恢复 img2img 完整身份 + config 原样保留',
  restored.module_version === 'v1' && restored.workflow_hash === 'wfh_1' &&
  restored.binding_hash === 'bnh_1' && restored.config?.denoise === 0.7)

// 7) Task7 Gate：img2img 不可用（available=false）→ 不能被当作可用图片模块
resetWorkbench()
setModuleCatalog(catalog.map((m) => (m.module_id === 'img2img' ? { ...m, available: false } : m)))
check('available=false → 图片模块列表为空（Gate 关闭）',
  availableImageModuleIds(getWorkbenchState().moduleCatalog).length === 0)
setWorkbenchMode('image')
check('Gate 关闭时不会选中不可用模块',
  getWorkbenchState().workflowModules[0].module_id !== 'img2img' &&
  isImageCapablePrimary(getWorkbenchState()) === false)

// 8) 历史矛盾数据（basic_generate + 输入图）在模块可用时被校正为 img2img
resetWorkbench()
setModuleCatalog(catalog)
hydrateWorkbench({
  prompt_mode: 'structured',
  structured_prompt: { style: '', face: '', clothing: '', pose: '', scene: '', composition: '', lighting: '', extra: '' },
  full_prompt: '', negative_prompt: '', selected_assets: {},
  width: 1024, height: 1024, count: 1, seed_mode: 'random',
  input_images: [{ role: 'source', image_id: 'img_source_1' }],
  workflow_modules: [{ module_id: 'basic_generate' }],
})
check('历史矛盾数据 → 校正为可用 img2img（禁止图片模式+basic_generate）',
  getWorkbenchState().workflowModules[0].module_id === 'img2img')

console.log(failures === 0 ? '\nALL PASS' : `\n${failures} FAILED`)
process.exit(failures === 0 ? 0 : 1)