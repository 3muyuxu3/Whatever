import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { GITHUB_URL, ICON_GITHUB } from '../constants'

// 子页面通用页脚：品牌 + 版权 + GitHub + 返回首页
const FOOTER_LINKS = [
    { to: '/capabilities', key: 'nav.capabilities' },
    { to: '/workflow', key: 'nav.workflow' },
    { to: '/vision', key: 'nav.vision' },
    { to: '/docs', key: 'nav.docs' },
]

/**
 * SiteFooter —— 「能力 / 流程 / 理念」等深色页面的通用页脚
 */
export default function SiteFooter() {
    const { t } = useTranslation()
    return (
        <footer className="border-t border-white/10 bg-black px-6 py-12 md:px-10 lg:px-14">
            <div className="mx-auto flex max-w-6xl flex-col gap-8 sm:flex-row sm:items-start sm:justify-between">
                <div>
                    <div className="text-lg font-semibold tracking-tight text-white">SimulMirror</div>
                    <div className="mt-1 text-sm text-white/50">{t('footer.tagline')}</div>
                </div>
                <div className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
                    {FOOTER_LINKS.map((item) => (
                        <Link key={item.to} to={item.to} className="text-white/60 transition hover:text-white">
                            {t(item.key)}
                        </Link>
                    ))}
                    <a
                        href={GITHUB_URL}
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-center gap-2 text-white/60 transition hover:text-white"
                    >
                        <img src={ICON_GITHUB} alt="" className="h-4 w-4" loading="lazy" />
                        {t('footer.github')}
                    </a>
                </div>
            </div>
            <div className="mx-auto mt-8 flex max-w-6xl items-center justify-between text-xs text-white/40">
                <span>© {new Date().getFullYear()} {t('footer.rights')}</span>
                <Link to="/" className="transition hover:text-white/70">{t('pages.backHome')}</Link>
            </div>
        </footer>
    )
}
