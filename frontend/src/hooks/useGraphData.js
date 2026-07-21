import { useCallback, useEffect, useRef, useState } from 'react'
import { getGraphData } from '../api/graph'

/**
 * useGraphData —— 获取图谱数据并可选自动刷新
 *
 * 模拟运行期间，GraphPanel 需要每 30 秒自动刷新图谱数据以展示实时演化。
 *
 * @param {string}  graphId              图谱 ID
 * @param {Object}  options
 * @param {boolean} options.autoRefresh    是否开启自动刷新
 * @param {number}  options.refreshInterval 自动刷新间隔（毫秒，默认 30000）
 */
export function useGraphData(
    graphId,
    { autoRefresh = false, refreshInterval = 30000 } = {}
) {
    const [data, setData] = useState(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)
    const timerRef = useRef(null)

    const refresh = useCallback(async () => {
        if (!graphId) return
        setLoading(true)
        try {
            const res = await getGraphData(graphId)
            setData(res.data)
            setError(null)
        } catch (e) {
            setError(e)
        } finally {
            setLoading(false)
        }
    }, [graphId])

    // 初次加载
    useEffect(() => {
        refresh()
    }, [refresh])

    // 定时自动刷新
    useEffect(() => {
        if (!autoRefresh || !graphId) return
        timerRef.current = setInterval(refresh, refreshInterval)
        return () => clearInterval(timerRef.current)
    }, [autoRefresh, graphId, refreshInterval, refresh])

    return { data, loading, error, refresh }
}

export default useGraphData
