import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import {
  getEntities,
  createSimulation,
  prepareSimulation,
  getPrepareStatus,
} from '../api/simulation'

/**
 * Step2EnvSetup —— 步骤2：环境搭建
 * 展示过滤后的图谱实体，创建模拟并异步准备环境（生成 Profile / 模拟配置）。
 */
export default function Step2EnvSetup({ project }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const graphId = project?.graph_id || project?.id
  const [entities, setEntities] = useState([])
  const [preparing, setPreparing] = useState(false)
  const [progress, setProgress] = useState(0)

  // 加载已过滤实体
  useEffect(() => {
    if (!graphId) return
    getEntities(graphId)
      .then((res) => setEntities(res.data?.entities || res.data || []))
      .catch(() => setEntities([]))
  }, [graphId])

  // 创建模拟并准备环境
  const handlePrepare = async () => {
    setPreparing(true)
    try {
      const created = await createSimulation({ project_id: project?.id })
      const simId = created.data?.simulation_id || created.data?.id
      await prepareSimulation({ simulation_id: simId })
      const timer = setInterval(async () => {
        try {
          const res = await getPrepareStatus({ simulation_id: simId })
          setProgress(res.data?.progress || 0)
          if (res.data?.status === 'completed') {
            clearInterval(timer)
            navigate(`/simulation/${simId}`)
          }
        } catch (e) {
          clearInterval(timer)
          setPreparing(false)
        }
      }, 2000)
    } catch (e) {
      setPreparing(false)
    }
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-xl font-medium">{t('steps.step2')}</h2>
        <button
          type="button"
          onClick={handlePrepare}
          disabled={preparing}
          className="rounded-lg bg-white px-5 py-2 text-sm font-medium text-black transition hover:bg-gray-100 disabled:opacity-50"
        >
          {preparing ? `${progress}%` : t('common.next')}
        </button>
      </div>

      {/* 实体列表 */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {entities.length === 0 && (
          <p className="text-sm text-gray-500">{t('common.loading')}</p>
        )}
        {entities.map((e) => (
          <div key={e.uuid || e.id} className="liquid-glass rounded-xl p-4">
            <div className="font-medium text-white">{e.name}</div>
            <div className="text-xs text-gray-400">
              {e.type || (Array.isArray(e.labels) ? e.labels.join(', ') : '')}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
