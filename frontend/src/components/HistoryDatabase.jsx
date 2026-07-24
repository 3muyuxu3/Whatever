import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { listProjects, deleteProject } from '../api/graph'

/**
 * HistoryDatabase —— 历史项目卡片列表
 *
 * 从后端拉取历史项目并以卡片形式展示；后端不可用时优雅降级为空状态。
 */
export default function HistoryDatabase() {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const [projects, setProjects] = useState([])
    const [loading, setLoading] = useState(true)
    const [err, setErr] = useState('')

    const load = async () => {
        setLoading(true)
        try {
            const res = await listProjects()
            // 兼容 { projects: [...] } 或直接返回数组两种结构
            setProjects(res.data?.projects || res.data || [])
        } catch (e) {
            // 后端不可用时降级为空列表
            setProjects([])
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        load()
    }, [])

    const handleDelete = async (id, e) => {
        e.stopPropagation()
        // 删除前二次确认，避免误触丢失项目
        if (!window.confirm(t('history.confirmDelete', { defaultValue: '确定删除该项目？此操作不可撤销。' }))) return
        setErr('')
        try {
            await deleteProject(id)
            load()
        } catch (e2) {
            // 失败时给出反馈，而非静默吞没
            setErr(t('history.deleteFailed', { defaultValue: '删除失败，请重试。' }))
        }
    }

    if (loading) {
        return <p className="text-gray-400">{t('common.loading')}</p>
    }

    if (!projects.length) {
        return (
            <div className="liquid-glass rounded-xl px-6 py-10 text-center text-gray-400">
                {t('history.empty')}
            </div>
        )
    }

    return (
        <>
            {err && <p className="mb-3 text-sm text-red-400">{err}</p>}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {projects.map((p) => (
                    <div
                        key={p.id}
                        onClick={() => navigate(`/process/${p.id}`)}
                        className="liquid-glass group cursor-pointer rounded-xl p-5 transition hover:-translate-y-1"
                    >
                        <h3 className="mb-2 truncate text-lg font-medium text-white">
                            {p.name || p.id}
                        </h3>
                        <p className="mb-4 line-clamp-2 text-sm text-gray-400">
                            {p.requirement || p.description || ''}
                        </p>
                        <div className="flex items-center justify-between text-xs text-gray-500">
                            <span>{p.status || ''}</span>
                            <button
                                type="button"
                                onClick={(e) => handleDelete(p.id, e)}
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
