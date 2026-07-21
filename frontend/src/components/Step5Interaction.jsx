import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { chatWithReport } from '../api/report'
import ReportContent from './ReportContent'

// 四种工具（icons8 图标）
const TOOLS = [
  { key: 'toolInsight', icon: 'https://img.icons8.com/ios/50/7c3aed/idea.png' },
  { key: 'toolPanorama', icon: 'https://img.icons8.com/ios/50/0ea5e9/globe--v1.png' },
  { key: 'toolQuick', icon: 'https://img.icons8.com/ios/50/f59e0b/flash-on.png' },
  { key: 'toolInterview', icon: 'https://img.icons8.com/ios/50/059669/conference-call.png' },
]

/**
 * Step5Interaction —— 步骤5 工作台：报告（左） + 交互工具与对话（右）
 */
export default function Step5Interaction({ reportId, content, outline = [], agentsCount = 0 }) {
  const { t } = useTranslation()
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)

  const send = async () => {
    const q = input.trim()
    if (!q || sending) return
    setMessages((m) => [...m, { role: 'user', content: q }])
    setInput('')
    setSending(true)
    try {
      const res = await chatWithReport({ report_id: reportId, message: q })
      setMessages((m) => [...m, { role: 'assistant', content: res.data?.reply || res.data?.message || '' }])
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', content: t('common.error') }])
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="flex h-full">
      {/* 左：报告正文 */}
      <div className="w-1/2 overflow-auto border-r border-neutral-200 bg-white">
        <ReportContent reportId={reportId} content={content} outline={outline} />
      </div>

      {/* 右：交互工具 + 对话 */}
      <div className="flex w-1/2 flex-col">
        {/* 交互模式 */}
        <div className="flex flex-wrap items-center gap-3 border-b border-neutral-200 p-5">
          <div className="mr-auto flex items-center gap-2">
            <span className="text-base font-semibold text-neutral-800">
              {t('process.interactionTools')}
            </span>
            <span className="text-xs text-neutral-400">
              {agentsCount} {t('process.agentsAvailable')}
            </span>
          </div>
          <button className="rounded-full bg-neutral-900 px-4 py-2 text-sm font-medium text-white">
            {t('process.chatReport')}
          </button>
          <button className="rounded-full border border-neutral-200 px-4 py-2 text-sm text-neutral-500">
            {t('process.chatAgent')}
          </button>
          <button className="rounded-full border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-600">
            {t('process.survey')}
          </button>
        </div>

        {/* Report Agent - Chat 说明 + 四工具 */}
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

        {/* 对话区 */}
        <div className="flex flex-1 flex-col gap-3 overflow-auto p-5">
          {messages.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center text-neutral-400">
              <img
                src="https://img.icons8.com/ios/50/d4d4d4/chat--v1.png"
                alt=""
                className="mb-3 h-10 w-10"
                loading="lazy"
              />
              <p className="text-sm">{t('process.emptyChat')}</p>
            </div>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm ${m.role === 'user'
                  ? 'self-end bg-neutral-900 text-white'
                  : 'self-start bg-neutral-100 text-neutral-800'
                }`}
            >
              {m.content}
            </div>
          ))}
        </div>

        {/* 输入 */}
        <div className="flex gap-3 border-t border-neutral-200 p-4">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send()}
            placeholder={t('process.inputPlaceholder')}
            className="flex-1 rounded-xl border border-neutral-200 px-4 py-3 text-sm text-neutral-800 outline-none transition focus:border-neutral-400"
          />
          <button
            type="button"
            onClick={send}
            disabled={sending}
            aria-label="Send"
            className="flex h-11 w-11 items-center justify-center rounded-xl bg-neutral-900 text-white transition hover:bg-neutral-800 disabled:opacity-40"
          >
            →
          </button>
        </div>
      </div>
    </div>
  )
}
