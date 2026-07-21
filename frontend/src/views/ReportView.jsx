import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { generateReport, getReport, getReportStatus } from '../api/report'
import { getSimulationStatus } from '../api/simulation'
import { useGraphData } from '../hooks/useGraphData'
import ProcessLayout from '../components/ProcessLayout'
import GraphPanel from '../components/GraphPanel'
import Step4Report from '../components/Step4Report'

// 报告章节骨架（生成中展示）
const OUTLINE = ['背景与概述', '关键实体与关系', '群体舆论演化', '风险与机会', '未来走向预测']

/**
 * ReportView —— 流程页 Step 4（报告生成）
 * 进入后自动触发报告生成，左侧报告正文，右侧工具调用结果，底部控制台。
 */
export default function ReportView() {
  // 路由参数携带模拟 ID（Step3 跳转而来）
  const { reportId: simulationId } = useParams()
  const { t } = useTranslation()
  const navigate = useNavigate()

  const [content, setContent] = useState('')
  const [generating, setGenerating] = useState(false)
  const [reportId, setReportId] = useState(null)
  const [sim, setSim] = useState({})
  const [logs, setLogs] = useState([])
  const startedRef = useRef(false)

  const graphId = sim?.graph_id
  const { data: graphData, refresh } = useGraphData(graphId)
  const stats = {
    nodes: graphData?.nodes?.length || 0,
    edges: graphData?.edges?.length || 0,
  }

  const pushLog = (text, level) =>
    setLogs((l) => [...l.slice(-80), { time: new Date().toLocaleTimeString(), level, text }])

  // 获取模拟信息（graph_id / requirement）
  useEffect(() => {
    getSimulationStatus({ simulation_id: simulationId })
      .then((res) => setSim(res.data || {}))
      .catch(() => { })
  }, [simulationId])

  // 自动开始生成报告（仅一次）
  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true
    setGenerating(true)
    pushLog('开始生成报告 …')
      ; (async () => {
        try {
          const res = await generateReport({ simulation_id: simulationId })
          const rid = res.data?.report_id || res.data?.id
          setReportId(rid)
          pushLog(`报告任务已启动 … ${rid || ''}`)
          const timer = setInterval(async () => {
            try {
              const st = await getReportStatus({ report_id: rid })
              pushLog(`生成进度 ${st.data?.progress || 0}%`)
              if (st.data?.status === 'completed') {
                clearInterval(timer)
                const rep = await getReport(rid)
                setContent(rep.data?.content || rep.data?.markdown || '')
                setGenerating(false)
                pushLog('报告生成完成')
              } else if (st.data?.status === 'failed') {
                clearInterval(timer)
                setGenerating(false)
                pushLog('报告生成失败', 'ERROR')
              }
            } catch (e) {
              clearInterval(timer)
              setGenerating(false)
            }
          }, 3000)
        } catch (e) {
          setGenerating(false)
          pushLog('报告启动失败', 'ERROR')
        }
      })()
  }, [simulationId])

  const goInteract = useCallback(() => {
    if (reportId) navigate(`/interaction/${reportId}`)
  }, [reportId, navigate])

  const status = generating
    ? { label: t('process.status.generating'), tone: 'orange' }
    : { label: t('process.status.done'), tone: 'green' }

  return (
    <ProcessLayout
      step={4}
      stepName={t('steps.step4')}
      status={status}
      defaultView="workbench"
      primary={<GraphPanel data={graphData} onRefresh={refresh} />}
      secondary={
        <Step4Report
          reportId={reportId}
          content={content}
          generating={generating}
          outline={OUTLINE}
          stats={stats}
          requirement={sim?.requirement}
          onInteract={reportId ? goInteract : undefined}
        />
      }
      consoleData={{
        title: t('process.consoleOutput'),
        id: `report_${(reportId || '').slice(0, 12)}`,
        lines: logs,
      }}
    />
  )
}
