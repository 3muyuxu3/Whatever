import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { buildGraph, getBuildStatus } from '../api/graph'
import { useGraphData } from '../hooks/useGraphData'
import GraphPanel from './GraphPanel'

/**
 * Step1GraphBuild —— 步骤1：知识图谱构建
 * 触发后端异步构建 Zep 图谱，轮询进度，完成后展示力导向图谱。
 */
export default function Step1GraphBuild({ project }) {
    const { t } = useTranslation()
    const graphId = project?.graph_id || project?.id
    const [status, setStatus] = useState(project?.status || 'idle')
    const [progress, setProgress] = useState(0)
    const { data, loading, refresh } = useGraphData(graphId)

    const handleBuild = async () => {
        try {
            setStatus('building')
            await buildGraph({ project_id: project?.id })
            // 轮询构建进度
            const timer = setInterval(async () => {
                try {
                    const res = await getBuildStatus({ project_id: project?.id })
                    setProgress(res.data?.progress || 0)
                    if (res.data?.status === 'completed') {
                        clearInterval(timer)
                        setStatus('completed')
                        refresh()
                    }
                } catch (e) {
                    clearInterval(timer)
                    setStatus('error')
                }
            }, 2000)
        } catch (e) {
            setStatus('error')
        }
    }

    return (
        <div>
            <div className="mb-4 flex items-center justify-between">
                <h2 className="text-xl font-medium">{t('steps.step1')}</h2>
                <button
                    type="button"
                    onClick={handleBuild}
                    disabled={status === 'building'}
                    className="rounded-lg bg-white px-5 py-2 text-sm font-medium text-black transition hover:bg-gray-100 disabled:opacity-50"
                >
                    {status === 'building' ? `${progress}%` : t('steps.step1')}
                </button>
            </div>
            <GraphPanel data={data} loading={loading} statusText={t(`steps.step1`)} />
        </div>
    )
}
