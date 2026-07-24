import { useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import LanguageSwitcher from './LanguageSwitcher'
import { GITHUB_URL, ICON_GITHUB } from '../constants'

// 顶部导航项：能力 / 流程 / 理念 / 文档，分别对应四个独立页面
const NAV_ITEMS = [
    { to: '/capabilities', key: 'nav.capabilities' },
    { to: '/workflow', key: 'nav.workflow' },
    { to: '/vision', key: 'nav.vision' },
    { to: '/docs', key: 'nav.docs' },
]

/**
 * SiteHeader —— 子页面通用玻璃态顶部导航
 *
 * 用于「能力 / 流程 / 理念」等深色 3D 页面：吸顶、液态玻璃背景、
 * 高亮当前路由。语言切换、GitHub 入口与「开始推演」主按钮与首页保持一致。
 */
export default function SiteHeader() {
    const { t } = useTranslation()
    const [open, setOpen] = useState(false)

    const linkCls = ({ isActive }) =>
        `transition hover:text-white ${isActive ? 'text-white' : 'text-white/60'}`

    return (
        <header className="sticky top-0 z-50 w-full">
            <div className="px-6 pt-4 md:px-10 lg:px-14">
                <nav className="liquid-glass flex items-center justify-between overflow-visible rounded-xl px-4 py-2.5">
                    {/* 左：Logo → 首页 */}
                    <Link to="/" className="text-xl font-semibold tracking-tight text-white md:text-2xl">
                        SimulMirror
                    </Link>

                    {/* 中：主导航（移动端隐藏） */}
                    <div className="hidden items-center gap-8 text-sm md:flex">
                        {NAV_ITEMS.map((item) => (
                            <NavLink key={item.to} to={item.to} className={linkCls}>
                                {t(item.key)}
                            </NavLink>
                        ))}
                    </div>

                    {/* 右：语言 + GitHub + 主按钮 */}
                    <div className="flex items-center gap-3">
                        <button
                            type="button"
                            onClick={() => setOpen((v) => !v)}
                            aria-label="Menu"
                            className="flex h-9 w-9 items-center justify-center rounded-lg text-white transition hover:bg-white/10 md:hidden"
                        >
                            <span className="text-xl leading-none">☰</span>
                        </button>
                        <LanguageSwitcher className="hidden sm:block" />
                        <a
                            href={GITHUB_URL}
                            target="_blank"
                            rel="noreferrer"
                            aria-label="GitHub"
                            className="flex h-9 w-9 items-center justify-center rounded-lg transition hover:bg-white/10"
                        >
                            <img src={ICON_GITHUB} alt="GitHub" className="h-5 w-5" loading="lazy" />
                        </a>
                        <Link
                            to="/#start"
                            className="rounded-lg bg-white px-5 py-2 text-sm font-medium text-black transition hover:bg-gray-100"
                        >
                            {t('nav.start')}
                        </Link>
                    </div>
                </nav>

                {/* 移动端下拉菜单 */}
                {open && (
                    <div className="liquid-glass mt-2 flex flex-col gap-1 rounded-xl p-2 text-sm md:hidden">
                        {NAV_ITEMS.map((item) => (
                            <NavLink
                                key={item.to}
                                to={item.to}
                                onClick={() => setOpen(false)}
                                className={({ isActive }) =>
                                    `rounded-lg px-4 py-2 text-left transition hover:bg-white/10 ${isActive ? 'text-white' : 'text-white/70'}`
                                }
                            >
                                {t(item.key)}
                            </NavLink>
                        ))}
                        <div className="px-2 py-1">
                            <LanguageSwitcher />
                        </div>
                    </div>
                )}
            </div>
        </header>
    )
}
