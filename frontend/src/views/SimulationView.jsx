import { useParams, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

/**
 * SimulationView —— 环境搭建详情页（Step 2）
 * 展示准备完成的模拟环境概览，并提供进入模拟运行的入口。
 */
export default function SimulationView() {
  const { simulationId } = useParams()
  const navigate = useNavigate()
  const { t } = useTranslation()

  return (
    <div className="mx-auto max-w-6xl px-6 py-8 md:px-12">
      <h1 className="mb-2 text-2xl font-medium">{t('steps.step2')}</h1>
      <p className="mb-8 text-sm text-gray-400">ID: {simulationId}</p>

      <button
        type="button"
        onClick={() => navigate(`/simulation/${simulationId}/start`)}
        className="rounded-lg bg-white px-6 py-3 font-medium text-black transition hover:bg-gray-100"
      >
        {t('steps.step3')}
      </button>
    </div>
  )
}
