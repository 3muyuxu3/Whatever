import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import ReportCharts from './ReportCharts'

// icons8 图标（浅色主题，灰色）
const ICON_GLOBE = 'https://img.icons8.com/ios/50/9ca3af/globe--v1.png'
const ICON_CHAT = 'https://img.icons8.com/ios/50/9ca3af/chat--v1.png'

// 将轮次换算为拟真「经过时间」（每轮约 30 分钟）
function elapsedOf(round) {
  const m = round * 30
  return `${Math.floor(m / 60)}h ${m % 60}m`
}

// 顶部统计卡
function StatCard({ icon, title, round, maxRounds, acts }) {
  const { t } = useTranslation()
  return (
    <div className="flex-1 rounded-2xl border border-neutral-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center gap-2">
        <img src={icon} alt="" className="h-4 w-4" loading="lazy" />
        <span className="text-sm font-semibold tracking-wide text-neutral-700">{title}</span>
      </div>
      <div className="flex items-center gap-4 text-xs text-neutral-400">
        <span>
          {t('process.round')}{' '}
          <b className="text-neutral-800">
            {round}/{maxRounds}
          </b>
        </span>
        <span>
          {t('process.elapsed')} <b className="text-neutral-800">{elapsedOf(round)}</b>
        </span>
        <span>
          {t('process.acts')} <b className="text-neutral-800">{acts}</b>
        </span>
      </div>
    </div>
  )
}

/**
 * Step3Simulation —— 步骤3 工作台：模拟统计 + 事件流
 *
 * @param {Object}   status           { round, max_rounds }
 * @param {Array}    actions          动作日志
 * @param {boolean}  started          是否已开始
 * @param {Function} onStart          启动模拟
 * @param {Function} onGenerateReport 进入报告生成
 */
export default function Step3Simulation({ status, actions = [], started, running, onStart, onStop, onGenerateReport, onInject }) {
  const { t } = useTranslation()
  const round = status?.round || 0
  const maxRounds = status?.max_rounds || 40

  const [injectText, setInjectText] = useState('')
  const [injecting, setInjecting] = useState(false)
  const [view, setView] = useState('events') // events | charts

  const plaza = actions.filter((a) => a.platform === 'twitter')
  const community = actions.filter((a) => a.platform === 'reddit')
  const posts = actions
    .filter((a) => ['CREATE_POST', 'QUOTE_POST', 'CREATE_COMMENT', 'INJECT'].includes(a.action) && a.content)
    .slice(-40)
    .reverse()

  const doInject = async () => {
    const c = injectText.trim()
    if (!c || injecting || !onInject) return
    setInjecting(true)
    try {
      await onInject(c)
      setInjectText('')
    } finally {
      setInjecting(false)
    }
  }

  return (
    <div className="flex h-full flex-col">
      {/* 顶部：两张统计卡 + 生成报告按钮 */}
      <div className="flex items-stretch gap-4 border-b border-neutral-200 p-6">
        <StatCard icon={ICON_GLOBE} title={t('process.infoPlaza')} round={round} maxRounds={maxRounds} acts={plaza.length} />
        <StatCard icon={ICON_CHAT} title={t('process.topicCommunity')} round={round} maxRounds={maxRounds} acts={community.length} />
        <div className="flex shrink-0 items-center gap-2 self-center">
          {!started && (
            <button
              type="button"
              onClick={onStart}
              className="rounded-xl bg-neutral-900 px-5 py-3 text-sm font-medium text-white transition hover:bg-neutral-800"
            >
              {t('process.startSim')} →
            </button>
          )}
          {started && running && onStop && (
            <button
              type="button"
              onClick={onStop}
              className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-600 transition hover:bg-red-100"
            >
              {t('process.stopSim')}
            </button>
          )}
          {started && (
            <button
              type="button"
              onClick={onGenerateReport}
              className="rounded-xl bg-neutral-900 px-5 py-3 text-sm font-medium text-white transition hover:bg-neutral-800"
            >
              {t('process.startReport')} →
            </button>
          )}
        </div>
      </div>

      {/* TOTAL EVENTS + 视图切换 */}
      <div className="flex items-center gap-4 border-b border-neutral-200 px-6 py-3 text-sm">
        <span className="font-semibold tracking-wide text-neutral-500">
          {t('process.totalEvents')}: <span className="text-neutral-900">{actions.length}</span>
        </span>
        <span className="flex items-center gap-1 text-neutral-500">
          <img src={ICON_GLOBE} alt="" className="h-3.5 w-3.5" loading="lazy" /> {plaza.length}
        </span>
        <span className="flex items-center gap-1 text-neutral-500">
          <img src={ICON_CHAT} alt="" className="h-3.5 w-3.5" loading="lazy" /> {community.length}
        </span>
        <div className="ml-auto flex items-center gap-1 rounded-lg bg-neutral-100 p-0.5">
          {[
            { key: 'events', label: t('process.tabEvents') },
            { key: 'charts', label: t('process.tabCharts') },
          ].map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setView(tab.key)}
              className={`rounded-md px-3 py-1 text-xs font-medium transition ${view === tab.key
                ? 'bg-white text-neutral-900 shadow-sm'
                : 'text-neutral-500 hover:text-neutral-800'
                }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* 上帝视角：动态注入变量 */}
      {started && onInject && (
        <div className="border-b border-neutral-200 bg-violet-50/40 px-6 py-3">
          <div className="mb-1.5 flex items-center gap-2 text-sm font-semibold text-violet-700">
            <span>🛰️</span>
            {t('process.godView')}
          </div>
          <div className="flex gap-2">
            <input
              value={injectText}
              onChange={(e) => setInjectText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && doInject()}
              placeholder={t('process.injectPlaceholder')}
              className="flex-1 rounded-xl border border-violet-200 bg-white px-4 py-2.5 text-sm text-neutral-800 outline-none transition focus:border-violet-400"
            />
            <button
              type="button"
              onClick={doInject}
              disabled={injecting || !injectText.trim()}
              className="rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-violet-700 disabled:opacity-40"
            >
              {injecting ? t('process.injecting') : t('process.inject')}
            </button>
          </div>
          <p className="mt-1.5 text-xs text-neutral-400">{t('process.injectHint')}</p>
        </div>
      )}

      {/* 数据图表（实时：每轮活跃度随模拟推进动态更新） */}
      {view === 'charts' && (
        <div className="flex-1 overflow-auto p-6">
          <ReportCharts actions={actions} />
        </div>
      )}

      {/* 事件流 */}
      {view === 'events' && (
        <div className="flex-1 space-y-4 overflow-auto p-6">
          {posts.length === 0 && (
            <div className="flex h-full items-center justify-center text-sm text-neutral-400">
              {t('process.waitingEvents')}
            </div>
          )}
          {posts.map((a, i) => {
            const isInject = a.action === 'INJECT' || a.agent_id === 'godview'
            return (
              <article
                key={i}
                className={`rounded-2xl border p-5 shadow-sm ${isInject ? 'border-violet-300 bg-violet-50' : 'border-neutral-200 bg-white'
                  }`}
              >
                <div className="mb-3 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span
                      className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold text-white ${isInject ? 'bg-violet-600' : a.platform === 'reddit' ? 'bg-orange-500' : 'bg-sky-500'
                        }`}
                    >
                      {isInject ? '🛰' : a.platform === 'reddit' ? 'R' : 'T'}
                    </span>
                    <span className="text-sm font-medium capitalize text-neutral-800">
                      {isInject ? t('process.godView') : a.platform || 'agent'}
                    </span>
                  </div>
                  <span
                    className={`rounded-md border px-2 py-0.5 text-xs ${isInject ? 'border-violet-300 text-violet-600' : 'border-neutral-200 text-neutral-500'
                      }`}
                  >
                    {a.action}
                  </span>
                </div>
                <p className="text-sm leading-relaxed text-neutral-700">{a.content}</p>
                <div className="mt-3 text-xs text-neutral-400">
                  {a.agent_name || a.agent_id} · R{a.round}
                </div>
              </article>
            )
          })}
        </div>
      )}
    </div>
  )
}
