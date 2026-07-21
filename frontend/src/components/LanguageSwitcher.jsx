import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SUPPORTED_LANGUAGES } from '../i18n'

/**
 * LanguageSwitcher —— 语言切换器
 *
 * 点击展开语言列表，选择后调用 i18n.changeLanguage 切换语言，
 * 并由 i18n 的 languageChanged 事件持久化到 localStorage。
 */
export default function LanguageSwitcher({ className = '' }) {
    const { i18n, t } = useTranslation()
    const [open, setOpen] = useState(false)
    const ref = useRef(null)

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

    return (
        <div className={`relative ${className}`} ref={ref}>
            <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                aria-label={t('language')}
                className="liquid-glass flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-white transition hover:text-gray-300"
            >
                {/* 地球图标（来自 icons8） */}
                <img
                    src="https://img.icons8.com/ios-glyphs/90/ffffff/globe--v1.png"
                    alt=""
                    className="h-4 w-4 opacity-90"
                    loading="lazy"
                />
                <span>{current.label}</span>
            </button>

            {open && (
                <ul className="liquid-glass absolute right-0 z-50 mt-2 w-40 overflow-hidden rounded-lg py-1 text-sm">
                    {SUPPORTED_LANGUAGES.map((lang) => (
                        <li key={lang.code}>
                            <button
                                type="button"
                                onClick={() => changeLang(lang.code)}
                                className={`block w-full px-4 py-2 text-left transition hover:bg-white/10 ${lang.code === current.code ? 'text-white' : 'text-gray-300'
                                    }`}
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
