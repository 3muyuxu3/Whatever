import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

/**
 * NotFound —— 404 页面 / 路由错误兜底
 */
export default function NotFound() {
  const { t } = useTranslation()
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-6 px-6 text-center">
      <h1 className="text-5xl font-light tracking-tight">404</h1>
      <p className="text-gray-400">{t('common.notFound')}</p>
      <Link
        to="/"
        className="rounded-lg bg-white px-6 py-3 font-medium text-black transition hover:bg-gray-100"
      >
        {t('common.backHome')}
      </Link>
    </div>
  )
}
