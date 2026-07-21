import { useTranslation } from 'react-i18next'

/**
 * Step2EnvSetup —— 步骤2 工作台：环境搭建（生成人设 + 智能配置）
 *
 * @param {Object}   project    项目（含 graph_id）
 * @param {Array}    entities   已过滤实体
 * @param {boolean}  preparing  是否准备中
 * @param {number}   progress   准备进度
 * @param {Function} onPrepare  触发准备环境
 */
export default function Step2EnvSetup({ project, entities = [], preparing = false, progress = 0, onPrepare }) {
  const { t } = useTranslation()
  const graphReady = !!project?.graph_id

  return (
    <section className="mx-6 mb-6 rounded-2xl border border-neutral-200 bg-white p-6 shadow-sm">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <span className="text-2xl font-bold text-neutral-300">03</span>
          <h3 className="text-lg font-semibold">{t('process.envTitle')}</h3>
        </div>
        <span
          className={`rounded-md border px-2.5 py-1 text-xs font-medium ${preparing
              ? 'border-orange-200 bg-orange-50 text-orange-600'
              : 'border-neutral-200 bg-neutral-100 text-neutral-500'
            }`}
        >
          {preparing ? `${progress}%` : graphReady ? t('process.status.ready') : '—'}
        </span>
      </div>
      <code className="mt-3 block font-mono text-xs text-neutral-400">POST /api/simulation/prepare</code>
      <p className="mt-2 text-sm leading-relaxed text-neutral-500">{t('process.envDesc')}</p>

      <div className="mt-4 flex items-center justify-between text-sm">
        <span className="font-medium text-neutral-700">{t('process.entities')}</span>
        <span className="text-neutral-400">{entities.length}</span>
      </div>
      {entities.length > 0 && (
        <div className="mt-2 grid max-h-40 grid-cols-2 gap-2 overflow-auto">
          {entities.map((e) => (
            <div
              key={e.uuid || e.id || e.name}
              className="truncate rounded-lg border border-neutral-200 bg-neutral-50 px-3 py-2 text-sm"
            >
              <span className="text-neutral-700">{e.name}</span>{' '}
              <span className="text-neutral-400">{e.type}</span>
            </div>
          ))}
        </div>
      )}

      <button
        type="button"
        onClick={onPrepare}
        disabled={!graphReady || preparing}
        className="mt-5 w-full rounded-xl bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-neutral-800 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {preparing ? `${progress}%` : t('process.prepareEnv')}
      </button>
    </section>
  )
}
