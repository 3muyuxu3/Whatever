import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { chatWithReport } from '../api/report'
import { interviewAgent, interviewBatch, listAgents } from '../api/simulation'
import ReportContent from './ReportContent'
import ReportCharts from './ReportCharts'

// 四种工具（icons8 图标）
const TOOLS = [
  { key: 'toolInsight', icon: 'https://img.icons8.com/ios/50/7c3aed/idea.png' },
  { key: 'toolPanorama', icon: 'https://img.icons8.com/ios/50/0ea5e9/globe--v1.png' },
  { key: 'toolQuick', icon: 'https://img.icons8.com/ios/50/f59e0b/flash-on.png' },
  { key: 'toolInterview', icon: 'https://img.icons8.com/ios/50/059669/conference-call.png' },
]

// 工具名 -> 展示元数据（用于真实 ReACT 调用轨迹）
const TOOL_META = {
  QuickSearch: { color: '#f59e0b', key: 'toolQuick' },
  PanoramaSearch: { color: '#0ea5e9', key: 'toolPanorama' },
  InsightForge: { color: '#7c3aed', key: 'toolInsight' },
  InterviewAgents: { color: '#059669', key: 'toolInterview' },
}

// 消息气泡
function Bubble({ role, children }) {
  return (
    <div
      className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm ${role === 'user'
        ? 'self-end bg-neutral-900 text-white'
        : 'self-start bg-neutral-100 text-neutral-800'
        }`}
    >
      {children}
    </div>
  )
}

// 头像圆点：按名字取首字母
function Avatar({ name, tone = 'bg-emerald-600' }) {
  const initial = (name || '?').trim().charAt(0).toUpperCase()
  return (
    <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white ${tone}`}>
      {initial}
    </span>
  )
}

/**
 * Step5Interaction —— 步骤5 深度互动工作台
 * 左：预测报告；右：三种互动模式
 *   1) 与 Report Agent 对话（调用 4 种检索工具）
 *   2) 与世界中任意个体对话（/simulation/interview）
 *   3) 向世界发送问卷调查（/simulation/interview/batch）
 */
export default function Step5Interaction({ reportId, simId, content, outline = [], actions = [], toolTrace = [] }) {
  const { t } = useTranslation()
  const [mode, setMode] = useState('overview') // overview | report | agent | survey
  const [agents, setAgents] = useState([])

  // —— Report Agent 对话 ——
  const [reportMsgs, setReportMsgs] = useState([])
  const [reportInput, setReportInput] = useState('')
  const [reportSending, setReportSending] = useState(false)

  // —— 与个体对话 ——
  const [activeAgent, setActiveAgent] = useState(null)
  const [threads, setThreads] = useState({}) // agentId -> messages[]
  const [agentInput, setAgentInput] = useState('')
  const [agentSending, setAgentSending] = useState(false)

  // —— 问卷调查 ——
  const [selected, setSelected] = useState(() => new Set())
  const [surveyQ, setSurveyQ] = useState('')
  const [surveyResults, setSurveyResults] = useState([])
  const [surveySending, setSurveySending] = useState(false)

  const reportEndRef = useRef(null)
  const agentEndRef = useRef(null)

  // 加载可对话的个体
  useEffect(() => {
    if (!simId) return
    listAgents(simId)
      .then((res) => setAgents(res.data?.agents || []))
      .catch(() => setAgents([]))
  }, [simId])

  // 自动滚动到底部
  useEffect(() => {
    reportEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [reportMsgs])
  useEffect(() => {
    agentEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [threads, activeAgent])

  const activeThread = activeAgent ? threads[activeAgent.id] || [] : []

  // —— 发送：Report Agent ——
  const sendReport = async () => {
    const q = reportInput.trim()
    if (!q || reportSending) return
    setReportMsgs((m) => [...m, { role: 'user', content: q }])
    setReportInput('')
    setReportSending(true)
    try {
      const res = await chatWithReport({ report_id: reportId, message: q })
      setReportMsgs((m) => [...m, { role: 'assistant', content: res.data?.reply || res.data?.message || '' }])
    } catch {
      setReportMsgs((m) => [...m, { role: 'assistant', content: t('common.error') }])
    } finally {
      setReportSending(false)
    }
  }

  // —— 发送：与个体对话 ——
  const sendAgent = async () => {
    const q = agentInput.trim()
    if (!q || !activeAgent || agentSending) return
    const aid = activeAgent.id
    setThreads((th) => ({ ...th, [aid]: [...(th[aid] || []), { role: 'user', content: q }] }))
    setAgentInput('')
    setAgentSending(true)
    try {
      const res = await interviewAgent({ simulation_id: simId, agent_id: aid, question: q })
      setThreads((th) => ({ ...th, [aid]: [...(th[aid] || []), { role: 'assistant', content: res.data?.answer || '' }] }))
    } catch {
      setThreads((th) => ({ ...th, [aid]: [...(th[aid] || []), { role: 'assistant', content: t('common.error') }] }))
    } finally {
      setAgentSending(false)
    }
  }

  // —— 问卷：选择 ——
  const toggleSel = (id) =>
    setSelected((s) => {
      const n = new Set(s)
      n.has(id) ? n.delete(id) : n.add(id)
      return n
    })
  const toggleAll = () =>
    setSelected((s) => (s.size === agents.length ? new Set() : new Set(agents.map((a) => a.id))))

  // —— 发送：问卷调查 ——
  const sendSurvey = async () => {
    const q = surveyQ.trim()
    if (!q || surveySending || agents.length === 0) return
    setSurveySending(true)
    setSurveyResults([])
    try {
      const ids = selected.size ? Array.from(selected) : agents.map((a) => a.id)
      const res = await interviewBatch({ simulation_id: simId, agent_ids: ids, question: q })
      setSurveyResults(res.data?.results || [])
    } catch {
      setSurveyResults([])
    } finally {
      setSurveySending(false)
    }
  }

  const MODES = useMemo(
    () => [
      { key: 'overview', label: t('process.overview') },
      { key: 'report', label: t('process.chatReport') },
      { key: 'agent', label: t('process.chatAgent') },
      { key: 'survey', label: t('process.survey') },
    ],
    [t],
  )

  return (
    <div className="flex h-full">
      {/* 左：报告正文 */}
      <div className="w-1/2 overflow-auto border-r border-neutral-200 bg-white">
        <ReportContent reportId={reportId} content={content} outline={outline} />
      </div>

      {/* 右：交互工作台 */}
      <div className="flex w-1/2 flex-col">
        {/* 模式切换 */}
        <div className="flex flex-wrap items-center gap-2 border-b border-neutral-200 p-4">
          <div className="mr-auto flex items-center gap-2">
            <span className="text-base font-semibold text-neutral-800">{t('process.interactionTools')}</span>
            <span className="text-xs text-neutral-400">
              {agents.length} {t('process.agentsAvailable')}
            </span>
          </div>
          {MODES.map((m) => (
            <button
              key={m.key}
              type="button"
              onClick={() => setMode(m.key)}
              className={`rounded-full px-4 py-2 text-sm font-medium transition ${mode === m.key
                ? 'bg-neutral-900 text-white'
                : 'border border-neutral-200 text-neutral-500 hover:bg-neutral-50'
                }`}
            >
              {m.label}
            </button>
          ))}
        </div>

        {/* ============ 模式零：数据总览 ============ */}
        {mode === 'overview' && (
          <div className="min-h-0 flex-1 space-y-4 overflow-auto p-5">
            <ReportCharts actions={actions} />
            {toolTrace.length > 0 && (
              <div className="rounded-2xl border border-neutral-200 bg-white p-4 shadow-sm">
                <div className="mb-3 text-sm font-semibold text-neutral-700">{t('process.toolTrace')}</div>
                <div className="space-y-2">
                  {toolTrace.map((tc, i) => {
                    const meta = TOOL_META[tc.tool] || { color: '#94a3b8' }
                    return (
                      <div key={i} className="flex items-start gap-2 rounded-lg border border-neutral-100 bg-neutral-50 px-3 py-2 text-xs">
                        <span className="mt-1 inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: meta.color }} />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-medium text-neutral-800">{meta.key ? t(`process.${meta.key}`) : tc.tool}</span>
                            {typeof tc.hits === 'number' && (
                              <span className="shrink-0 rounded-full bg-white px-2 py-0.5 text-[10px] text-neutral-500">{tc.hits} hits</span>
                            )}
                          </div>
                          {tc.query && <div className="truncate text-neutral-500" title={tc.query}>{tc.query}</div>}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ============ 模式一：Report Agent ============ */}
        {mode === 'report' && (
          <div className="flex min-h-0 flex-1 flex-col">
            <div className="border-b border-neutral-200 p-5">
              <div className="mb-1 flex items-center gap-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-neutral-900 text-xs font-bold text-white">
                  R
                </span>
                <span className="font-semibold text-neutral-800">{t('process.reportAgentChat')}</span>
              </div>
              <p className="mb-4 text-xs text-neutral-500">{t('process.reportAgentDesc')}</p>
              <div className="grid grid-cols-2 gap-3">
                {TOOLS.map((tool) => (
                  <div key={tool.key} className="rounded-xl border border-neutral-200 bg-white p-3">
                    <div className="mb-1 flex items-center gap-2">
                      <img src={tool.icon} alt="" className="h-4 w-4" loading="lazy" />
                      <span className="text-sm font-medium text-neutral-800">{t(`process.${tool.key}`)}</span>
                    </div>
                    <p className="text-xs leading-relaxed text-neutral-500">{t(`process.${tool.key}Desc`)}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-5">
              {reportMsgs.length === 0 && (
                <div className="flex h-full flex-col items-center justify-center text-neutral-400">
                  <img src="https://img.icons8.com/ios/50/d4d4d4/chat--v1.png" alt="" className="mb-3 h-10 w-10" loading="lazy" />
                  <p className="text-sm">{t('process.emptyChat')}</p>
                </div>
              )}
              {reportMsgs.map((m, i) => (
                <Bubble key={i} role={m.role}>{m.content}</Bubble>
              ))}
              {reportSending && <Bubble role="assistant">{t('process.thinking')}</Bubble>}
              <div ref={reportEndRef} />
            </div>

            <ChatInput
              value={reportInput}
              onChange={setReportInput}
              onSend={sendReport}
              disabled={reportSending}
              placeholder={t('process.inputPlaceholder')}
            />
          </div>
        )}

        {/* ============ 模式二：与个体对话 ============ */}
        {mode === 'agent' && (
          <div className="flex min-h-0 flex-1">
            {/* 个体列表 */}
            <div className="w-2/5 overflow-auto border-r border-neutral-200 p-3">
              {agents.length === 0 && (
                <p className="p-4 text-center text-sm text-neutral-400">{t('process.noAgents')}</p>
              )}
              {agents.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => setActiveAgent(a)}
                  className={`mb-2 flex w-full items-center gap-2 rounded-xl border p-2.5 text-left transition ${activeAgent?.id === a.id
                    ? 'border-neutral-900 bg-neutral-50'
                    : 'border-neutral-200 hover:bg-neutral-50'
                    }`}
                >
                  <Avatar name={a.name} />
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium text-neutral-800">{a.name}</span>
                    <span className="block truncate text-xs text-neutral-400">{a.occupation || a.mbti || '—'}</span>
                  </span>
                </button>
              ))}
            </div>

            {/* 对话区 */}
            <div className="flex min-h-0 w-3/5 flex-col">
              {!activeAgent ? (
                <div className="flex h-full flex-col items-center justify-center p-4 text-center text-neutral-400">
                  <img src="https://img.icons8.com/ios/50/d4d4d4/conference-call.png" alt="" className="mb-3 h-10 w-10" loading="lazy" />
                  <p className="text-sm">{t('process.agentChatEmpty')}</p>
                </div>
              ) : (
                <>
                  <div className="border-b border-neutral-200 p-4">
                    <div className="flex items-center gap-2">
                      <Avatar name={activeAgent.name} />
                      <div className="min-w-0">
                        <div className="truncate text-sm font-semibold text-neutral-800">{activeAgent.name}</div>
                        {activeAgent.bio && <div className="truncate text-xs text-neutral-400">{activeAgent.bio}</div>}
                      </div>
                    </div>
                  </div>
                  <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-4">
                    {activeThread.length === 0 && (
                      <p className="mt-8 text-center text-sm text-neutral-400">{t('process.agentChatHint')}</p>
                    )}
                    {activeThread.map((m, i) => (
                      <Bubble key={i} role={m.role}>{m.content}</Bubble>
                    ))}
                    {agentSending && <Bubble role="assistant">{t('process.thinking')}</Bubble>}
                    <div ref={agentEndRef} />
                  </div>
                  <ChatInput
                    value={agentInput}
                    onChange={setAgentInput}
                    onSend={sendAgent}
                    disabled={agentSending}
                    placeholder={t('process.askAgentPlaceholder')}
                  />
                </>
              )}
            </div>
          </div>
        )}

        {/* ============ 模式三：问卷调查 ============ */}
        {mode === 'survey' && (
          <div className="flex min-h-0 flex-1 flex-col">
            <div className="border-b border-neutral-200 p-4">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-semibold text-neutral-800">{t('process.surveyAudience')}</span>
                <button type="button" onClick={toggleAll} className="text-xs font-medium text-violet-600 hover:underline">
                  {selected.size === agents.length && agents.length > 0 ? t('process.clearAll') : t('process.selectAll')}
                </button>
              </div>
              <div className="grid max-h-32 grid-cols-2 gap-2 overflow-auto">
                {agents.length === 0 && <p className="col-span-2 text-sm text-neutral-400">{t('process.noAgents')}</p>}
                {agents.map((a) => (
                  <label
                    key={a.id}
                    className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm ${selected.has(a.id) ? 'border-violet-400 bg-violet-50' : 'border-neutral-200'
                      }`}
                  >
                    <input type="checkbox" checked={selected.has(a.id)} onChange={() => toggleSel(a.id)} className="accent-violet-600" />
                    <span className="truncate text-neutral-700">{a.name}</span>
                  </label>
                ))}
              </div>
              <div className="mt-3 flex gap-2">
                <input
                  value={surveyQ}
                  onChange={(e) => setSurveyQ(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && sendSurvey()}
                  placeholder={t('process.surveyPlaceholder')}
                  className="flex-1 rounded-xl border border-neutral-200 px-4 py-2.5 text-sm text-neutral-800 outline-none transition focus:border-neutral-400"
                />
                <button
                  type="button"
                  onClick={sendSurvey}
                  disabled={surveySending || !surveyQ.trim() || agents.length === 0}
                  className="rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-emerald-700 disabled:opacity-40"
                >
                  {surveySending ? t('process.sending') : t('process.sendSurvey')}
                </button>
              </div>
              <p className="mt-2 text-xs text-neutral-400">
                {t('process.surveyTargetCount', { count: selected.size || agents.length })}
              </p>
            </div>

            {/* 结果 */}
            <div className="flex-1 space-y-3 overflow-auto p-4">
              {surveyResults.length === 0 && !surveySending && (
                <div className="flex h-full items-center justify-center text-sm text-neutral-400">{t('process.surveyEmpty')}</div>
              )}
              {surveySending && (
                <div className="flex h-full items-center justify-center gap-2 text-sm text-neutral-400">
                  <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-neutral-300 border-t-transparent" />
                  {t('process.sending')}
                </div>
              )}
              {surveyResults.map((r, i) => (
                <div key={i} className="rounded-xl border border-neutral-200 bg-white p-4 shadow-sm">
                  <div className="mb-2 flex items-center gap-2">
                    <Avatar name={r.name} tone="bg-emerald-600" />
                    <span className="text-sm font-medium text-neutral-800">{r.name || r.agent_id}</span>
                  </div>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-neutral-700">{r.answer}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// 通用聊天输入条
function ChatInput({ value, onChange, onSend, disabled, placeholder }) {
  return (
    <div className="flex gap-3 border-t border-neutral-200 p-4">
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && onSend()}
        placeholder={placeholder}
        className="flex-1 rounded-xl border border-neutral-200 px-4 py-3 text-sm text-neutral-800 outline-none transition focus:border-neutral-400"
      />
      <button
        type="button"
        onClick={onSend}
        disabled={disabled}
        aria-label="Send"
        className="flex h-11 w-11 items-center justify-center rounded-xl bg-neutral-900 text-white transition hover:bg-neutral-800 disabled:opacity-40"
      >
        →
      </button>
    </div>
  )
}
