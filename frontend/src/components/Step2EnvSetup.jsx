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
export default function Step2EnvSetup({ project, entities = [], preparing = false, progress = 0, profiles = [], total = null, onPrepare }) {
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

      {/* 人设实时流式展示（环境搭建阶段，边生成边展示，） */}
      {(preparing || profiles.length > 0) && (
        <div className="mt-4">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="font-medium text-neutral-700">{t('process.personas')}</span>
            <span className="text-neutral-400">
              {profiles.length}{total ? ` / ${total}` : ''}
            </span>
          </div>
          {profiles.length === 0 ? (
            <div className="flex items-center gap-2 py-3 text-sm text-neutral-400">
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-neutral-300 border-t-transparent" />
              {t('process.preparingAgents')}
            </div>
          ) : (
            <div className="grid max-h-56 grid-cols-1 gap-2 overflow-auto sm:grid-cols-2">
              {profiles.map((p, i) => (
                <div
                  key={p.entity_uuid || p.name || i}
                  className="rounded-lg border border-neutral-200 bg-neutral-50 p-2.5"
                >
                  <div className="flex items-center gap-2">
                    <span className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-sky-400 to-indigo-500 text-xs font-bold text-white">
                      {(p.name || '?').trim().charAt(0).toUpperCase()}
                    </span>
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-neutral-800">{p.name}</div>
                      <div className="truncate text-[11px] text-neutral-400">
                        {[p.occupation, p.mbti].filter(Boolean).join(' · ') || '—'}
                      </div>
                    </div>
                  </div>
                  {p.bio && (
                    <p className="mt-1.5 line-clamp-2 text-[11px] leading-relaxed text-neutral-500">{p.bio}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
