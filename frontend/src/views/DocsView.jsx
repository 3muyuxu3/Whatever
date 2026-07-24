import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import LanguageSwitcher from '../components/LanguageSwitcher'
import Logo from '../components/Logo'
import { GITHUB_URL, ICON_GITHUB } from '../constants'

/**
 * DocsView —— 「文档」页面（参考 trae.cn 文档布局）
 * 浅色主题：顶部栏（品牌 + 搜索 + 语言 + 开始推演）、左侧目录（吸顶 + 滚动高亮 + 搜索过滤）、
 * 右侧数据驱动的正文（段落 / 列表 / 表格），内容全部来自 i18n（pages.docs）。
 */
export default function DocsView() {
    const { t } = useTranslation()
    const nav = t('pages.docs.nav', { returnObjects: true }) || []
    const sections = t('pages.docs.sections', { returnObjects: true }) || []

    const [active, setActive] = useState(nav[0]?.id)
    const [query, setQuery] = useState('')
    const sectionRefs = useRef({})

    // 滚动高亮：section 越过视口上部 ~24% 时置为当前
    useEffect(() => {
        const observer = new IntersectionObserver(
            (entries) => {
                const visible = entries
                    .filter((e) => e.isIntersecting)
                    .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
                if (visible[0]) setActive(visible[0].target.id)
            },
            { rootMargin: '-24% 0px -70% 0px', threshold: 0 },
        )
        Object.values(sectionRefs.current).forEach((el) => el && observer.observe(el))
        return () => observer.disconnect()
    }, [sections.length])

    const filteredNav = useMemo(() => {
        const q = query.trim().toLowerCase()
        if (!q) return nav
        return nav.filter((n) => n.label.toLowerCase().includes(q))
    }, [nav, query])

    const goto = (id) => {
        sectionRefs.current[id]?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }

    // —— 正文块渲染器 ——
    const renderBlock = (block, i) => {
        switch (block.type) {
            case 'h3':
                return (
                    <h3 key={i} className="mb-2 mt-8 text-lg font-semibold text-neutral-900">
                        {block.text}
                    </h3>
                )
            case 'list': {
                const Tag = block.ordered ? 'ol' : 'ul'
                return (
                    <Tag
                        key={i}
                        className={`my-4 space-y-2 pl-6 text-neutral-600 ${block.ordered ? 'list-decimal' : 'list-disc'}`}
                    >
                        {block.items.map((it, k) => (
                            <li key={k} className="leading-7 marker:text-emerald-500">{it}</li>
                        ))}
                    </Tag>
                )
            }
            case 'table':
                return (
                    <div key={i} className="my-6 overflow-x-auto rounded-xl border border-neutral-200">
                        <table className="w-full border-collapse text-left text-sm">
                            <thead>
                                <tr className="bg-emerald-50">
                                    {block.head.map((h, k) => (
                                        <th key={k} className="border-b border-neutral-200 px-4 py-3 font-semibold text-neutral-900">
                                            {h}
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {block.rows.map((row, r) => (
                                    <tr key={r} className="odd:bg-white even:bg-neutral-50/60">
                                        {row.map((cell, c) => (
                                            <td key={c} className="border-b border-neutral-100 px-4 py-3 align-top text-neutral-600">
                                                {cell}
                                            </td>
                                        ))}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )
            case 'p':
            default:
                return (
                    <p key={i} className="my-4 leading-7 text-neutral-600">
                        {block.text}
                    </p>
                )
        }
    }

    return (
        <div className="min-h-screen bg-white text-neutral-800" style={{ colorScheme: 'light' }}>
            {/* ===== 顶部栏 ===== */}
            <header className="sticky top-0 z-40 border-b border-neutral-200 bg-white/90 backdrop-blur">
                <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-6">
                    <Link to="/" className="flex items-center gap-2.5">
                        <Logo className="h-7 w-7 text-neutral-900" />
                        <span className="text-base font-semibold text-neutral-900">{t('pages.docs.brand')}</span>
                    </Link>
                    <div className="flex items-center gap-3">
                        <LanguageSwitcher variant="light" className="hidden sm:block" />
                        <a
                            href={GITHUB_URL}
                            target="_blank"
                            rel="noreferrer"
                            aria-label="GitHub"
                            className="hidden h-9 w-9 items-center justify-center rounded-lg transition hover:bg-neutral-100 sm:flex"
                        >
                            <img src="https://img.icons8.com/ios-glyphs/90/1f2937/github.png" alt="GitHub" className="h-5 w-5" loading="lazy" />
                        </a>
                        <Link
                            to="/#start"
                            className="rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-neutral-700"
                        >
                            {t('nav.start')}
                        </Link>
                    </div>
                </div>
            </header>

            {/* ===== 移动端横向目录 ===== */}
            <nav className="sticky top-16 z-30 flex gap-2 overflow-x-auto border-b border-neutral-200 bg-white/90 px-4 py-2 backdrop-blur lg:hidden">
                {nav.map((n) => (
                    <button
                        key={n.id}
                        type="button"
                        onClick={() => goto(n.id)}
                        className={`whitespace-nowrap rounded-full px-3 py-1.5 text-sm transition ${active === n.id ? 'bg-neutral-900 text-white' : 'bg-neutral-100 text-neutral-600'
                            }`}
                    >
                        {n.label}
                    </button>
                ))}
            </nav>

            <div className="mx-auto flex max-w-7xl gap-10 px-6 py-10">
                {/* ===== 左侧目录 ===== */}
                <aside className="hidden w-60 shrink-0 lg:block">
                    <div className="sticky top-24">
                        <div className="relative mb-4">
                            <input
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                placeholder={t('pages.docs.search')}
                                className="w-full rounded-lg border border-neutral-200 bg-white py-2 pl-9 pr-3 text-sm text-neutral-700 outline-none transition placeholder:text-neutral-400 focus:border-emerald-400"
                            />
                            <img
                                src="https://img.icons8.com/ios/50/9ca3af/search--v1.png"
                                alt=""
                                className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4"
                                loading="lazy"
                            />
                        </div>
                        <ul className="space-y-1 text-sm">
                            {filteredNav.map((n) => (
                                <li key={n.id}>
                                    <button
                                        type="button"
                                        onClick={() => goto(n.id)}
                                        className={`flex w-full items-center rounded-lg border-l-2 px-3 py-2 text-left transition ${active === n.id
                                            ? 'border-emerald-500 bg-emerald-50 font-medium text-neutral-900'
                                            : 'border-transparent text-neutral-500 hover:bg-neutral-50 hover:text-neutral-800'
                                            }`}
                                    >
                                        {n.label}
                                    </button>
                                </li>
                            ))}
                        </ul>
                    </div>
                </aside>

                {/* ===== 正文 ===== */}
                <main className="min-w-0 max-w-3xl flex-1">
                    <h1 className="text-3xl font-semibold tracking-tight text-neutral-900 md:text-4xl">
                        {t('pages.docs.title')}
                    </h1>
                    <p className="mt-4 max-w-2xl leading-7 text-neutral-500">{t('pages.docs.intro')}</p>

                    <div className="mt-4">
                        {sections.map((section) => (
                            <section
                                key={section.id}
                                id={section.id}
                                ref={(el) => (sectionRefs.current[section.id] = el)}
                                className="scroll-mt-28 border-t border-neutral-100 py-10 first:border-t-0"
                            >
                                <div className="mb-4 h-1 w-12 rounded-full bg-emerald-500" />
                                <h2 className="mb-2 text-2xl font-bold text-neutral-900 md:text-3xl">{section.title}</h2>
                                {section.blocks.map(renderBlock)}
                            </section>
                        ))}
                    </div>

                    {/* 底部：返回首页 */}
                    <div className="mt-6 flex items-center justify-between border-t border-neutral-200 py-8 text-sm text-neutral-500">
                        <Link to="/" className="flex items-center gap-2 transition hover:text-neutral-900">
                            <span aria-hidden="true">←</span> {t('pages.backHome')}
                        </Link>
                        <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="flex items-center gap-2 transition hover:text-neutral-900">
                            <img src="https://img.icons8.com/ios-glyphs/90/1f2937/github.png" alt="" className="h-4 w-4" loading="lazy" />
                            {t('footer.github')}
                        </a>
                    </div>
                </main>
            </div>
        </div>
    )
}
