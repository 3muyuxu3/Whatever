import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { generateReport, getReport, getReportLog } from '../api/report'
import { getActions, getSimulationStatus } from '../api/simulation'
import { useGraphData } from '../hooks/useGraphData'
import ProcessLayout from '../components/ProcessLayout'
import GraphPanel from '../components/GraphPanel'
import Step4Report from '../components/Step4Report'

// 报告章节骨架（生成中展示，从 i18n 读取）
const FALLBACK_OUTLINE = ['背景与概述', '关键实体与关系', '群体舆论演化', '风险与机会', '未来走向预测']

// 将已完成章节拼装为实时预览的 Markdown（逐章展示， 的分章节输出）
function assembleLive(outline, sections) {
  if (!sections || !sections.length) return ''
  const sorted = [...sections].sort((a, b) => (a.index ?? 0) - (b.index ?? 0))
  let out = ''
  if (outline?.title) out += `# ${outline.title}\n\n`
  if (outline?.summary) out += `> ${outline.summary}\n\n---\n\n`
  for (const s of sorted) out += `## ${s.title}\n\n${s.content}\n\n`
  return out
}

/**
 * ReportView —— 流程页 Step 4（报告生成）
 * 进入后自动触发报告生成，左侧报告正文，右侧工具调用结果，底部控制台。
 */
export default function ReportView() {
  // 路由参数携带模拟 ID（Step3 跳转而来）
  const { reportId: simulationId } = useParams()
  const { t } = useTranslation()
  const navigate = useNavigate()

  // 报告章节骨架（优先使用当前语言的本地化大纲）
  const outline = t('process.defaultOutline', { returnObjects: true })
  const OUTLINE = Array.isArray(outline) ? outline : FALLBACK_OUTLINE

  const [content, setContent] = useState('')
  const [generating, setGenerating] = useState(false)
  const [reportId, setReportId] = useState(null)
  const [liveOutline, setLiveOutline] = useState(null)
  const [sim, setSim] = useState({})
  const [actions, setActions] = useState([])
  const [toolTrace, setToolTrace] = useState([])
  const [timeline, setTimeline] = useState([])
  const [logs, setLogs] = useState([])
  const startedRef = useRef(false)
  // 章节日志去重：仅当当前撰写章节变化时才输出日志
  const lastSectionRef = useRef('')
  // 报告进度轮询定时器：组件卸载时清理，避免离开页面后仍在后台轮询
  const pollTimerRef = useRef(null)

  const graphId = sim?.graph_id
  const { data: graphData, refresh } = useGraphData(graphId)
  const stats = {
    nodes: graphData?.nodes?.length || 0,
    edges: graphData?.edges?.length || 0,
  }

  const pushLog = (text, level) =>
    setLogs((l) => [...l.slice(-80), { time: new Date().toLocaleTimeString(), level, text }])

  // 获取模拟信息（graph_id / requirement）与动作日志（用于可视化）
  useEffect(() => {
    getSimulationStatus({ simulation_id: simulationId })
      .then((res) => setSim(res.data || {}))
      .catch(() => { })
    getActions({ simulation_id: simulationId })
      .then((res) => setActions(res.data?.actions || []))
      .catch(() => { })
  }, [simulationId])

  // 生成报告（可强制重生成）：抽为可复用函数，供首次自动触发与「重新生成」按钮调用
  const runGenerate = useCallback((force = false) => {
    // 清理上一次的轮询
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
    }
    // 重置展示状态
    setContent('')
    setTimeline([])
    setLiveOutline(null)
    setToolTrace([])
    lastSectionRef.current = ''
    setGenerating(true)
    pushLog(t('log.reportStarting'))
      ; (async () => {
        try {
          const res = await generateReport({ simulation_id: simulationId, force_regenerate: force })
          const rid = res.data?.report_id || res.data?.id
          setReportId(rid)
          pushLog(t('log.reportTaskStarted', { id: rid || '' }))
          const timer = setInterval(async () => {
            try {
              // 轮询完整报告对象：含大纲 / 已完成章节 / 状态 / 进度（实时逐章展示）
              const rep = await getReport(rid)
              const d = rep.data || {}
              // 拉取生成时间线（逐步结构化事件，实时回放）
              try {
                const lg = await getReportLog(rid)
                setTimeline(lg.data?.events || [])
              } catch (e) { /* 忽略 */ }
              const titles = d.outline?.section_titles
              if (Array.isArray(titles) && titles.length) setLiveOutline(titles)
              // 当前撰写章节变化时输出日志
              if (d.current_section && d.current_section !== lastSectionRef.current) {
                lastSectionRef.current = d.current_section
                pushLog(t('log.writingSection', { title: d.current_section }))
              }
              if (d.status === 'completed') {
                clearInterval(timer)
                setContent(d.content || d.markdown || '')
                setToolTrace(d.tool_trace || [])
                try {
                  const ac = await getActions({ simulation_id: simulationId })
                  setActions(ac.data?.actions || [])
                } catch (e) { /* 忽略 */ }
                setGenerating(false)
                pushLog(t('log.reportDone'))
              } else if (d.status === 'failed') {
                clearInterval(timer)
                setGenerating(false)
                pushLog(t('log.reportFailed'), 'ERROR')
              } else {
                // 生成中：拼装已完成章节，实时逐章展示
                const live = assembleLive(d.outline, d.sections)
                if (live) setContent(live)
              }
            } catch (e) {
              clearInterval(timer)
              setGenerating(false)
            }
          }, 3000)
          pollTimerRef.current = timer
        } catch (e) {
          setGenerating(false)
          pushLog(t('log.reportStartFailed'), 'ERROR')
        }
      })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [simulationId, t])

  // 首次自动生成（仅一次）
  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true
    runGenerate(false)
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current)
    }
  }, [runGenerate])

  // 手动重新生成（强制刷新，绕过幂等复用）
  const handleRegenerate = useCallback(() => {
    if (generating) return
    runGenerate(true)
  }, [generating, runGenerate])

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
      primary={<GraphPanel data={graphData} graphId={graphId} onRefresh={refresh} />}
      secondary={
        <Step4Report
          reportId={reportId}
          content={content}
          generating={generating}
          outline={liveOutline || OUTLINE}
          stats={stats}
          requirement={sim?.requirement}
          actions={actions}
          toolTrace={toolTrace}
          timeline={timeline}
          onInteract={reportId ? goInteract : undefined}
          onRegenerate={handleRegenerate}
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
