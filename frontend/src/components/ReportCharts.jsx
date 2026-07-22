import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

// 平台配色
const C_TWITTER = '#0ea5e9'
const C_REDDIT = '#f97316'
const C_INJECT = '#7c3aed'
const C_NEUTRAL = '#94a3b8'

// 动作类型配色（循环取用）
const ACTION_COLORS = [
    '#2563eb', '#059669', '#f59e0b', '#dc2626', '#7c3aed',
    '#0ea5e9', '#65a30d', '#db2777', '#ea580c', '#0d9488',
]

const POST_ACTIONS = ['CREATE_POST', 'QUOTE_POST', 'CREATE_COMMENT']

/** 从动作日志派生统计数据。 */
function derive(actions) {
    const byRound = new Map() // round -> {twitter, reddit}
    const byAction = new Map()
    const byAgent = new Map()
    let twitter = 0
    let reddit = 0
    let posts = 0
    let injections = 0
    const agents = new Set()
    let maxRound = 0

    for (const a of actions) {
        const rnd = Number(a.round || 0)
        maxRound = Math.max(maxRound, rnd)
        const plat = a.platform === 'reddit' ? 'reddit' : 'twitter'
        if (a.platform === 'reddit') reddit += 1
        else if (a.platform === 'twitter') twitter += 1

        const r = byRound.get(rnd) || { twitter: 0, reddit: 0 }
        r[plat] += 1
        byRound.set(rnd, r)

        const act = a.action || 'UNKNOWN'
        byAction.set(act, (byAction.get(act) || 0) + 1)
        if (act === 'INJECT') injections += 1
        if (POST_ACTIONS.includes(act) && a.content) posts += 1

        const aid = a.agent_id
        if (aid && aid !== 'seed' && aid !== 'godview') {
            agents.add(aid)
            const name = a.agent_name || aid
            byAgent.set(name, (byAgent.get(name) || 0) + 1)
        }
    }

    const rounds = []
    for (let i = 0; i <= maxRound; i++) {
        const r = byRound.get(i) || { twitter: 0, reddit: 0 }
        rounds.push({ round: i, ...r })
    }

    const actionList = [...byAction.entries()]
        .sort((a, b) => b[1] - a[1])
        .map(([name, count]) => ({ name, count }))

    const topAgents = [...byAgent.entries()]
        .sort((a, b) => b[1] - a[1])
        .slice(0, 6)
        .map(([name, count]) => ({ name, count }))

    return {
        rounds,
        actionList,
        topAgents,
        twitter,
        reddit,
        posts,
        injections,
        total: actions.length,
        agentCount: agents.size,
        maxRound,
    }
}

/** 顶部统计小卡。 */
function Stat({ value, label, tone = 'text-neutral-900' }) {
    return (
        <div className="rounded-xl border border-neutral-200 bg-white p-3 text-center shadow-sm">
            <div className={`text-2xl font-bold ${tone}`}>{value}</div>
            <div className="mt-0.5 text-[11px] leading-tight text-neutral-400">{label}</div>
        </div>
    )
}

/** 多序列折线 / 面积图：各平台每轮活跃度。 */
function ActivityChart({ rounds }) {
    const { t } = useTranslation()
    const W = 320
    const H = 120
    const P = 18
    const maxY = Math.max(1, ...rounds.map((r) => Math.max(r.twitter, r.reddit)))
    const n = Math.max(1, rounds.length - 1)
    const x = (i) => P + (i * (W - 2 * P)) / n
    const y = (v) => H - P - (v * (H - 2 * P)) / maxY

    const series = [
        { key: 'twitter', color: C_TWITTER },
        { key: 'reddit', color: C_REDDIT },
    ]

    const linePath = (key) =>
        rounds.map((r, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)} ${y(r[key]).toFixed(1)}`).join(' ')
    const areaPath = (key) =>
        `${linePath(key)} L${x(rounds.length - 1).toFixed(1)} ${y(0)} L${x(0).toFixed(1)} ${y(0)} Z`

    return (
        <div className="rounded-2xl border border-neutral-200 bg-white p-4 shadow-sm">
            <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-semibold text-neutral-700">{t('process.chartActivity')}</span>
                <div className="flex items-center gap-3 text-[11px] text-neutral-500">
                    <span className="flex items-center gap-1">
                        <span className="inline-block h-2 w-2 rounded-full" style={{ background: C_TWITTER }} /> Twitter
                    </span>
                    <span className="flex items-center gap-1">
                        <span className="inline-block h-2 w-2 rounded-full" style={{ background: C_REDDIT }} /> Reddit
                    </span>
                </div>
            </div>
            <svg viewBox={`0 0 ${W} ${H}`} className="h-32 w-full">
                <line x1={P} y1={H - P} x2={W - P} y2={H - P} stroke="#e5e7eb" strokeWidth="1" />
                {series.map((s) => (
                    <g key={s.key}>
                        <path d={areaPath(s.key)} fill={s.color} opacity="0.12" />
                        <path d={linePath(s.key)} fill="none" stroke={s.color} strokeWidth="2" />
                    </g>
                ))}
            </svg>
            <div className="mt-1 flex justify-between text-[10px] text-neutral-400">
                <span>R0</span>
                <span>R{rounds.length ? rounds[rounds.length - 1].round : 0}</span>
            </div>
        </div>
    )
}

/** 甜甜圈：平台占比。 */
function PlatformDonut({ twitter, reddit }) {
    const { t } = useTranslation()
    const total = twitter + reddit
    const r = 38
    const cx = 50
    const cy = 50
    const C = 2 * Math.PI * r
    const fTw = total ? twitter / total : 0
    const fRe = total ? reddit / total : 0

    return (
        <div className="rounded-2xl border border-neutral-200 bg-white p-4 shadow-sm">
            <div className="mb-2 text-sm font-semibold text-neutral-700">{t('process.chartPlatform')}</div>
            <div className="flex items-center gap-4">
                <svg viewBox="0 0 100 100" className="h-24 w-24 shrink-0">
                    <g transform="rotate(-90 50 50)">
                        <circle cx={cx} cy={cy} r={r} fill="none" stroke="#f1f5f9" strokeWidth="12" />
                        <circle
                            cx={cx} cy={cy} r={r} fill="none" stroke={C_TWITTER} strokeWidth="12"
                            strokeDasharray={`${(fTw * C).toFixed(2)} ${C.toFixed(2)}`} strokeDashoffset="0"
                        />
                        <circle
                            cx={cx} cy={cy} r={r} fill="none" stroke={C_REDDIT} strokeWidth="12"
                            strokeDasharray={`${(fRe * C).toFixed(2)} ${C.toFixed(2)}`}
                            strokeDashoffset={`${(-fTw * C).toFixed(2)}`}
                        />
                    </g>
                    <text x="50" y="54" textAnchor="middle" className="fill-neutral-700" style={{ fontSize: 14, fontWeight: 700 }}>
                        {total}
                    </text>
                </svg>
                <div className="space-y-2 text-sm">
                    <div className="flex items-center gap-2">
                        <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: C_TWITTER }} />
                        <span className="text-neutral-600">Twitter</span>
                        <b className="ml-auto text-neutral-800">{twitter}</b>
                    </div>
                    <div className="flex items-center gap-2">
                        <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: C_REDDIT }} />
                        <span className="text-neutral-600">Reddit</span>
                        <b className="ml-auto text-neutral-800">{reddit}</b>
                    </div>
                </div>
            </div>
        </div>
    )
}

/** 水平条形图：动作类型分布 / 活跃 Agent。 */
function BarList({ title, items, colorFn }) {
    const max = Math.max(1, ...items.map((i) => i.count))
    return (
        <div className="rounded-2xl border border-neutral-200 bg-white p-4 shadow-sm">
            <div className="mb-3 text-sm font-semibold text-neutral-700">{title}</div>
            {items.length === 0 && <p className="text-xs text-neutral-400">—</p>}
            <div className="space-y-2">
                {items.map((it, i) => (
                    <div key={it.name} className="flex items-center gap-2">
                        <span className="w-28 shrink-0 truncate text-xs text-neutral-600" title={it.name}>
                            {it.name}
                        </span>
                        <div className="h-3 flex-1 overflow-hidden rounded-full bg-neutral-100">
                            <div
                                className="h-full rounded-full"
                                style={{ width: `${(it.count / max) * 100}%`, background: colorFn(i) }}
                            />
                        </div>
                        <span className="w-8 shrink-0 text-right text-xs font-medium text-neutral-700">{it.count}</span>
                    </div>
                ))}
            </div>
        </div>
    )
}

/**
 * ReportCharts —— 报告数据可视化（由模拟动作日志派生）
 *
 * 统计卡 + 每轮活跃度折线 + 平台占比甜甜圈 + 动作类型分布 + 活跃 Agent 排行。
 */
export default function ReportCharts({ actions = [] }) {
    const { t } = useTranslation()
    const d = useMemo(() => derive(actions), [actions])

    if (!actions.length) {
        return (
            <div className="rounded-2xl border border-dashed border-neutral-200 bg-neutral-50 p-6 text-center text-sm text-neutral-400">
                {t('process.noSimData')}
            </div>
        )
    }

    return (
        <div className="space-y-4">
            <div className="grid grid-cols-3 gap-2">
                <Stat value={d.maxRound + 1} label={t('process.statRounds')} />
                <Stat value={d.total} label={t('process.statActions')} />
                <Stat value={d.posts} label={t('process.statPosts')} />
                <Stat value={d.agentCount} label={t('process.statAgents')} />
                <Stat value={d.injections} label={t('process.godView')} tone="text-violet-600" />
                <Stat value={`${d.twitter}/${d.reddit}`} label="T / R" />
            </div>

            <ActivityChart rounds={d.rounds} />

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <PlatformDonut twitter={d.twitter} reddit={d.reddit} />
                <BarList
                    title={t('process.chartTopAgents')}
                    items={d.topAgents}
                    colorFn={() => C_NEUTRAL}
                />
            </div>

            <BarList
                title={t('process.chartActions')}
                items={d.actionList}
                colorFn={(i) => ACTION_COLORS[i % ACTION_COLORS.length]}
            />
        </div>
    )
}
