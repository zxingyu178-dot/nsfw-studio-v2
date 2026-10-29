import { useCallback, useEffect, useState } from 'react'
import {
  ApiRequestError,
  mobileReviewApi,
  type MobilePairingCodeDTO,
  type MobileReviewRuntimeDTO,
  type MobileReviewRuntimeState,
  type PairedDeviceDTO,
} from '../../api/client'
import { Button } from '../../components/ui'

/**
 * Phase 0.13 Settings「手机审核」区：局域网手机审核桥（独立端口 8877）管理面板。
 *
 * - 运行状态 / 启停：复用 mobileReviewApi（与 EngineRuntime 同款受管 runtime，不写第二套）；
 * - 配对码：6 位一次性码 + 10 分钟倒计时；
 * - 已配对设备列表 / 撤销：loopback 管理端点；
 * - 红线：本组件绝不调用 netsh / 不改防火墙，连不通只做 UI 提示（专用网络放行）。
 */

const STATE_LABEL: Record<MobileReviewRuntimeState, string> = {
  STOPPED: '已停止',
  STARTING: '启动中…',
  RUNNING: '运行中',
  STOPPING: '停止中…',
  PORT_CONFLICT: '端口 8877 被占用（非本程序进程）',
  ERROR: '启动失败',
}

function failMessage(e: unknown): string {
  return e instanceof ApiRequestError ? e.message : '操作失败'
}

function formatCountdown(ms: number): string {
  const total = Math.max(0, Math.ceil(ms / 1000))
  const mm = Math.floor(total / 60)
  const ss = total % 60
  return `${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
}

export default function MobileReviewSection() {
  const [runtime, setRuntime] = useState<MobileReviewRuntimeDTO | null>(null)
  const [runtimeError, setRuntimeError] = useState<string | null>(null)
  const [acting, setActing] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const [pairing, setPairing] = useState<{ code: string; expiresAt: number } | null>(null)
  const [now, setNow] = useState(() => Date.now())

  const [devices, setDevices] = useState<PairedDeviceDTO[] | null>(null)
  const [devicesError, setDevicesError] = useState<string | null>(null)

  const loadRuntime = useCallback(async () => {
    try {
      setRuntime(await mobileReviewApi.runtime())
      setRuntimeError(null)
    } catch (e) {
      setRuntimeError(failMessage(e))
    }
  }, [])

  const loadDevices = useCallback(async () => {
    try {
      setDevices(await mobileReviewApi.devices())
      setDevicesError(null)
    } catch (e) {
      // 设备管理端点未就绪 / 不可用：优雅降级为提示，不炸面板
      setDevicesError(e instanceof ApiRequestError ? `设备列表暂不可用：${e.message}` : '设备列表暂不可用')
    }
  }, [])

  useEffect(() => {
    void loadRuntime()
    void loadDevices()
  }, [loadRuntime, loadDevices])

  // 配对码倒计时：1s 心跳；过期即隐藏
  useEffect(() => {
    if (!pairing) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [pairing])

  useEffect(() => {
    if (pairing && Date.now() >= pairing.expiresAt) setPairing(null)
  }, [now, pairing])

  async function runAction(action: () => Promise<unknown>): Promise<void> {
    setActing(true)
    setActionError(null)
    try {
      await action()
      await loadRuntime()
    } catch (e) {
      setActionError(failMessage(e))
    } finally {
      setActing(false)
    }
  }

  async function generateCode(): Promise<void> {
    setActionError(null)
    try {
      const dto: MobilePairingCodeDTO = await mobileReviewApi.createPairingCode()
      setPairing({ code: dto.code, expiresAt: Date.now() + dto.expires_in_seconds * 1000 })
      setNow(Date.now())
    } catch (e) {
      setActionError(failMessage(e))
    }
  }

  async function revoke(deviceId: string): Promise<void> {
    setActionError(null)
    try {
      await mobileReviewApi.revokeDevice(deviceId)
      await loadDevices()
    } catch (e) {
      setActionError(failMessage(e))
    }
  }

  const state: MobileReviewRuntimeState = runtime?.state ?? 'STOPPED'
  const running = state === 'RUNNING'
  const countdownLeft = pairing ? pairing.expiresAt - now : 0

  return (
    <section className="st-panel">
      <h2 className="st-panel__title">手机审核</h2>
      {runtimeError && <p className="ds-notice ds-notice--error">{runtimeError}</p>}
      {!runtime && !runtimeError && <p className="muted">加载中…</p>}

      {runtime && (
        <>
          <div className="st-row">
            <span className={`st-dot${running ? ' st-dot--ok' : ''}`} aria-hidden="true" />
            <span data-testid="mobile-runtime-state">{STATE_LABEL[state]}</span>
            <span className="muted st-mono">
              {runtime.host === '0.0.0.0' ? `*:${runtime.port}` : `${runtime.host}:${runtime.port}`}
              {runtime.owned ? ' · 本程序托管' : ''}
            </span>
          </div>

          <dl className="st-dl">
            <dt>手机访问地址</dt>
            <dd className="st-mono">http://&lt;电脑局域网IP&gt;:{runtime.port}</dd>
            <dt>配对入口</dt>
            <dd>手机浏览器打开地址后输入配对码完成绑定</dd>
          </dl>
          <p className="st-panel__text">
            手机与电脑需在同一 Wi-Fi/局域网。不知道电脑 IP：PowerShell 执行
            <span className="st-mono"> ipconfig </span>
            看「IPv4 地址」（如 192.168.x.x）。连不通时请在 Windows 防火墙
            <strong>「专用网络」</strong>放行入站端口 {runtime.port}（本应用不会自动修改防火墙）。
          </p>

          <div className="st-actions">
            {!running && state !== 'STARTING' && (
              <Button variant="primary" size="sm" loading={acting} onClick={() => void runAction(() => mobileReviewApi.start())}>
                启动手机审核桥
              </Button>
            )}
            {running && (
              <>
                <Button variant="danger" size="sm" loading={acting} onClick={() => void runAction(() => mobileReviewApi.stop())}>
                  停止
                </Button>
                <Button variant="secondary" size="sm" loading={acting} onClick={() => void runAction(() => mobileReviewApi.restart())}>
                  重启
                </Button>
              </>
            )}
            <Button size="sm" variant="secondary" loading={acting} disabled={!running} onClick={() => void generateCode()}>
              生成配对码
            </Button>
          </div>

          {pairing && countdownLeft > 0 && (
            <p className="st-panel__text" role="status" data-testid="pairing-code-box">
              配对码：<strong className="st-mono" data-testid="pairing-code" style={{ fontSize: '1.25em', letterSpacing: '0.2em' }}>{pairing.code}</strong>
              <span className="muted"> · 有效期剩余 </span>
              <span className="st-muted st-mono" data-testid="pairing-countdown">{formatCountdown(countdownLeft)}</span>
              <span className="muted"> · 一次性，绑定成功即失效</span>
            </p>
          )}

          <h3 className="st-panel__title" style={{ fontSize: 'var(--text-sm)', marginTop: 'var(--space-3)' }}>已配对设备</h3>
          {devicesError && <p className="ds-notice st-notice--warn">{devicesError}</p>}
          {devices === null && !devicesError && <p className="muted">加载中…</p>}
          {devices !== null && devices.length === 0 && (
            <p className="st-panel__text">暂无已配对设备。启动桥并生成配对码，在手机上完成绑定。</p>
          )}
          {devices !== null && devices.length > 0 && (
            <ul style={{ margin: 0, paddingLeft: 'var(--space-4)' }}>
              {devices.map((device) => (
                <li key={device.device_id} className="st-row" data-testid={`device-row-${device.device_id}`}>
                  <span>{device.name || '未命名设备'}</span>
                  <span className="muted">{device.installation_id}</span>
                  <Button size="xs" variant="danger" onClick={() => void revoke(device.device_id)}>撤销</Button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      {actionError && <p className="ds-notice ds-notice--error">{actionError}</p>}
    </section>
  )
}
