import { useCallback, useEffect, useRef, useState } from 'react'
import { getSimulationStatus } from '../api/simulation'

// 模拟的终止状态集合
const TERMINAL_STATES = ['completed', 'stopped', 'failed']

/**
 * useSimulationStatus —— 实时监控模拟运行状态
 *
 * @param {string}  simulationId       模拟 ID
 * @param {Object}  options
 * @param {number}  options.interval   轮询间隔（毫秒，默认 3000）
 * @param {boolean} options.enabled    是否启用监控
 */
export function useSimulationStatus(
    simulationId,
    { interval = 3000, enabled = true } = {}
) {
    const [status, setStatus] = useState(null)
    const [error, setError] = useState(null)
    const timerRef = useRef(null)

    const poll = useCallback(async () => {
        if (!simulationId) return
        try {
            const res = await getSimulationStatus({ simulation_id: simulationId })
            setStatus(res.data)
            setError(null)
            // 到达终止状态则停止轮询
            if (TERMINAL_STATES.includes(res.data?.status) && timerRef.current) {
                clearInterval(timerRef.current)
            }
        } catch (e) {
            setError(e)
        }
    }, [simulationId])

    useEffect(() => {
        if (!enabled || !simulationId) return
        poll()
        timerRef.current = setInterval(poll, interval)
        return () => clearInterval(timerRef.current)
    }, [enabled, simulationId, interval, poll])

    return { status, error, refresh: poll }
}

export default useSimulationStatus
