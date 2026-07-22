import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { getReport } from '../api/report'
import { getActions, getSimulationStatus } from '../api/simulation'
import { useGraphData } from '../hooks/useGraphData'
import ProcessLayout from '../components/ProcessLayout'
import GraphPanel from '../components/GraphPanel'
import Step5Interaction from '../components/Step5Interaction'

const FALLBACK_OUTLINE = ['背景与概述', '关键实体与关系', '群体舆论演化', '风险与机会', '未来走向预测']

/**
 * InteractionView —— 流程页 Step 5（深度互动）
 * 左：预测报告；右：交互工具 + 与 Report Agent 对话。
 */
export default function InteractionView() {
  const { reportId } = useParams()
  const { t } = useTranslation()
  const outline = t('process.defaultOutline', { returnObjects: true })
  const OUTLINE = Array.isArray(outline) ? outline : FALLBACK_OUTLINE
  const [content, setContent] = useState('')
  const [sim, setSim] = useState({})
  const [actions, setActions] = useState([])
  const [toolTrace, setToolTrace] = useState([])

  // 拉取报告内容，并顺藤摸瓜取到对应模拟的 graph_id / 动作日志
  useEffect(() => {
    getReport(reportId)
      .then(async (res) => {
        setContent(res.data?.content || res.data?.markdown || '')
        setToolTrace(res.data?.tool_trace || [])
        const simId = res.data?.simulation_id
        if (simId) {
          try {
            const s = await getSimulationStatus({ simulation_id: simId })
            setSim(s.data || {})
          } catch (e) {
            /* 忽略 */
          }
          try {
            const ac = await getActions({ simulation_id: simId })
            setActions(ac.data?.actions || [])
          } catch (e) {
            /* 忽略 */
          }
        }
      })
      .catch(() => { })
  }, [reportId])

  const graphId = sim?.graph_id
  const { data: graphData, refresh } = useGraphData(graphId)

  return (
    <ProcessLayout
      step={5}
      stepName={t('steps.step5')}
      status={{ label: t('process.status.ready'), tone: 'green' }}
      defaultView="workbench"
      primary={<GraphPanel data={graphData} graphId={graphId} onRefresh={refresh} />}
      secondary={
        <Step5Interaction
          reportId={reportId}
          simId={sim?.id}
          content={content}
          outline={OUTLINE}
          actions={actions}
          toolTrace={toolTrace}
        />
      }
    />
  )
}
