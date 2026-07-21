import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { startSimulation } from '../api/simulation'
import { getActions } from '../api/simulation'
import { useSimulationStatus } from '../hooks/useSimulationStatus'
import { useGraphData } from '../hooks/useGraphData'
import GraphPanel from './GraphPanel'

/**
 * Step3Simulation —— 步骤3：模拟运行
 * 启动双平台并行模拟；GraphPanel 每 30 秒自动刷新以展示社会演化实时动态。
 */
export default function Step3Simulation({ simulationId, graphId, maxRounds = 10 }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [started, setStarted] = useState(false)
  const [actions, setActions] = useState([])

  // 实时监控模拟状态
  const { status } = useSimulationStatus(simulationId, { enabled: started })
  // 模拟运行期间每 30 秒自动刷新图谱
  const { data, loading } = useGraphData(graphId, { autoRefresh: started })

  const handleStart = async () => {
    try {
      await startSimulation({ simulation_id: simulationId, max_rounds: maxRounds })
      setStarted(true)
      // 定时拉取动作日志
      setInterval(async () => {
        try {
          const res = await getActions({ simulation_id: simulationId })
          setActions(res.data?.actions || [])
        } catch (e) {
          /* 忽略 */
        }
      }, 5000)
    } catch (e) {
      /* 忽略 */
    }
  }

  const statusText = status
    ? `${t('steps.step3')} · ${status.status || ''} · ${status.round || 0}/${maxRounds}`
    : t('steps.step3')

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-xl font-medium">{t('steps.step3')}</h2>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={handleStart}
            disabled={started}
            className="rounded-lg bg-white px-5 py-2 text-sm font-medium text-black transition hover:bg-gray-100 disabled:opacity-50"
          >
            {started ? status?.status || '...' : t('steps.step3')}
          </button>
          <button
            type="button"
            onClick={() => navigate(`/report/${simulationId}`)}
            className="liquid-glass rounded-lg px-5 py-2 text-sm text-white"
          >
            {t('steps.step4')}
          </button>
        </div>
      </div>

      <GraphPanel data={data} loading={loading} statusText={statusText} />

      {/* 动作日志（实时） */}
      {actions.length > 0 && (
        <div className="liquid-glass mt-6 max-h-60 overflow-auto rounded-xl p-4 text-xs">
          {actions.slice(-50).map((a, i) => (
            <div key={i} className="border-b border-white/5 py-1 text-gray-300">
              <span className="text-gray-500">[{a.platform || ''}]</span>{' '}
              <span className="text-white">{a.agent_name || a.agent_id}</span>{' '}
              {a.action} {a.content ? `— ${a.content}` : ''}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
