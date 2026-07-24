import { useTranslation } from 'react-i18next'
import { downloadReport } from '../api/report'
import { TOOLS, TOOL_META } from '../constants'
import ReportContent from './ReportContent'
import ReportCharts from './ReportCharts'

// 从报告内容提取普通段落，作为「检索到的记忆」列表
function extractMemories(content) {
  return (content || '')
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith('#') && !l.startsWith('>'))
    .slice(0, 8)
}

// 从预测需求拆出关键词标签
function keywords(requirement) {
  return (requirement || '')
    .split(/[\s,，。、；;]+/)
    .filter(Boolean)
    .slice(0, 10)
}

// 生成时间线：将结构化事件映射为可读文案与色点
function timelineLabel(t, ev) {
  const d = ev.details || {}
  switch (ev.action) {
    case 'report_start':
      return t('timeline.reportStart', { defaultValue: '开始生成报告' })
    case 'planning_complete':
      return t('timeline.planningComplete', {
        count: d.outline?.sections?.length ?? d.outline?.section_titles?.length ?? 0,
        defaultValue: '大纲规划完成',
      })
    case 'section_start':
      return t('timeline.sectionStart', { title: d.section_title || '', defaultValue: `撰写章节：${d.section_title || ''}` })
    case 'section_complete':
      return t('timeline.sectionComplete', { title: d.section_title || '', defaultValue: `完成章节：${d.section_title || ''}` })
    case 'tool_call':
      return t('timeline.toolCall', { tool: d.tool || '', hits: d.hits ?? 0, defaultValue: `检索 ${d.tool || ''}` })
    case 'report_complete':
      return t('timeline.reportComplete', { defaultValue: '报告生成完成' })
    case 'error':
      return t('timeline.error', { error: d.error || '', defaultValue: '生成失败' })
    default:
      return ev.action
  }
}

function timelineDot(ev) {
  switch (ev.action) {
    case 'tool_call':
      return (TOOL_META[ev.details?.tool] || {}).color || '#94a3b8'
    case 'section_complete':
    case 'report_complete':
      return '#059669'
    case 'planning_complete':
      return '#7c3aed'
    case 'section_start':
      return '#0ea5e9'
    case 'error':
      return '#dc2626'
    default:
      return '#94a3b8'
  }
}

// 报告生成时间线面板（逐步回放：规划 / 工具检索 / 章节完成 / 完成）
function Timeline({ t, events }) {
  return (
    <div className="mb-4 rounded-2xl border border-neutral-200 bg-white p-4 shadow-sm">
      <div className="mb-3 text-sm font-semibold text-neutral-700">
        {t('timeline.title', { defaultValue: '生成时间线' })}
      </div>
      <ol className="max-h-52 space-y-2 overflow-auto">
        {events.map((ev, i) => (
          <li key={i} className="flex items-start gap-2 text-xs">
            <span
              className="mt-1 inline-block h-2 w-2 shrink-0 rounded-full"
              style={{ background: timelineDot(ev) }}
            />
            <span className="min-w-0 flex-1 truncate text-neutral-700" title={timelineLabel(t, ev)}>
              {timelineLabel(t, ev)}
            </span>
            <span className="shrink-0 font-mono text-[10px] text-neutral-400">
              {Number(ev.elapsed_seconds || 0).toFixed(1)}s
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}

/**
 * Step4Report —— 步骤4 工作台：报告（左） + 工具调用结果（右）
 */
export default function Step4Report({
  reportId,
  content,
  generating = false,
  outline = [],
  stats = {},
  requirement = '',
  actions = [],
  toolTrace = [],
  timeline = [],
  onInteract,
  onRegenerate,
}) {
  const { t } = useTranslation()
  const memories = extractMemories(content)
  const tags = keywords(requirement)

  const handleDownload = async () => {
    if (!reportId) return
    try {
      const res = await downloadReport(reportId)
      const url = URL.createObjectURL(new Blob([res.data], { type: 'text/markdown' }))
      const a = document.createElement('a')
      a.href = url
      a.download = `report-${reportId}.md`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch {
      /* 忽略下载错误 */
    }
  }

  return (
    <div className="flex h-full">
      {/* 左：报告正文 */}
      <div className="w-1/2 overflow-auto border-r border-neutral-200 bg-white">
        <ReportContent
          reportId={reportId}
          content={content}
          generating={generating}
          outline={outline}
        />
      </div>

      {/* 右：工具调用结果（Panorama Search 风格） */}
      <div className="w-1/2 overflow-auto p-6">
        {/* 工具栏：下载 + 进入深度互动 */}
        <div className="mb-4 flex gap-2">
          <button
            type="button"
            onClick={handleDownload}
            disabled={!content}
            className="flex-1 rounded-xl border border-neutral-200 bg-white px-5 py-2.5 text-sm font-medium text-neutral-700 transition hover:bg-neutral-50 disabled:opacity-40"
          >
            ↓ {t('process.downloadReport')}
          </button>
          {onRegenerate && !generating && content && (
            <button
              type="button"
              onClick={onRegenerate}
              className="flex-1 rounded-xl border border-neutral-200 bg-white px-5 py-2.5 text-sm font-medium text-neutral-700 transition hover:bg-neutral-50"
            >
              ↻ {t('process.regenerateReport', { defaultValue: '重新生成' })}
            </button>
          )}
          {onInteract && content && (
            <button
              type="button"
              onClick={onInteract}
              className="flex-1 rounded-xl bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-neutral-800"
            >
              {t('steps.step5')} →
            </button>
          )}
        </div>

        {/* 生成时间线（逐步回放：规划 / 工具检索 / 章节完成） */}
        {timeline.length > 0 && <Timeline t={t} events={timeline} />}

        {/* 生成中：检索工具调用活动 */}
        {generating && (
          <div className="mb-4 rounded-2xl border border-neutral-200 bg-white p-4 shadow-sm">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-neutral-700">
              <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-violet-400 border-t-transparent" />
              {t('process.toolActivity')}
            </div>
            <div className="grid grid-cols-2 gap-2">
              {TOOLS.map((tool) => (
                <div
                  key={tool.key}
                  className="flex items-center gap-2 rounded-lg border border-neutral-100 bg-neutral-50 px-3 py-2 text-xs text-neutral-600"
                >
                  <img src={tool.icon} alt="" className="h-4 w-4" loading="lazy" />
                  <span className="truncate">{t(`process.${tool.key}`)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 数据可视化（由模拟动作日志派生） */}
        {!generating && (
          <div className="mb-4">
            <div className="mb-2 text-sm font-semibold text-neutral-700">{t('process.dataViz')}</div>
            <ReportCharts actions={actions} />
          </div>
        )}

        {/* 真实 ReACT 工具调用轨迹 */}
        {!generating && toolTrace.length > 0 && (
          <div className="mb-4 rounded-2xl border border-neutral-200 bg-white p-4 shadow-sm">
            <div className="mb-3 text-sm font-semibold text-neutral-700">{t('process.toolTrace')}</div>
            <div className="space-y-2">
              {toolTrace.map((tc, i) => {
                const meta = TOOL_META[tc.tool] || { color: '#94a3b8' }
                return (
                  <div key={i} className="flex items-start gap-2 rounded-lg border border-neutral-100 bg-neutral-50 px-3 py-2 text-xs">
                    <span className="mt-1 inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: meta.color }} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium text-neutral-800">
                          {meta.key ? t(`process.${meta.key}`) : tc.tool}
                        </span>
                        {typeof tc.hits === 'number' && (
                          <span className="shrink-0 rounded-full bg-white px-2 py-0.5 text-[10px] text-neutral-500">
                            {tc.hits} hits
                          </span>
                        )}
                      </div>
                      {tc.query && (
                        <div className="truncate text-neutral-500" title={tc.query}>{tc.query}</div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        <div className="rounded-2xl border border-sky-200 bg-sky-50/60 p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-bold text-sky-900">Panorama Search</h3>
            <div className="text-xs text-neutral-500">
              <b className="text-neutral-800">{stats.nodes || 0}</b> Nodes /{' '}
              <b className="text-neutral-800">{stats.edges || 0}</b> Edges
            </div>
          </div>
          {tags.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-sm text-sky-700">
              {tags.map((k, i) => (
                <span key={i}>{k}</span>
              ))}
            </div>
          )}
          <div className="mt-4 flex gap-2 text-xs">
            <span className="rounded-md border border-sky-300 bg-white px-3 py-1.5 font-medium text-sky-700">
              {t('process.validMemory')} ({memories.length})
            </span>
            <span className="rounded-md px-3 py-1.5 text-neutral-500">
              {t('process.historyMemory')}
            </span>
            <span className="rounded-md px-3 py-1.5 text-neutral-500">
              {t('process.involvedEntities')} ({stats.nodes || 0})
            </span>
          </div>
        </div>

        {/* 记忆列表 */}
        <div className="mt-4 space-y-3">
          <div className="text-sm font-semibold text-neutral-700">{t('process.validMemory')}</div>
          {memories.length === 0 && <p className="text-sm text-neutral-400">…</p>}
          {memories.map((m, i) => (
            <div
              key={i}
              className="flex gap-3 rounded-xl border border-neutral-200 bg-white p-4 text-sm leading-relaxed text-neutral-700 shadow-sm"
            >
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-neutral-100 text-xs text-neutral-500">
                {i + 1}
              </span>
              <span>{m}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
