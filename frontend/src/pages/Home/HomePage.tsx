import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { imageApi } from '../../api/client'
import { ImageLightbox } from '../../components/ImageLightbox'
import { IconCheck, IconGrid, IconImage, IconQueue } from '../../components/ui/icons'
import { IconActualSize, IconNext, IconQuote, IconSpark } from '../../components/ui/ui3'
import { useJobStore } from '../../stores/jobStore'
import { imagePreviewUrl, imageThumbUrl, normalizeImageStatus, type ImageDTO, type ImageStatsResponse } from '../../types/workbench'
import './home.css'

const RECENT_LIMIT = 7
const VISIBLE_STATUSES = ['NEW', 'KEEP', 'ARCHIVED'] as const
const TIME_FORMAT = new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })

const QUICK_LINKS = [
  { to: '/generate', label: '新建', Icon: IconSpark },
  { to: '/gallery?status=NEW&review=1', label: '审核', Icon: IconCheck },
  { to: '/gallery', label: '图库', Icon: IconGrid },
  { to: '/prompts', label: '词库', Icon: IconQuote },
]

interface HomeData {
  images: ImageDTO[]
  stats: ImageStatsResponse
  today: number
}

async function readHome(): Promise<HomeData> {
  const midnight = new Date()
  midnight.setHours(0, 0, 0, 0)

  const [stats, today, pages] = await Promise.all([
    imageApi.stats(),
    imageApi.stats({ date_from: midnight.toISOString(), source: 'comfyui' }),
    Promise.all(VISIBLE_STATUSES.map(status => imageApi.list({
      status, sort: 'created_desc', page: 1, page_size: RECENT_LIMIT,
    }))),
  ])

  const uniqueImages = new Map<string, ImageDTO>()
  for (const { items } of pages) {
    for (const image of items) {
      if (normalizeImageStatus(image) !== 'REJECT') uniqueImages.set(image.id, image)
    }
  }
  const images = [...uniqueImages.values()]
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at) || b.id.localeCompare(a.id))
    .slice(0, RECENT_LIMIT)

  return { images, stats, today: today.total }
}

export default function HomePage() {
  const { queue } = useJobStore()
  const [data, setData] = useState<HomeData | null>(null)
  const [failed, setFailed] = useState(false)
  const [loading, setLoading] = useState(true)
  const [reload, setReload] = useState(0)
  const [lightbox, setLightbox] = useState<number | null>(null)
  const [badPreview, setBadPreview] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    void readHome().then(
      result => {
        if (!active) return
        setData(result)
        setFailed(false)
        setLoading(false)
      },
      () => {
        if (!active) return
        setFailed(true)
        setLoading(false)
      },
    )
    return () => { active = false }
  }, [reload])

  function refresh() {
    setBadPreview(null)
    setFailed(false)
    setLoading(true)
    setReload(key => key + 1)
  }

  const images = data?.images ?? []
  const latest = images[0]
  const latestTime = latest ? new Date(latest.created_at) : null
  const validTime = latestTime && Number.isFinite(latestTime.valueOf())
  const metrics = [
    { label: '今日出图', value: data?.today, to: null },
    { label: '待审', value: data?.stats.new, to: '/gallery?status=NEW' },
    { label: '保留', value: data?.stats.keep, to: '/gallery?status=KEEP' },
    { label: '废片', value: data?.stats.reject, to: '/gallery?status=REJECT' },
  ]

  return (
    <div className="studio-home" aria-busy={loading}>
      {failed && (
        <div className="studio-home__error" role="alert">
          首页数据加载失败
          <button type="button" className="studio-home__button" onClick={refresh}>重试</button>
        </div>
      )}
      <section className="studio-home__hero" aria-label="最新作品">
        <div className="studio-home__frame">
          {latest && badPreview !== latest.id ? (
            <button className="studio-home__preview" type="button" onClick={() => setLightbox(0)} aria-label="查看最新作品">
              <img src={imagePreviewUrl(latest.id)} alt="最新作品" onError={() => setBadPreview(latest.id)} />
            </button>
          ) : (
            <div className="studio-home__placeholder">
              <IconImage size={24} />
              <strong>{latest ? '预览暂不可用' : loading ? '正在读取最新作品' : failed ? '最新作品暂不可用' : '还没有作品'}</strong>
              {latest ? (
                <button className="studio-home__button" type="button" onClick={() => setLightbox(0)}>查看大图</button>
              ) : !loading && !failed && (
                <Link className="studio-home__primary" to="/generate">去创作</Link>
              )}
            </div>
          )}
          {latest && (
            <div className="studio-home__tags" aria-label="作品信息">
              <span>{latest.width} × {latest.height}</span>
              {normalizeImageStatus(latest) === 'NEW' && <span className="studio-home__pending">待审</span>}
            </div>
          )}
        </div>
        {latest && (
          <div className="studio-home__meta">
            {validTime && <time dateTime={latest.created_at}>{TIME_FORMAT.format(latestTime)}</time>}
            <span>{latest.source === 'import' ? '导入作品' : '生成作品'}</span>
            <button className="studio-home__button" type="button" onClick={() => setLightbox(0)}>
              <IconActualSize /> 查看大图
            </button>
          </div>
        )}
      </section>
      <aside className="studio-home__side" aria-label="图像与队列概览">
        <div className="studio-home__metrics">
          {metrics.map(({ label, value, to }) => {
            const contents = <><span>{label}</span><strong>{value?.toLocaleString('zh-CN') ?? '—'}</strong></>
            return to
              ? <Link key={label} to={to} className="studio-home__metric">{contents}</Link>
              : <div key={label} className="studio-home__metric">{contents}</div>
          })}
        </div>
        <Link className="studio-home__queue" to="/generate">
          <IconQueue />
          {queue ? (
            <span>{queue.running ? 1 : 0} 运行 <span>{queue.queued.length} 排队</span>{queue.paused.length > 0 && <span>{queue.paused.length} 暂停</span>}</span>
          ) : <span>查看队列</span>}
          <IconNext />
        </Link>
        <div className="studio-home__quick">
          {QUICK_LINKS.map(({ to, label, Icon }) => (
            <Link key={label} to={to}><Icon size={18} />{label}</Link>
          ))}
        </div>
        {!!data?.stats.new && <Link className="studio-home__primary" to="/gallery?status=NEW&review=1"><IconCheck />继续审核</Link>}
        <section className="studio-home__recent">
          <div className="studio-home__recent-header">
            <h2>最近作品</h2>
            <button className="studio-home__button" type="button" onClick={refresh} disabled={loading}>刷新</button>
            <Link to="/gallery">全部</Link>
          </div>
          {images.length > 1 ? (
            <div className="studio-home__recent-grid">
              {images.slice(1).map((image, index) => (
                <button type="button" key={image.id} onClick={() => setLightbox(index + 1)} aria-label={'查看最近作品 ' + (index + 1)}>
                  <img src={imageThumbUrl(image.id)} alt="" loading="lazy" />
                </button>
              ))}
            </div>
          ) : <p>{loading ? '正在读取' : failed ? '暂不可用' : '暂无更多作品'}</p>}
        </section>
      </aside>
      {lightbox !== null && images.length > 0 && (
        <ImageLightbox images={images} index={lightbox} onClose={() => setLightbox(null)} onNavigate={setLightbox} />
      )}
    </div>
  )
}
