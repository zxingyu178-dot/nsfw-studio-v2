import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { PromptTab } from './PromptTab'
import type { PromptDTO, PromptEvaluationDTO } from '../../types/workbench'

vi.mock('../../api/client', () => ({
  ApiRequestError: class extends Error {},
  promptApi: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    addVersion: vi.fn(),
    updateMeta: vi.fn(),
    archive: vi.fn(),
    restore: vi.fn(),
    listVersions: vi.fn(),
    restoreVersion: vi.fn(),
    setPreviewImage: vi.fn(),
    clearPreviewImage: vi.fn(),
    createEvaluation: vi.fn(),
    listEvaluations: vi.fn(),
    setStatus: vi.fn(),
  },
  imageApi: { list: vi.fn(), get: vi.fn() },
}))

function makeEvaluation(overrides: Partial<PromptEvaluationDTO> = {}): PromptEvaluationDTO {
  return {
    id: 'prev_1',
    prompt_id: 'prm_1',
    prompt_version_id: 'prmv_1',
    overall_score: 4,
    dimension_scores: { subject: 5, clothing: 4, scene: 4, composition: 4, lighting: 4, style: 4, quality: 4 },
    source: 'user',
    notes: '人物很稳',
    created_at: '2026-10-20T00:00:00Z',
    ...overrides,
  }
}

function makePrompt(overrides: Partial<PromptDTO> = {}): PromptDTO {
  return {
    id: 'prm_1',
    name: '测试 Prompt',
    favorite: false,
    archived: false,
    preview_image_id: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
    current_version: {
      id: 'prmv_1',
      prompt_id: 'prm_1',
      version_no: 1,
      mode: 'full',
      positive_prompt: 'masterpiece, 1girl',
      negative_prompt: 'blur',
      structured: { style: '', face: '', clothing: '', pose: '', scene: '', composition: '', lighting: '', extra: '' },
      created_at: '2026-01-01T00:00:00Z',
    },
    status: 'candidate',
    status_reason: '',
    ...overrides,
  }
}

async function mockList(prompts: PromptDTO[]) {
  const { promptApi } = await import('../../api/client')
  vi.mocked(promptApi.list).mockResolvedValue({
    items: prompts,
    total: prompts.length,
    limit: 50,
    offset: 0,
  } as never)
}

function renderTab() {
  return render(
    <MemoryRouter>
      <PromptTab />
    </MemoryRouter>,
  )
}

describe('Prompt 评分与手动淘汰（Phase 0.17.3）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('列表请求带上 include_evaluation', async () => {
    await mockList([makePrompt()])
    const { promptApi } = await import('../../api/client')
    renderTab()
    await waitFor(() => expect(promptApi.list).toHaveBeenCalled())
    expect(vi.mocked(promptApi.list).mock.calls[0][0]).toMatchObject({ include_evaluation: true })
  })

  it('卡片展示状态徽章与最近评分', async () => {
    await mockList([
      makePrompt({ status: 'keep', status_reason: '出图稳定', latest_evaluation: makeEvaluation() }),
    ])
    renderTab()

    expect(await screen.findByText('保留')).toBeInTheDocument()
    expect(screen.getByLabelText('最近评分 4 分（满分 5）')).toBeInTheDocument()
    expect(screen.getByText('出图稳定')).toBeInTheDocument()
  })

  it('无评分时不展示评分块，只提供“评分”入口', async () => {
    await mockList([makePrompt()])
    renderTab()
    await screen.findByText('测试 Prompt')
    expect(screen.queryByLabelText(/最近评分/)).toBeNull()
    expect(screen.getByRole('button', { name: '评分' })).toBeInTheDocument()
  })

  it('评分弹窗包含 7 个维度，保存时提交总分/维度/状态', async () => {
    const prompt = makePrompt()
    await mockList([prompt])
    const { promptApi } = await import('../../api/client')
    vi.mocked(promptApi.createEvaluation).mockResolvedValue(makeEvaluation() as never)
    vi.mocked(promptApi.setStatus).mockResolvedValue(prompt as never)

    renderTab()
    fireEvent.click(await screen.findByRole('button', { name: '评分' }))

    // 7 个维度都可见
    for (const label of ['人物', '服饰', '场景', '构图', '光影', '风格', '画质']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }

    fireEvent.click(screen.getByRole('button', { name: '人物评分 5 分' }))
    fireEvent.click(screen.getByRole('button', { name: '保留' }))
    fireEvent.click(screen.getByRole('button', { name: '保存评分' }))

    await waitFor(() => expect(promptApi.createEvaluation).toHaveBeenCalled())
    const [promptId, body] = vi.mocked(promptApi.createEvaluation).mock.calls[0]
    expect(promptId).toBe('prm_1')
    expect(body.overall_score).toBeGreaterThanOrEqual(1)
    expect(body.overall_score).toBeLessThanOrEqual(5)
    expect(body.dimension_scores?.subject).toBe(5)
    await waitFor(() =>
      expect(promptApi.setStatus).toHaveBeenCalledWith('prm_1', { status: 'keep', reason: '' }),
    )
  })
})
