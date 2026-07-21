import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import {
  generateReport,
  getReportStatus,
  getReport,
  downloadReport,
} from '../api/report'

/**
 * Step4Report —— 步骤4：报告生成
 * 触发 ReACT 报告 Agent 异步生成报告，轮询进度，完成后展示 Markdown 内容。
 */
export default function Step4Report({ simulationId }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [status, setStatus] = useState('idle')
  const [progress, setProgress] = useState(0)
  const [content, setContent] = useState('')
  const [reportId, setReportId] = useState(null)

  const handleGenerate = async () => {
    setStatus('generating')
    try {
      const res = await generateReport({ simulation_id: simulationId })
      const rid = res.data?.report_id || res.data?.id
      setReportId(rid)
      const timer = setInterval(async () => {
        try {
          const st = await getReportStatus({ report_id: rid })
          setProgress(st.data?.progress || 0)
          if (st.data?.status === 'completed') {
            clearInterval(timer)
            const rep = await getReport(rid)
            setContent(rep.data?.content || rep.data?.markdown || '')
            setStatus('completed')
          }
        } catch (e) {
          clearInterval(timer)
          setStatus('error')
        }
      }, 3000)
    } catch (e) {
      setStatus('error')
    }
  }

  // 下载 Markdown 报告
  const handleDownload = async () => {
    if (!reportId) return
    try {
      const res = await downloadReport(reportId)
      const url = URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `report-${reportId}.md`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      /* 忽略 */
    }
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-xl font-medium">{t('steps.step4')}</h2>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={handleGenerate}
            disabled={status === 'generating'}
            className="rounded-lg bg-white px-5 py-2 text-sm font-medium text-black transition hover:bg-gray-100 disabled:opacity-50"
          >
            {status === 'generating' ? `${progress}%` : t('steps.step4')}
          </button>
          {status === 'completed' && (
            <>
              <button
                type="button"
                onClick={handleDownload}
                className="liquid-glass rounded-lg px-5 py-2 text-sm text-white"
              >
                Markdown
              </button>
              <button
                type="button"
                onClick={() => navigate(`/interaction/${reportId}`)}
                className="liquid-glass rounded-lg px-5 py-2 text-sm text-white"
              >
                {t('steps.step5')}
              </button>
            </>
          )}
        </div>
      </div>

      {/* 报告内容（Markdown 源文本，按空白排版展示） */}
      <div className="liquid-glass min-h-[320px] rounded-xl p-6">
        {content ? (
          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-gray-200">
            {content}
          </pre>
        ) : (
          <p className="text-gray-500">{t('common.loading')}</p>
        )}
      </div>
    </div>
  )
}
