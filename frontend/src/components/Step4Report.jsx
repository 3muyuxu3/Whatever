import { useTranslation } from 'react-i18next'
import ReportContent from './ReportContent'

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
  onInteract,
}) {
  const { t } = useTranslation()
  const memories = extractMemories(content)
  const tags = keywords(requirement)

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
        {onInteract && content && (
          <button
            type="button"
            onClick={onInteract}
            className="mb-4 w-full rounded-xl bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-neutral-800"
          >
            {t('steps.step5')} →
          </button>
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
