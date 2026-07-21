import { useTranslation } from 'react-i18next'

// 小徽标
function Badge({ tone = 'gray', children }) {
    const cls = {
        green: 'bg-emerald-50 text-emerald-600 border-emerald-200',
        orange: 'bg-orange-50 text-orange-600 border-orange-200',
        gray: 'bg-neutral-100 text-neutral-500 border-neutral-200',
    }[tone]
    return (
        <span className={`rounded-md border px-2.5 py-1 text-xs font-medium ${cls}`}>{children}</span>
    )
}

// 类型标签
function Tag({ children }) {
    return (
        <span className="rounded-lg border border-neutral-200 bg-neutral-50 px-3 py-1.5 text-sm text-neutral-700">
            {children}
        </span>
    )
}

// 统计块
function Stat({ value, label }) {
    return (
        <div className="rounded-xl bg-neutral-50 p-4 text-center">
            <div className="text-3xl font-bold text-neutral-900">{value}</div>
            <div className="mt-1 text-xs text-neutral-400">{label}</div>
        </div>
    )
}

/**
 * Step1GraphBuild —— 步骤1 工作台：本体生成 + GraphRAG 构建
 *
 * @param {Object} project  项目（含 ontology / graph_id）
 * @param {boolean} building 是否构建中
 * @param {number} progress 构建进度
 * @param {Object} stats    { nodes, edges, schema }
 * @param {Function} onBuild 触发构建
 */
export default function Step1GraphBuild({ project, building = false, progress = 0, stats = {}, onBuild }) {
    const { t } = useTranslation()
    const ontology = project?.ontology || {}
    const entityTypes = (ontology.entity_types || []).map((e) => e.name || e)
    const relationTypes = (ontology.edge_types || []).map((e) => e.name || e)
    const ontologyReady = entityTypes.length > 0
    const graphReady = !!project?.graph_id

    return (
        <div className="space-y-5 p-6">
            {/* 01 本体生成 */}
            <section className="rounded-2xl border border-neutral-200 bg-white p-6 shadow-sm">
                <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                        <span className="text-2xl font-bold text-neutral-300">01</span>
                        <h3 className="text-lg font-semibold">{t('process.ontologyTitle')}</h3>
                    </div>
                    <Badge tone={ontologyReady ? 'green' : 'orange'}>
                        {ontologyReady ? t('process.buildDone') : t('process.building')}
                    </Badge>
                </div>
                <code className="mt-3 block font-mono text-xs text-neutral-400">
                    POST /api/graph/ontology/generate
                </code>
                <p className="mt-2 text-sm leading-relaxed text-neutral-500">
                    {t('process.ontologyDesc')}
                </p>

                <div className="mt-4">
                    <div className="mb-2 text-xs font-semibold tracking-wide text-neutral-400">
                        {t('process.genEntityTypes')}
                    </div>
                    <div className="flex flex-wrap gap-2">
                        {entityTypes.length === 0 && <span className="text-sm text-neutral-400">…</span>}
                        {entityTypes.map((tag) => (
                            <Tag key={tag}>{tag}</Tag>
                        ))}
                    </div>
                </div>

                {relationTypes.length > 0 && (
                    <div className="mt-4">
                        <div className="mb-2 text-xs font-semibold tracking-wide text-neutral-400">
                            {t('process.genRelationTypes')}
                        </div>
                        <div className="flex flex-wrap gap-2">
                            {relationTypes.map((tag) => (
                                <Tag key={tag}>{tag}</Tag>
                            ))}
                        </div>
                    </div>
                )}
            </section>

            {/* 02 GraphRAG 构建 */}
            <section
                className={`rounded-2xl border bg-white p-6 shadow-sm ${building ? 'border-orange-300' : 'border-neutral-200'
                    }`}
            >
                <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                        <span className="text-2xl font-bold text-neutral-300">02</span>
                        <h3 className="text-lg font-semibold">{t('process.graphragTitle')}</h3>
                    </div>
                    <Badge tone={graphReady ? 'green' : building ? 'orange' : 'gray'}>
                        {graphReady ? t('process.buildDone') : building ? `${progress}%` : '—'}
                    </Badge>
                </div>
                <code className="mt-3 block font-mono text-xs text-neutral-400">POST /api/graph/build</code>
                <p className="mt-2 text-sm leading-relaxed text-neutral-500">
                    {t('process.graphragDesc')}
                </p>

                <div className="mt-5 grid grid-cols-3 gap-3">
                    <Stat value={stats.nodes || 0} label={t('process.statNodes')} />
                    <Stat value={stats.edges || 0} label={t('process.statEdges')} />
                    <Stat value={stats.schema || entityTypes.length} label={t('process.statSchema')} />
                </div>

                {!graphReady && (
                    <button
                        type="button"
                        onClick={onBuild}
                        disabled={building || !ontologyReady}
                        className="mt-5 w-full rounded-xl bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-neutral-800 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                        {building ? `${progress}%` : t('process.startBuild')}
                    </button>
                )}
            </section>
        </div>
    )
}
