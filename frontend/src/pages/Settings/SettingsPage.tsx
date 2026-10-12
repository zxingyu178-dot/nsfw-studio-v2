import { useCallback, useEffect, useState } from 'react'
import type { Theme } from '../../stores/themeStore'
import { useTheme } from '../../themes/ThemeProvider'
import { ApiRequestError, engineRuntimeApi, imageApi, systemApi } from '../../api/client'
import { Button, RadioGroup } from '../../components/ui'
import type { EngineRuntimeState, SystemStatus, ThumbnailBackfillStatusDTO } from '../../types/workbench'
import MobileReviewSection from './MobileReviewSection'
import './settings.css'

/** 磁盘剩余空间阈值：Warning / Severe（用于存储面板提示）。 */
const DISK_WARNING_BYTES = 10 * 1024 * 1024 * 1024 // 10 GB
const DISK_SEVERE_BYTES = 5 * 1024 * 1024 * 1024 // 5 GB

const ENGINE_STATE_LABEL: Record<EngineRuntimeState, string> = {
  STOPPED: '已停止',
  STARTING: '启动中…',
  RUNNING_MANAGED: '运行中（Studio 托管）',
  RUNNING_EXTERNAL: '运行中（外部 ComfyUI）',
  STOPPING: '停止中…',
  PORT_CONFLICT: '端口冲突',
  ERROR: '启动失败',
}

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)))
  const value = bytes / Math.pow(1024, i)
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

function failMessage(e: unknown): string {
  return e instanceof ApiRequestError ? e.message : '操作失败'
}

/**
 * 设置 = 系统与维护中心（Phase 0.12 Task7）。
 * 全部只读数据来自 systemApi.status()；引擎启停复用 engineRuntimeApi；
 * 图片缓存回填复用 imageApi 的 backfill 接口。不读取/展示任何敏感配置。
 */
export default function SettingsPage() {
  const { theme, setTheme } = useTheme()

  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [acting, setActing] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [backfill, setBackfill] = useState<ThumbnailBackfillStatusDTO | null>(null)

  const reloadStatus = useCallback(async () => {
    try {
      const s = await systemApi.status()
      setStatus(s)
      setLoadError(null)
    } catch (e) {
      setLoadError(failMessage(e))
    }
  }, [])

  // 打开即拉取系统状态
  useEffect(() => {
    void reloadStatus()
  }, [reloadStatus])

  // 回填进行中时轮询进度
  useEffect(() => {
    if (!backfill?.running) return
    const timer = window.setInterval(() => {
      imageApi
        .backfillStatus()
        .then((b) => setBackfill(b))
        .catch(() => undefined)
    }, 2000)
    return () => window.clearInterval(timer)
  }, [backfill?.running])

  async function runEngineAction(action: () => Promise<unknown>): Promise<void> {
    setActing(true)
    setActionError(null)
    try {
      await action()
      await reloadStatus()
    } catch (e) {
      setActionError(failMessage(e))
    } finally {
      setActing(false)
    }
  }

  async function startBackfill(kind: 'thumbnail' | 'preview'): Promise<void> {
    setActionError(null)
    try {
      setBackfill(await imageApi.startBackfill({ kind }))
    } catch (e) {
      setActionError(failMessage(e))
    }
  }

  async function stopBackfill(): Promise<void> {
    setActionError(null)
    try {
      setBackfill(await imageApi.stopBackfill())
    } catch (e) {
      setActionError(failMessage(e))
    }
  }

  const engine = status?.engine_runtime
  const engineState: EngineRuntimeState | null = engine?.state ?? null

  const diskFree = status?.disk_free ?? 0
  const diskSevere = diskFree < DISK_SEVERE_BYTES
  const diskWarning = !diskSevere && diskFree < DISK_WARNING_BYTES

  return (
    <>
      <section className="st-panel">
        <h2 className="st-panel__title">外观</h2>
        <RadioGroup<Theme>
          name="theme"
          value={theme}
          onChange={setTheme}
          direction="column"
          options={[
            { value: 'dark', label: '深色' },
            { value: 'light', label: '浅色' },
          ]}
        />
      </section>

      <section className="st-panel">
        <h2 className="st-panel__title">生图引擎</h2>
        {loadError && <p className="ds-notice ds-notice--error">{loadError}</p>}
        {!status && !loadError && <p className="muted">加载中…</p>}
        {engine && (
          <>
            <div className="st-row">
              <span className="st-dot st-dot--ok" aria-hidden="true" />
              <span>{ENGINE_STATE_LABEL[engineState ?? 'STOPPED']}</span>
              <span className="muted">
                {engine.host}:{engine.port} · {engine.owned ? 'Studio 托管' : '外部进程'}
              </span>
            </div>
            <div className="st-actions">
              {engineState !== 'RUNNING_MANAGED' && engineState !== 'RUNNING_EXTERNAL' && engineState !== 'STARTING' && (
                <Button variant="primary" size="sm" loading={acting} onClick={() => void runEngineAction(() => engineRuntimeApi.start())}>
                  启动生图引擎
                </Button>
              )}
              {engineState === 'RUNNING_MANAGED' && (
                <>
                  <Button variant="danger" size="sm" loading={acting} onClick={() => void runEngineAction(() => engineRuntimeApi.stop())}>
                    停止引擎
                  </Button>
                  <Button variant="secondary" size="sm" loading={acting} onClick={() => void runEngineAction(() => engineRuntimeApi.restart())}>
                    重启
                  </Button>
                </>
              )}
              {engineState === 'RUNNING_EXTERNAL' && (
                <span className="muted">外部 ComfyUI 不由 Studio 托管，不能从这里停止或重启。</span>
              )}
            </div>
          </>
        )}
        {actionError && <p className="ds-notice ds-notice--error">{actionError}</p>}
      </section>

      {/* Phase 0.13：局域网手机审核桥（独立 8767） */}
      <MobileReviewSection />

      <section className="st-panel">
        <h2 className="st-panel__title">图片缓存</h2>
        {status && (
          <dl className="st-dl">
            <dt>缩略图</dt>
            <dd>{status.thumbnail_count} / {status.image_count} 张已生成</dd>
            <dt>渐进预览图</dt>
            <dd>{status.preview_count} / {status.image_count} 张已生成</dd>
          </dl>
        )}
        <div className="st-actions">
          <Button size="sm" variant="secondary" disabled={acting || backfill?.running} onClick={() => void startBackfill('thumbnail')}>
            补齐缩略图
          </Button>
          <Button size="sm" variant="secondary" disabled={acting || backfill?.running} onClick={() => void startBackfill('preview')}>
            补齐预览图
          </Button>
        </div>
        {backfill?.running && (
          <p className="st-panel__text" role="status">
            回填中：{backfill.done} / {backfill.total}
            {backfill.failed > 0 ? `（失败 ${backfill.failed}）` : ''}
            <Button size="xs" variant="danger" onClick={() => void stopBackfill()}>停止</Button>
          </p>
        )}
      </section>

      <section className="st-panel">
        <h2 className="st-panel__title">存储</h2>
        {status && (
          <>
            <dl className="st-dl">
              <dt>DataRoot</dt>
              <dd className="st-mono">{status.data_root}</dd>
              <dt>数据库大小</dt>
              <dd>{formatBytes(status.database_size)}</dd>
              <dt>磁盘剩余</dt>
              <dd>
                {formatBytes(status.disk_free)} / 共 {formatBytes(status.disk_total)}
              </dd>
            </dl>
            {diskSevere && (
              <p className="ds-notice ds-notice--error">磁盘空间严重不足（&lt; 5 GB），请尽快清理。</p>
            )}
            {diskWarning && (
              <p className="ds-notice st-notice--warn">
                磁盘空间偏低（&lt; 10 GB），建议清理。
              </p>
            )}
          </>
        )}
      </section>

      <section className="st-panel">
        <h2 className="st-panel__title">关于</h2>
        <p className="st-panel__text">NSFW Studio V2 · 本地家庭媒体生成与批阅工作台。</p>
        <dl className="st-dl">
          <dt>版本</dt>
          <dd className="st-mono">{status?.app_version ?? '—'}</dd>
          <dt>当前数据库 Migration</dt>
          <dd className="st-mono">{status?.latest_migration ?? '—'}</dd>
        </dl>
      </section>
    </>
  )
}
