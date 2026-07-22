import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import ConsolePanel from './ConsolePanel'
import LanguageSwitcher from './LanguageSwitcher'

const GITHUB_URL = 'https://github.com/3muyuxu3/muyuxu'

// 状态圆点颜色
const TONE = {
    orange: 'bg-orange-500',
    green: 'bg-emerald-500',
    gray: 'bg-neutral-400',
}

/**
 * ProcessLayout —— 流程页统一外壳（浅色主题，参考 MiroFish 布局）
 *
 * 顶部导航：返回 · Logo · 视图切换(图谱/双栏/工作台) · Step X/5 + 状态 · 语言 · GitHub
 * 主体：按视图模式在 primary（左，图谱/报告）与 secondary（右，工作台）之间切换布局
 * 底部：可选的黑色控制台日志面板
 *
 * @param {number} step         当前步骤 1-5
 * @param {string} stepName     步骤名称
 * @param {{label,tone}} status 状态（label + tone: orange|green|gray）
 * @param {'graph'|'split'|'workbench'} defaultView 默认视图
 * @param {ReactNode} primary   左侧主区（通常是图谱）
 * @param {ReactNode} secondary 右侧工作台
 * @param {{title,id,lines}} consoleData 底部控制台数据（可选）
 */
export default function ProcessLayout({
    step,
    stepName,
    status = { label: '', tone: 'orange' },
    defaultView = 'split',
    primary,
    secondary,
    consoleData,
}) {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const [view, setView] = useState(defaultView)

    const VIEW_TABS = [
        { key: 'graph', label: t('process.views.graph') },
        { key: 'split', label: t('process.views.split') },
        { key: 'workbench', label: t('process.views.workbench') },
    ]

    // 控制台面板：双栏视图时嵌入右栏底部，其余视图全宽置底
    const consoleEl = consoleData ? (
        <ConsolePanel
            title={consoleData.title}
            id={consoleData.id}
            lines={consoleData.lines}
            className="h-44 shrink-0"
        />
    ) : null

    return (
        <div className="flex h-screen flex-col bg-neutral-50 text-neutral-900">
            {/* ============ 顶部导航 ============ */}
            <header className="flex shrink-0 items-center justify-between border-b border-neutral-200 bg-white px-4 py-3">
                {/* 左：返回 + Logo */}
                <div className="flex items-center gap-3">
                    <button
                        type="button"
                        onClick={() => navigate('/')}
                        aria-label="Back"
                        className="flex h-9 w-9 items-center justify-center rounded-lg border border-neutral-200 text-neutral-600 transition hover:bg-neutral-100"
                    >
                        <span className="text-lg leading-none">←</span>
                    </button>
                    <div className="flex items-center gap-2">
                        <span className="inline-block h-7 w-7 rounded-lg bg-gradient-to-br from-sky-400 to-indigo-500" />
                        <span className="text-lg font-semibold tracking-tight">SimulMirror</span>
                    </div>
                </div>

                {/* 中：视图切换 */}
                <div className="hidden items-center gap-1 rounded-xl bg-neutral-100 p-1 md:flex">
                    {VIEW_TABS.map((tab) => (
                        <button
                            key={tab.key}
                            type="button"
                            onClick={() => setView(tab.key)}
                            className={`rounded-lg px-4 py-1.5 text-sm font-medium transition ${view === tab.key
                                ? 'bg-white text-neutral-900 shadow-sm'
                                : 'text-neutral-500 hover:text-neutral-800'
                                }`}
                        >
                            {tab.label}
                        </button>
                    ))}
                </div>

                {/* 右：步骤 + 状态 + 语言 + GitHub */}
                <div className="flex items-center gap-3">
                    <div className="hidden items-center gap-2 md:flex">
                        <span className="text-sm text-neutral-400">Step {step}/5</span>
                        <span className="text-sm font-semibold">{stepName}</span>
                        {status.label && (
                            <span className="ml-1 flex items-center gap-1.5 text-sm text-neutral-500">
                                <span className={`h-2 w-2 rounded-full ${TONE[status.tone] || TONE.orange}`} />
                                {status.label}
                            </span>
                        )}
                    </div>
                    <LanguageSwitcher variant="light" />
                    <a
                        href={GITHUB_URL}
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-center gap-2 rounded-lg bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-neutral-800"
                    >
                        <img
                            src="https://img.icons8.com/ios-glyphs/90/ffffff/github.png"
                            alt=""
                            className="h-4 w-4"
                            loading="lazy"
                        />
                        GitHub
                    </a>
                </div>
            </header>

            {/* ============ 主体 ============ */}
            <div className="flex min-h-0 flex-1">
                {(view === 'graph' || view === 'split') && (
                    <div
                        className={`min-w-0 ${view === 'split' ? 'w-1/2 border-r border-neutral-200' : 'flex-1'}`}
                    >
                        {primary}
                    </div>
                )}
                {(view === 'workbench' || view === 'split') && (
                    <div className={`flex min-h-0 min-w-0 flex-col ${view === 'split' ? 'w-1/2' : 'flex-1'}`}>
                        <div className="min-h-0 flex-1 overflow-auto">{secondary}</div>
                        {/* 双栏时控制台跟随右栏，避免左侧图谱下方出现大片黑色空白 */}
                        {view === 'split' && consoleEl}
                    </div>
                )}
            </div>

            {/* ============ 底部控制台（非双栏视图时全宽置底） ============ */}
            {view !== 'split' && consoleEl}
        </div>
    )
}
