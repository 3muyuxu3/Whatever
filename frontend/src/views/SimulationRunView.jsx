import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { getActions, getSimulationStatus, startSimulation } from '../api/simulation'
import { useGraphData } from '../hooks/useGraphData'
import ProcessLayout from '../components/ProcessLayout'
import GraphPanel from '../components/GraphPanel'
import Step3Simulation from '../components/Step3Simulation'

/**
 * SimulationRunView —— 流程页 Step 3（开始模拟）
 * 左：实时图谱；右：INFO PLAZA / TOPIC COMMUNITY 统计 + 事件流；底部：模拟监控。
 */
export default function SimulationRunView() {
  const { simulationId } = useParams()
  const [params] = useSearchParams()
  const maxRounds = Number(params.get('maxRounds')) || 10
  const { t } = useTranslation()
  const navigate = useNavigate()

  const [started, setStarted] = useState(false)
  const [status, setStatus] = useState({ round: 0, max_rounds: maxRounds })
  const [actions, setActions] = useState([])
  const [logs, setLogs] = useState([])
  const startedRef = useRef(false)

  const graphId = status?.graph_id
  const { data: graphData, refresh } = useGraphData(graphId, { autoRefresh: started })

  const pushLog = (text, level, tone) =>
    setLogs((l) => [...l.slice(-80), { time: new Date().toLocaleTimeString(), level, text, tone }])

  // 轮询模拟状态（始终）+ 动作日志（开始后）
  useEffect(() => {
    let alive = true
    const poll = async () => {
      try {
        const st = await getSimulationStatus({ simulation_id: simulationId })
        if (!alive) return
        setStatus((s) => ({ ...s, ...st.data }))
        if (startedRef.current) {
          const ac = await getActions({ simulation_id: simulationId })
          if (!alive) return
          const list = ac.data?.actions || []
          setActions(list)
          const last = list[list.length - 1]
          if (last) {
            pushLog(`[${last.platform}] R${last.round} ${last.action}`, undefined, 'accent')
          }
        }
      } catch (e) {
        /* 忽略轮询错误 */
      }
    }
    poll()
    const timer = setInterval(poll, 3000)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [simulationId])

  const handleStart = useCallback(async () => {
    pushLog('启动模拟 …')
    try {
      await startSimulation({ simulation_id: simulationId, max_rounds: maxRounds })
      startedRef.current = true
      setStarted(true)
    } catch (e) {
      pushLog('启动失败', 'ERROR')
    }
  }, [simulationId, maxRounds])

  const status2 = started
    ? { label: t('process.status.processing'), tone: 'orange' }
    : { label: t('process.status.ready'), tone: 'green' }

  return (
    <ProcessLayout
      step={3}
      stepName={t('steps.step3')}
      status={status2}
      defaultView="split"
      primary={
        <GraphPanel
          data={graphData}
          memoryLabel={started ? t('process.memoryUpdating') : undefined}
          onRefresh={refresh}
        />
      }
      secondary={
        <Step3Simulation
          status={status}
          actions={actions}
          started={started}
          onStart={handleStart}
          onGenerateReport={() => navigate(`/report/${simulationId}`)}
        />
      }
      consoleData={{
        title: t('process.monitor'),
        id: `sim_${(simulationId || '').slice(0, 12)}`,
        lines: logs,
      }}
    />
  )
}
