import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { chatWithReport } from '../api/report'

/**
 * Step5Interaction —— 步骤5：深度互动
 * 基于已生成报告的上下文，与 Report Agent 连续对话（可继续调用工具回答追问）。
 */
export default function Step5Interaction({ reportId }) {
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
      const reply = res.data?.reply || res.data?.message || ''
      setMessages((m) => [...m, { role: 'assistant', content: reply }])
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: t('common.error') },
      ])
    } finally {
      setSending(false)
    }
  }

  return (
    <div>
      <h2 className="mb-4 text-xl font-medium">{t('steps.step5')}</h2>

      {/* 对话记录 */}
      <div className="liquid-glass mb-4 flex min-h-[360px] flex-col gap-3 rounded-xl p-6">
        {messages.length === 0 && (
          <p className="text-gray-500">SimulMirror Report Agent</p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`max-w-[80%] rounded-xl px-4 py-2 text-sm ${
              m.role === 'user'
                ? 'self-end bg-white text-black'
                : 'self-start bg-white/10 text-gray-200'
            }`}
          >
            {m.content}
          </div>
        ))}
      </div>

      {/* 输入框 */}
      <div className="flex gap-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          placeholder="..."
          className="flex-1 rounded-lg border border-white/15 bg-black/40 px-4 py-3 text-white outline-none focus:border-white/40"
        />
        <button
          type="button"
          onClick={send}
          disabled={sending}
          className="rounded-lg bg-white px-6 py-3 font-medium text-black transition hover:bg-gray-100 disabled:opacity-50"
        >
          {t('common.next')}
        </button>
      </div>
    </div>
  )
}
