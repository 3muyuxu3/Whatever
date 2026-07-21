import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import HttpBackend from 'i18next-http-backend'
import LanguageDetector from 'i18next-browser-languagedetector'

/**
 * 支持的语言列表（至少 7 种：中文、English、Español、Français、Português、Русский、Deutsch）
 * label 用于语言切换器展示，code 为 i18next 语言标识。
 */
export const SUPPORTED_LANGUAGES = [
    { code: 'zh', label: '中文' },
    { code: 'en', label: 'English' },
    { code: 'es', label: 'Español' },
    { code: 'fr', label: 'Français' },
    { code: 'pt', label: 'Português' },
    { code: 'ru', label: 'Русский' },
    { code: 'de', label: 'Deutsch' },
]

// localStorage 中持久化语言的键名
export const LANG_STORAGE_KEY = 'simulmirror_lang'

i18n
    // 通过 HTTP 后端动态加载 /public/locales 下的语言资源
    .use(HttpBackend)
    // 自动检测浏览器/本地存储中的语言
    .use(LanguageDetector)
    // 接入 react-i18next
    .use(initReactI18next)
    .init({
        fallbackLng: 'zh',
        supportedLngs: SUPPORTED_LANGUAGES.map((l) => l.code),
        ns: ['translation'],
        defaultNS: 'translation',
        load: 'languageOnly', // 将 zh-CN 归一化为 zh
        backend: {
            // 语言文件位于 public/locales/<lng>/translation.json，构建后作为静态资源提供
            loadPath: '/locales/{{lng}}/{{ns}}.json',
        },
        detection: {
            order: ['localStorage', 'navigator', 'htmlTag'],
            caches: ['localStorage'],
            lookupLocalStorage: LANG_STORAGE_KEY,
        },
        interpolation: {
            escapeValue: false, // React 已对 XSS 做转义
        },
    })

// 语言切换后：持久化并同步 <html lang> 属性
i18n.on('languageChanged', (lng) => {
    try {
        localStorage.setItem(LANG_STORAGE_KEY, lng)
    } catch (e) {
        // 忽略隐私模式下 localStorage 不可用的情况
    }
    document.documentElement.lang = lng
})

export default i18n
