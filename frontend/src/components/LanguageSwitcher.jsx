import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SUPPORTED_LANGUAGES } from '../i18n'

/**
 * LanguageSwitcher —— 语言切换器
 *
 * 点击展开语言列表，选择后调用 i18n.changeLanguage 切换语言，
 * 并由 i18n 的 languageChanged 事件持久化到 localStorage。
 *
 * @param {string} variant 'dark'（首页液态玻璃）| 'light'（流程页浅色主题）
 */
export default function LanguageSwitcher({ className = '', variant = 'dark' }) {
    const { i18n, t } = useTranslation()
    const [open, setOpen] = useState(false)
    const ref = useRef(null)
    const isLight = variant === 'light'

    // 点击外部区域时关闭下拉
    useEffect(() => {
        const onClick = (e) => {
            if (ref.current && !ref.current.contains(e.target)) setOpen(false)
        }
        document.addEventListener('mousedown', onClick)
        return () => document.removeEventListener('mousedown', onClick)
    }, [])

    // 归一化当前语言（zh-CN -> zh）
    const current =
        SUPPORTED_LANGUAGES.find((l) => i18n.language?.startsWith(l.code)) ||
        SUPPORTED_LANGUAGES[0]

    const changeLang = (code) => {
        i18n.changeLanguage(code)
        setOpen(false)
    }

    const btnCls = isLight
        ? 'flex items-center gap-2 rounded-lg border border-neutral-200 bg-white px-3 py-1.5 text-sm text-neutral-600 transition hover:bg-neutral-100'
        : 'liquid-glass flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-white transition hover:text-gray-300'
    const globeIcon = isLight
        ? 'https://img.icons8.com/ios-glyphs/90/6b7280/globe--v1.png'
        : 'https://img.icons8.com/ios-glyphs/90/ffffff/globe--v1.png'
    const menuCls = isLight
        ? 'absolute right-0 z-50 mt-2 w-40 overflow-hidden rounded-lg border border-neutral-200 bg-white py-1 text-sm shadow-lg'
        : 'liquid-glass absolute right-0 z-50 mt-2 w-40 overflow-hidden rounded-lg py-1 text-sm'
    const itemCls = (active) =>
        isLight
            ? `block w-full px-4 py-2 text-left transition hover:bg-neutral-100 ${active ? 'font-medium text-neutral-900' : 'text-neutral-500'}`
            : `block w-full px-4 py-2 text-left transition hover:bg-white/10 ${active ? 'text-white' : 'text-gray-300'}`

    return (
        <div className={`relative ${className}`} ref={ref}>
            <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                aria-label={t('language')}
                className={btnCls}
            >
                {/* 地球图标（来自 icons8） */}
                <img src={globeIcon} alt="" className="h-4 w-4 opacity-90" loading="lazy" />
                <span>{current.label}</span>
            </button>

            {open && (
                <ul className={menuCls}>
                    {SUPPORTED_LANGUAGES.map((lang) => (
                        <li key={lang.code}>
                            <button
                                type="button"
                                onClick={() => changeLang(lang.code)}
                                className={itemCls(lang.code === current.code)}
                            >
                                {lang.label}
                            </button>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    )
}
