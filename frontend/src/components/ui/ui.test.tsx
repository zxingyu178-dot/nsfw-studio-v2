import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Button } from './Button'
import { Input, Textarea, Field } from './Input'
import { Select } from './Select'
import { Switch } from './Switch'
import { Checkbox } from './Checkbox'
import { SegmentedControl, RadioGroup } from './RadioGroup'
import { Tabs } from './Tabs'
import { Badge, StatusBadge } from './Badge'
import { ProgressBar, Spinner } from './Progress'
import { Drawer } from './Drawer'
import { Modal, ConfirmModal } from './Modal'
import { EmptyState, ErrorState, Skeleton } from './States'

/* ================= Button ================= */
describe('Button', () => {
  it('渲染子文本，默认 secondary 外观', () => {
    render(<Button>生成</Button>)
    const btn = screen.getByRole('button', { name: '生成' })
    expect(btn).toBeInTheDocument()
    expect(btn.className).toContain('ds-btn--secondary')
  })

  it('primary 变体类名正确', () => {
    render(<Button variant="primary">开始</Button>)
    expect(screen.getByRole('button', { name: '开始' }).className).toContain('ds-btn--primary')
  })

  it('点击触发 onClick', async () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>点我</Button>)
    await userEvent.click(screen.getByRole('button', { name: '点我' }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('disabled 时不触发', async () => {
    const onClick = vi.fn()
    render(
      <Button disabled onClick={onClick}>
        禁用
      </Button>
    )
    await userEvent.click(screen.getByRole('button', { name: '禁用' }))
    expect(onClick).not.toHaveBeenCalled()
  })

  it('loading 时禁用并标记 aria-busy', () => {
    render(<Button loading>提交</Button>)
    const btn = screen.getByRole('button')
    expect(btn).toBeDisabled()
    expect(btn).toHaveAttribute('aria-busy', 'true')
  })
})

/* ================= Input / Textarea / Field ================= */
describe('Input', () => {
  it('可输入文本', async () => {
    render(<Input defaultValue="" aria-label="搜索" />)
    const input = screen.getByLabelText('搜索')
    await userEvent.type(input, 'hello')
    expect(input).toHaveValue('hello')
  })

  it('invalid 时设置 aria-invalid', () => {
    render(<Input invalid aria-label="坏输入" />)
    expect(screen.getByLabelText('坏输入')).toHaveAttribute('aria-invalid', 'true')
  })

  it('Textarea 可多行输入', async () => {
    render(<Textarea aria-label="正文" defaultValue="" />)
    const ta = screen.getByLabelText('正文')
    await userEvent.type(ta, '第一行')
    expect(ta).toHaveValue('第一行')
    expect(ta.className).toContain('ds-input--textarea')
  })

  it('Field 展示标签、必填与错误', () => {
    render(
      <Field label="名称" required error="不能为空">
        <Input />
      </Field>
    )
    expect(screen.getByText('名称')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('不能为空')
  })
})

/* ================= Select ================= */
describe('Select', () => {
  const opts = [
    { value: 'a', label: '选项A' },
    { value: 'b', label: '选项B' },
  ]
  it('渲染选项并可切换', () => {
    const onChange = vi.fn()
    render(<Select options={opts} value="a" onChange={onChange} aria-label="选择" />)
    const select = screen.getByLabelText('选择')
    expect(select).toContainElement(screen.getByText('选项A'))
    fireEvent.change(select, { target: { value: 'b' } })
    expect(onChange).toHaveBeenCalled()
  })
})

/* ================= Switch ================= */
describe('Switch', () => {
  it('role=switch，点击切换', async () => {
    render(<Switch aria-label="开关" />)
    const sw = screen.getByRole('switch')
    expect(sw).not.toBeChecked()
    await userEvent.click(sw)
    expect(sw).toBeChecked()
  })
})

/* ================= Checkbox ================= */
describe('Checkbox', () => {
  it('点击勾选', async () => {
    render(<Checkbox label="启用模块" />)
    const cb = screen.getByRole('checkbox', { name: '启用模块' })
    await userEvent.click(cb)
    expect(cb).toBeChecked()
  })
})

/* ================= RadioGroup / Segmented ================= */
describe('SegmentedControl', () => {
  const opts = [
    { value: 'structured', label: '结构化' },
    { value: 'full', label: '完整' },
  ]
  it('当前项高亮并可切换', async () => {
    const onChange = vi.fn()
    render(<SegmentedControl options={opts} value="structured" onChange={onChange} />)
    const full = screen.getByRole('radio', { name: '完整' })
    expect(full).toHaveAttribute('aria-checked', 'false')
    await userEvent.click(full)
    expect(onChange).toHaveBeenCalledWith('full')
  })
})

describe('RadioGroup', () => {
  it('单选行为', async () => {
    const opts = [
      { value: 'light', label: '浅色' },
      { value: 'dark', label: '深色' },
    ]
    const onChange = vi.fn()
    render(<RadioGroup name="theme" options={opts} value="light" onChange={onChange} />)
    await userEvent.click(screen.getByRole('radio', { name: '深色' }))
    expect(onChange).toHaveBeenCalledWith('dark')
  })
})

/* ================= Tabs ================= */
describe('Tabs', () => {
  const items = [
    { key: 'p', label: '提示词' },
    { key: 'r', label: '配方' },
  ]
  it('渲染并点击切换', async () => {
    const onChange = vi.fn()
    render(<Tabs items={items} active="p" onChange={onChange} />)
    const recipe = screen.getByRole('tab', { name: '配方' })
    expect(recipe).toHaveAttribute('aria-selected', 'false')
    await userEvent.click(recipe)
    expect(onChange).toHaveBeenCalledWith('r')
  })
})

/* ================= Badge / StatusBadge ================= */
describe('Badge', () => {
  it('渲染中性徽标', () => {
    render(<Badge>标签</Badge>)
    expect(screen.getByText('标签').className).toContain('ds-badge--neutral')
  })
})

describe('StatusBadge', () => {
  it.each([
    ['RUNNING', '运行中'],
    ['COMPLETED', '已完成'],
    ['FAILED', '失败'],
    ['KEPT', '已保留'],
    ['REJECTED', '已拒绝'],
  ])('%s 映射为中文「%s」', (status, label) => {
    render(<StatusBadge status={status} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })
})

/* ================= Progress / Spinner ================= */
describe('ProgressBar', () => {
  it('根据值设置 aria-valuenow', () => {
    render(<ProgressBar value={0.5} />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '50')
  })
  it('超过 1 被截断', () => {
    render(<ProgressBar value={3} />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100')
  })
})

describe('Spinner', () => {
  it('role=status 且带可读标签', () => {
    render(<Spinner />)
    expect(screen.getByRole('status')).toHaveAttribute('aria-label', '加载中')
  })
})

/* ================= Drawer ================= */
describe('Drawer', () => {
  it('关闭时不渲染，打开时渲染标题', () => {
    const { rerender } = render(
      <Drawer open={false} onClose={() => {}} title="详情">
        内容
      </Drawer>
    )
    expect(screen.queryByText('详情')).not.toBeInTheDocument()
    rerender(
      <Drawer open onClose={() => {}} title="详情">
        内容
      </Drawer>
    )
    expect(screen.getByText('详情')).toBeInTheDocument()
    expect(screen.getByText('内容')).toBeInTheDocument()
  })

  it('ESC 触发 onClose', async () => {
    const onClose = vi.fn()
    render(
      <Drawer open onClose={onClose} title="详情">
        内容
      </Drawer>
    )
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

/* ================= Modal / Confirm ================= */
describe('Modal', () => {
  it('打开时渲染，关闭按钮触发 onClose', async () => {
    const onClose = vi.fn()
    render(
      <Modal open onClose={onClose} title="编辑">
        表单
      </Modal>
    )
    expect(screen.getByText('编辑')).toBeInTheDocument()
    await userEvent.click(screen.getByLabelText('关闭'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

describe('ConfirmModal', () => {
  it('确认 / 取消分别触发', async () => {
    const onConfirm = vi.fn()
    const onCancel = vi.fn()
    render(
      <ConfirmModal
        open
        title="确认拒绝？"
        message="该操作可稍后重置"
        danger
        onConfirm={onConfirm}
        onCancel={onCancel}
      />
    )
    await userEvent.click(screen.getByRole('button', { name: '确认' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
    await userEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })
})

/* ================= Empty / Error / Skeleton ================= */
describe('EmptyState', () => {
  it('渲染标题、描述与动作', () => {
    render(<EmptyState title="暂无图片" description="去生成一张" action={<button>生成</button>} />)
    expect(screen.getByText('暂无图片')).toBeInTheDocument()
    expect(screen.getByText('去生成一张')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '生成' })).toBeInTheDocument()
  })
})

describe('ErrorState', () => {
  it('渲染错误与重试', async () => {
    const onRetry = vi.fn()
    render(<ErrorState error="网络异常" onRetry={onRetry} />)
    expect(screen.getByText('网络异常')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })
})

describe('Skeleton', () => {
  it('对 AT 隐藏', () => {
    render(<Skeleton width={100} height={12} />)
    const sk = document.querySelector('.ds-skeleton')
    expect(sk).toHaveAttribute('aria-hidden', 'true')
  })
})
