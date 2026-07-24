import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { getSimulationDetail, updateSimConfig } from '../api/simulation'
import { useGraphData } from '../hooks/useGraphData'
import ProcessLayout from '../components/ProcessLayout'
import GraphPanel from '../components/GraphPanel'

// 单个人设卡片
function PersonaCard({ p }) {
  const { t } = useTranslation()
  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-center gap-2">
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-sky-400 to-indigo-500 text-sm font-bold text-white">
          {(p.name || '?').trim().charAt(0).toUpperCase()}
        </span>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-neutral-800">{p.name}</div>
          <div className="truncate text-xs text-neutral-400">
            {[p.occupation, p.mbti].filter(Boolean).join(' · ') || '—'}
          </div>
        </div>
      </div>
      {p.bio && <p className="mb-2 line-clamp-2 text-xs leading-relaxed text-neutral-600">{p.bio}</p>}
      {p.persona && <p className="mb-2 line-clamp-2 text-xs italic leading-relaxed text-neutral-500">{p.persona}</p>}
      <div className="flex flex-wrap gap-1">
        {(p.interests || []).slice(0, 5).map((it, i) => (
          <span key={i} className="rounded-md bg-neutral-100 px-2 py-0.5 text-[11px] text-neutral-600">
            {it}
          </span>
        ))}
      </div>
      {typeof p.activity_level === 'number' && (
        <div className="mt-3">
          <div className="mb-1 flex items-center justify-between text-[11px] text-neutral-400">
            <span>{t('process.activityLevel')}</span>
            <span>{Math.round(p.activity_level * 100)}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-neutral-100">
            <div className="h-full rounded-full bg-emerald-500" style={{ width: `${Math.round(p.activity_level * 100)}%` }} />
          </div>
        </div>
      )}
    </div>
  )
}

// 24 小时活跃度曲线可视化
function ActivityCurve({ curve = [] }) {
  const { t } = useTranslation()
  if (!curve.length) return null
  const max = Math.max(1, ...curve)
  return (
    <div className="mt-5">
      <div className="mb-1 text-sm font-medium text-neutral-700">{t('process.activityCurve')}</div>
      <div className="flex h-16 items-end gap-0.5">
        {curve.map((v, h) => (
          <div
            key={h}
            className="flex-1 rounded-t bg-emerald-400/70"
            style={{ height: `${(v / max) * 100}%` }}
            title={`${h}:00 · ${Math.round(v * 100)}%`}
          />
        ))}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-neutral-400">
        <span>0h</span>
        <span>12h</span>
        <span>23h</span>
      </div>
    </div>
  )
}

/**
 * SimulationView —— 步骤2 环境搭建详情
 * 展示已生成的智能体人设 + 可编辑的模拟配置（轮次 / 平台 / 种子事件 / 平台参数），确认后进入模拟运行。
 */
export default function SimulationView() {
  const { simulationId } = useParams()
  const { t } = useTranslation()
  const navigate = useNavigate()

  const [detail, setDetail] = useState(null)
  const [profiles, setProfiles] = useState([])
  const [ready, setReady] = useState(false)
  const [maxRounds, setMaxRounds] = useState(10)
  const [platforms, setPlatforms] = useState({ twitter: true, reddit: true })
  const [config, setConfig] = useState(null)
  const [events, setEvents] = useState([])
  const [platformParams, setPlatformParams] = useState({
    twitter: { recsys: 'twhin-bert', max_rec_post: 20 },
    reddit: { recsys: 'reddit', max_rec_post: 20 },
  })
  const [starting, setStarting] = useState(false)
  const [logs, setLogs] = useState([])
  const cfgLoadedRef = useRef(false)
  const pushLog = (text, level) =>
    setLogs((l) => [...l.slice(-60), { time: new Date().toLocaleTimeString(), level, text }])

  // 拉取详情；人设尚未就绪时持续轮询
  useEffect(() => {
    let alive = true
    let tries = 0
    let announced = false
    pushLog(t('log.loadingEnvConfig'))
    const poll = async () => {
      try {
        const res = await getSimulationDetail(simulationId)
        if (!alive) return
        const d = res.data || {}
        setDetail(d)
        const profs = d.profiles || []
        setProfiles(profs)
        const cfg = d.config || {}
        // 仅首次加载时从后端配置初始化表单，避免轮询覆盖用户编辑
        if (!cfgLoadedRef.current && Object.keys(cfg).length) {
          cfgLoadedRef.current = true
          setConfig(cfg)
          if (cfg.time?.max_rounds) setMaxRounds(cfg.time.max_rounds)
          if (cfg.platforms) {
            setPlatforms({
              twitter: cfg.platforms.twitter?.enabled !== false,
              reddit: cfg.platforms.reddit?.enabled !== false,
            })
            setPlatformParams({
              twitter: {
                recsys: cfg.platforms.twitter?.recsys || 'twhin-bert',
                max_rec_post: cfg.platforms.twitter?.max_rec_post ?? 20,
              },
              reddit: {
                recsys: cfg.platforms.reddit?.recsys || 'reddit',
                max_rec_post: cfg.platforms.reddit?.max_rec_post ?? 20,
              },
            })
          }
          if (Array.isArray(cfg.events)) {
            setEvents(cfg.events.map((e) => ({ content: e.content || '', author_uuid: e.author_uuid || null })))
          }
        }
        // 环境就绪：有人设 或 已生成配置 或 模拟状态已进入 prepared 之后
        // （无 Zep / 未抽到实体的降级场景下人设可能为空，此时仍应允许启动模拟）
        const prepared =
          profs.length > 0 ||
          Object.keys(cfg).length > 0 ||
          ['prepared', 'running', 'completed', 'stopped'].includes(d.simulation?.status)
        if (prepared) {
          setReady(true)
          if (!announced) {
            announced = true
            pushLog(profs.length ? t('log.personasGenerated', { count: profs.length }) : t('log.envReady'))
          }
        }
        // 有人设即停止轮询；否则继续等待人设生成（最多约 20 次）
        if (profs.length > 0 || tries > 20) return
      } catch {
        /* 忽略 */
      }
      tries += 1
      if (alive) setTimeout(poll, 2000)
    }
    poll()
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [simulationId])

  const graphId = detail?.simulation?.graph_id
  const { data: graphData, refresh } = useGraphData(graphId)

  const handleStart = async () => {
    if (starting) return
    setStarting(true)
    pushLog(t('log.savingAndStarting'))
    const base = config || {}
    const fullConfig = {
      ...base,
      time: { ...(base.time || {}), max_rounds: maxRounds },
      events: events
        .map((e, i) => ({
          ...(base.events?.[i] || {}),
          content: e.content,
          author_uuid: e.author_uuid ?? (base.events?.[i]?.author_uuid ?? null),
        }))
        .filter((e) => (e.content || '').trim()),
      platforms: {
        twitter: {
          ...(base.platforms?.twitter || {}),
          enabled: platforms.twitter,
          recsys: platformParams.twitter.recsys,
          max_rec_post: Number(platformParams.twitter.max_rec_post) || 20,
        },
        reddit: {
          ...(base.platforms?.reddit || {}),
          enabled: platforms.reddit,
          recsys: platformParams.reddit.recsys,
          max_rec_post: Number(platformParams.reddit.max_rec_post) || 20,
        },
      },
    }
    try {
      await updateSimConfig({ simulation_id: simulationId, config: fullConfig })
    } catch {
      /* 保存失败不阻塞启动 */
    }
    const mode =
      platforms.twitter && platforms.reddit
        ? 'parallel'
        : platforms.twitter
          ? 'twitter'
          : 'reddit'
    navigate(`/simulation/${simulationId}/start?maxRounds=${maxRounds}&mode=${mode}`)
  }

  // 种子事件 / 平台参数编辑
  const updateEvent = (i, val) =>
    setEvents((arr) => arr.map((e, idx) => (idx === i ? { ...e, content: val } : e)))
  const addEvent = () => setEvents((arr) => [...arr, { content: '', author_uuid: null }])
  const removeEvent = (i) => setEvents((arr) => arr.filter((_, idx) => idx !== i))
  const updateParam = (plat, key, val) =>
    setPlatformParams((p) => ({ ...p, [plat]: { ...p[plat], [key]: val } }))

  const togglePlatform = (key) =>
    setPlatforms((p) => {
      const next = { ...p, [key]: !p[key] }
      // 至少保留一个平台
      if (!next.twitter && !next.reddit) return p
      return next
    })

  const secondary = (
    <div className="space-y-5 p-6">
      {/* 人设 */}
      <section className="rounded-2xl border border-neutral-200 bg-white p-6 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl font-bold text-neutral-300">03</span>
            <h3 className="text-lg font-semibold">{t('process.personas')}</h3>
          </div>
          <span className="rounded-md border border-neutral-200 bg-neutral-100 px-2.5 py-1 text-xs font-medium text-neutral-500">
            {profiles.length}
          </span>
        </div>
        {!ready && (
          <div className="flex items-center gap-2 py-6 text-sm text-neutral-400">
            <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-neutral-300 border-t-transparent" />
            {t('process.preparingAgents')}
          </div>
        )}
        {ready && profiles.length === 0 && (
          <p className="py-6 text-center text-sm text-neutral-400">{t('process.noPersonas')}</p>
        )}
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {profiles.map((p, i) => (
            <PersonaCard key={p.entity_uuid || p.name || i} p={p} />
          ))}
        </div>
      </section>

      {/* 模拟配置 */}
      <section className="rounded-2xl border border-neutral-200 bg-white p-6 shadow-sm">
        <div className="mb-4 flex items-center gap-3">
          <span className="text-2xl font-bold text-neutral-300">04</span>
          <h3 className="text-lg font-semibold">{t('process.simConfig')}</h3>
        </div>

        {/* 轮次 */}
        <label className="mb-1 block text-sm font-medium text-neutral-700">
          {t('process.maxRounds')}: <span className="text-neutral-900">{maxRounds}</span>
        </label>
        <input
          type="range"
          min={1}
          max={60}
          value={maxRounds}
          onChange={(e) => setMaxRounds(Number(e.target.value))}
          className="w-full accent-neutral-900"
        />
        <p className="mb-4 text-xs text-neutral-400">{t('process.maxRoundsHint')}</p>

        {/* 平台 */}
        <div className="mb-2 text-sm font-medium text-neutral-700">{t('process.platforms')}</div>
        <div className="flex gap-3">
          {[
            { key: 'twitter', label: 'Twitter', tone: 'sky' },
            { key: 'reddit', label: 'Reddit', tone: 'orange' },
          ].map((pf) => (
            <button
              key={pf.key}
              type="button"
              onClick={() => togglePlatform(pf.key)}
              className={`flex-1 rounded-xl border px-4 py-3 text-sm font-medium transition ${platforms[pf.key]
                ? pf.tone === 'sky'
                  ? 'border-sky-300 bg-sky-50 text-sky-700'
                  : 'border-orange-300 bg-orange-50 text-orange-700'
                : 'border-neutral-200 bg-white text-neutral-400'
                }`}
            >
              {platforms[pf.key] ? '● ' : '○ '}
              {pf.label}
            </button>
          ))}
        </div>

        {/* 平台参数（已启用平台） */}
        <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {[
            { key: 'twitter', label: 'Twitter' },
            { key: 'reddit', label: 'Reddit' },
          ]
            .filter((pf) => platforms[pf.key])
            .map((pf) => (
              <div key={pf.key} className="rounded-xl border border-neutral-200 bg-neutral-50 p-3">
                <div className="mb-2 text-xs font-semibold text-neutral-600">
                  {pf.label} · {t('process.platformParams')}
                </div>
                <label className="mb-1 block text-[11px] text-neutral-400">{t('process.recsys')}</label>
                <input
                  value={platformParams[pf.key].recsys}
                  onChange={(e) => updateParam(pf.key, 'recsys', e.target.value)}
                  className="mb-2 w-full rounded-lg border border-neutral-200 bg-white px-2.5 py-1.5 text-sm text-neutral-900 outline-none focus:border-neutral-400"
                />
                <label className="mb-1 block text-[11px] text-neutral-400">{t('process.maxRecPost')}</label>
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={platformParams[pf.key].max_rec_post}
                  onChange={(e) => updateParam(pf.key, 'max_rec_post', e.target.value)}
                  className="w-full rounded-lg border border-neutral-200 bg-white px-2.5 py-1.5 text-sm text-neutral-900 outline-none focus:border-neutral-400"
                />
              </div>
            ))}
        </div>

        {/* 种子事件编辑 */}
        <div className="mt-5 flex items-center justify-between">
          <span className="text-sm font-medium text-neutral-700">{t('process.seedEvents')}</span>
          <button
            type="button"
            onClick={addEvent}
            className="text-xs font-medium text-violet-600 hover:underline"
          >
            + {t('process.addEvent')}
          </button>
        </div>
        <p className="mb-2 text-xs text-neutral-400">{t('process.seedEventsHint')}</p>
        <div className="space-y-2">
          {events.length === 0 && <p className="text-xs text-neutral-400">—</p>}
          {events.map((ev, i) => (
            <div key={i} className="flex items-start gap-2">
              <textarea
                value={ev.content}
                onChange={(e) => updateEvent(i, e.target.value)}
                rows={2}
                placeholder={t('process.seedEventPlaceholder')}
                className="flex-1 resize-none rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-neutral-900 outline-none transition placeholder:text-neutral-400 focus:border-neutral-400"
              />
              <button
                type="button"
                onClick={() => removeEvent(i)}
                className="mt-1 shrink-0 text-neutral-400 hover:text-red-500"
                aria-label="remove"
              >
                ✕
              </button>
            </div>
          ))}
        </div>

        {/* 活跃度曲线 */}
        <ActivityCurve curve={config?.time?.activity_curve || []} />

        {/* Agent 分布 */}
        {config?.agents && (
          <div className="mt-4 flex items-center gap-4 text-xs text-neutral-500">
            <span>{t('process.agentDistribution')}:</span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-sky-500" />{' '}
              {(config.agents.twitter || []).length}
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-orange-500" />{' '}
              {(config.agents.reddit || []).length}
            </span>
          </div>
        )}

        <button
          type="button"
          onClick={handleStart}
          disabled={!ready || starting}
          className="mt-6 w-full rounded-xl bg-neutral-900 px-5 py-3 text-sm font-medium text-white transition hover:bg-neutral-800 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {starting ? `${t('process.startSim')} …` : `${t('process.startSim')} →`}
        </button>
      </section>
    </div>
  )

  return (
    <ProcessLayout
      step={2}
      stepName={t('steps.step2')}
      status={ready ? { label: t('process.status.ready'), tone: 'green' } : { label: t('process.status.processing'), tone: 'orange' }}
      defaultView="split"
      primary={<GraphPanel data={graphData} graphId={graphId} onRefresh={refresh} />}
      secondary={secondary}
      consoleData={{
        title: t('process.environmentSetup'),
        id: `sim_${(simulationId || '').slice(0, 12)}`,
        lines: logs,
      }}
    />
  )
}
