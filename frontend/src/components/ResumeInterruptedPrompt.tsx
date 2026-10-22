import { useEffect, useRef, useState } from 'react'
import { ApiRequestError, jobApi } from '../api/client'
import { Button, Modal, useToast } from './ui'

const DISMISSED_KEY = 'resume-interrupted-dismissed'

export function ResumeInterruptedPrompt() {
  const toast = useToast()
  const checkedRef = useRef(false)
  const activeRef = useRef(false)
  const [interruptedCount, setInterruptedCount] = useState(0)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    activeRef.current = true
    if (checkedRef.current) {
      return () => {
        activeRef.current = false
      }
    }
    checkedRef.current = true
    if (sessionStorage.getItem(DISMISSED_KEY) === '1') {
      return () => {
        activeRef.current = false
      }
    }

    jobApi
      .list({ status: 'INTERRUPTED', limit: 1 })
      .then(({ total }) => {
        if (!activeRef.current || total <= 0) return
        setInterruptedCount(total)
        setOpen(true)
      })
      .catch(() => {})

    return () => {
      activeRef.current = false
    }
  }, [])

  function dismiss(): void {
    if (busy) return
    sessionStorage.setItem(DISMISSED_KEY, '1')
    setOpen(false)
  }

  async function resumeAll(): Promise<void> {
    setBusy(true)
    setError(null)
    try {
      const result = await jobApi.resumeInterrupted()
      const recovered = result.requeued_count + result.resumed_count
      toast.success(`已恢复 ${recovered} 个任务，剩余 ${result.remaining_images} 张`)
      sessionStorage.setItem(DISMISSED_KEY, '1')
      setOpen(false)
    } catch (resumeError) {
      setError(resumeError instanceof ApiRequestError ? resumeError.message : '恢复中断任务失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={dismiss}
      title="继续中断的生成任务？"
      size="sm"
      footer={
        <>
          <Button variant="secondary" disabled={busy} onClick={dismiss}>
            稍后
          </Button>
          <Button variant="primary" loading={busy} onClick={() => void resumeAll()}>
            一键继续全部
          </Button>
        </>
      }
    >
      <p>检测到 {interruptedCount} 个中断任务。</p>
      <p className="muted">
        未开始的任务会保留原提示词和 Seed 重新排队；已生成部分图片的任务会继续生成剩余图片，并使用新的 Seed。
      </p>
      {error && <p className="ds-notice ds-notice--error">{error}</p>}
    </Modal>
  )
}
