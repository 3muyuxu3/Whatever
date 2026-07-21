import { useTranslation } from 'react-i18next'

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
export default function Step3Simulation({ status, actions = [], started, onStart, onGenerateReport }) {
  const { t } = useTranslation()
  const round = status?.round || 0
  const maxRounds = status?.max_rounds || 40

  const plaza = actions.filter((a) => a.platform === 'twitter')
  const community = actions.filter((a) => a.platform === 'reddit')
  const posts = actions
    .filter((a) => ['CREATE_POST', 'QUOTE_POST', 'CREATE_COMMENT'].includes(a.action) && a.content)
    .slice(-30)
    .reverse()

  return (
    <div className="flex h-full flex-col">
      {/* 顶部：两张统计卡 + 生成报告按钮 */}
      <div className="flex items-stretch gap-4 border-b border-neutral-200 p-6">
        <StatCard icon={ICON_GLOBE} title={t('process.infoPlaza')} round={round} maxRounds={maxRounds} acts={plaza.length} />
        <StatCard icon={ICON_CHAT} title={t('process.topicCommunity')} round={round} maxRounds={maxRounds} acts={community.length} />
        <button
          type="button"
          onClick={started ? onGenerateReport : onStart}
          className="shrink-0 self-center rounded-xl bg-neutral-900 px-5 py-3 text-sm font-medium text-white transition hover:bg-neutral-800"
        >
          {started ? `${t('process.startReport')} →` : `${t('process.startSim')} →`}
        </button>
      </div>

      {/* TOTAL EVENTS */}
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
      </div>

      {/* 事件流 */}
      <div className="flex-1 space-y-4 overflow-auto p-6">
        {posts.length === 0 && (
          <div className="flex h-full items-center justify-center text-sm text-neutral-400">
            {t('process.waitingEvents')}
          </div>
        )}
        {posts.map((a, i) => (
          <article key={i} className="rounded-2xl border border-neutral-200 bg-white p-5 shadow-sm">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span
                  className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold text-white ${a.platform === 'reddit' ? 'bg-orange-500' : 'bg-sky-500'
                    }`}
                >
                  {a.platform === 'reddit' ? 'R' : 'T'}
                </span>
                <span className="text-sm font-medium capitalize text-neutral-800">
                  {a.platform || 'agent'}
                </span>
              </div>
              <span className="rounded-md border border-neutral-200 px-2 py-0.5 text-xs text-neutral-500">
                {a.action}
              </span>
            </div>
            <p className="text-sm leading-relaxed text-neutral-700">{a.content}</p>
            <div className="mt-3 text-xs text-neutral-400">
              {a.agent_name || a.agent_id} · R{a.round}
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}
