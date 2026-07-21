import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * usePolling —— 异步任务轮询 Hook
 *
 * 用于本体生成、图谱构建、环境准备、报告生成等异步任务的状态轮询。
 *
 * @param {Function} fetcher   返回 Promise 的轮询函数（通常是查询任务状态的 API 调用）
 * @param {Object}   options
 * @param {number}   options.interval  轮询间隔（毫秒，默认 2000）
 * @param {boolean}  options.enabled   是否在挂载后立即开始轮询
 * @param {Function} options.isDone    (data) => boolean，返回 true 时停止轮询
 */
export function usePolling(
    fetcher,
    { interval = 2000, enabled = false, isDone } = {}
) {
    const [data, setData] = useState(null)
    const [error, setError] = useState(null)
    const [polling, setPolling] = useState(enabled)
    const timerRef = useRef(null)

    // 始终保存最新的 fetcher，避免闭包捕获旧值
    const savedFetcher = useRef(fetcher)
    savedFetcher.current = fetcher

    const stop = useCallback(() => {
        setPolling(false)
        if (timerRef.current) {
            clearTimeout(timerRef.current)
            timerRef.current = null
        }
    }, [])

    const start = useCallback(() => {
        setError(null)
        setPolling(true)
    }, [])

    useEffect(() => {
        if (!polling) return
        let cancelled = false

        const tick = async () => {
            try {
                const result = await savedFetcher.current()
                if (cancelled) return
                setData(result)
                if (isDone && isDone(result)) {
                    stop()
                    return
                }
            } catch (e) {
                if (cancelled) return
                setError(e)
            }
            if (!cancelled) {
                timerRef.current = setTimeout(tick, interval)
            }
        }

        tick()
        return () => {
            cancelled = true
            if (timerRef.current) clearTimeout(timerRef.current)
        }
    }, [polling, interval, isDone, stop])

    return { data, error, polling, start, stop }
}

export default usePolling
