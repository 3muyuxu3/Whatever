import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { listReports, deleteReport } from '../api/report'

// 从报告 Markdown 内容提取一级标题作为卡片标题
function reportTitle(content) {
    const line = (content || '').split('\n').find((l) => l.trim().startsWith('# '))
    return line ? line.replace(/^#\s*/, '').trim() : ''
}

/**
 * ReportHistory —— 历史预测报告卡片列表
 *
 * 从后端拉取全部报告并以卡片展示；点击卡片进入深度互动页（可查看报告 + 继续对话）。
 * 后端不可用时优雅降级为空状态。
 */
export default function ReportHistory() {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const [reports, setReports] = useState([])
    const [loading, setLoading] = useState(true)
    const [err, setErr] = useState('')

    const load = async () => {
        setLoading(true)
        try {
            const res = await listReports()
            setReports(res.data?.reports || res.data || [])
        } catch (e) {
            setReports([])
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        load()
    }, [])

    const handleDelete = async (id, e) => {
        e.stopPropagation()
        // 删除前二次确认，避免误触丢失报告
        if (!window.confirm(t('reports.confirmDelete', { defaultValue: '确定删除该报告？此操作不可撤销。' }))) return
        setErr('')
        try {
            await deleteReport(id)
            load()
        } catch (e2) {
            // 失败时给出反馈，而非静默吞没
            setErr(t('reports.deleteFailed', { defaultValue: '删除失败，请重试。' }))
        }
    }

    if (loading) {
        return <p className="text-gray-400">{t('common.loading')}</p>
    }

    if (!reports.length) {
        return (
            <div className="liquid-glass rounded-xl px-6 py-10 text-center text-gray-400">
                {t('reports.empty')}
            </div>
        )
    }

    return (
        <>
            {err && <p className="mb-3 text-sm text-red-400">{err}</p>}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {reports.map((r) => (
                    <div
                        key={r.id}
                        onClick={() => navigate(`/interaction/${r.id}`)}
                        className="liquid-glass group cursor-pointer rounded-xl p-5 transition hover:-translate-y-1"
                    >
                        <div className="mb-2 flex items-center justify-between">
                            <span className="rounded bg-white/10 px-2 py-0.5 text-[10px] font-semibold tracking-widest text-white">
                                {t('process.predictionReport')}
                            </span>
                            <span className="text-xs text-gray-500">{r.status || ''}</span>
                        </div>
                        <h3 className="mb-3 line-clamp-2 text-base font-medium text-white">
                            {reportTitle(r.content) || r.id}
                        </h3>
                        <div className="flex items-center justify-between text-xs text-gray-500">
                            <span>
                                {r.created_at ? new Date(r.created_at * 1000).toLocaleString() : ''}
                            </span>
                            <button
                                type="button"
                                onClick={(e) => handleDelete(r.id, e)}
                                className="text-gray-400 opacity-0 transition hover:text-white group-hover:opacity-100"
                            >
                                {t('history.delete')}
                            </button>
                        </div>
                    </div>
                ))}
            </div>
        </>
    )
}
