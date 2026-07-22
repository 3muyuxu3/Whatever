import axios from 'axios'
import i18next from 'i18next'

/**
 * 全局 Axios 实例
 * - baseURL: /api（开发环境由 Vite 代理到后端 localhost:5001）
 * - timeout: 5 分钟（模拟/报告等操作耗时较长）
 * - 请求拦截器：注入当前语言到 Accept-Language 头
 * - 响应拦截器：对网络错误 / 5xx 进行指数退避重试（最多 3 次）
 */
const api = axios.create({
    baseURL: '/api',
    timeout: 5 * 60 * 1000, // 5 分钟
})

// 请求拦截器：根据 i18next 当前语言注入 Accept-Language
api.interceptors.request.use((config) => {
    config.headers = config.headers || {}
    config.headers['Accept-Language'] = i18next.language || 'zh'
    return config
})

// 最大重试次数
const MAX_RETRIES = 3

// 响应拦截器：失败时按指数退避自动重试
api.interceptors.response.use(
    (response) => response,
    async (error) => {
        const config = error.config
        if (!config) return Promise.reject(error)

        config.__retryCount = config.__retryCount || 0

        // 仅对「无响应（网络错误）」或「5xx 服务端错误」重试
        const status = error.response?.status
        const retriable = !error.response || (status >= 500 && status < 600)

        if (config.__retryCount >= MAX_RETRIES || !retriable) {
            return Promise.reject(error)
        }

        config.__retryCount += 1
        // 指数退避：1s, 2s, 4s（上限 8s）
        const delay = Math.min(1000 * 2 ** (config.__retryCount - 1), 8000)
        await new Promise((resolve) => setTimeout(resolve, delay))
        return api(config)
    }
)

export default api

/**
 * streamPost —— 以 SSE 方式消费后端流式接口（fetch + ReadableStream）
 *
 * 后端每条消息形如：`data: {"delta":"..."}\n\n`，结束为 `data: {"done":true}\n\n`。
 * axios 不便处理浏览器流式响应，这里用原生 fetch。
 *
 * @param {string}   path     相对 /api 的路径（如 '/simulation/interview/stream'）
 * @param {Object}   body     请求体（JSON）
 * @param {Object}   options
 * @param {Function} options.onToken (delta, full) => void，每个增量回调
 * @param {AbortSignal} options.signal 取消信号
 * @returns {Promise<string>} 完整文本
 */
export async function streamPost(path, body, { onToken, signal } = {}) {
    const res = await fetch(`/api${path}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept-Language': i18next.language || 'zh',
        },
        body: JSON.stringify(body || {}),
        signal,
    })
    if (!res.ok || !res.body) {
        throw new Error(`stream request failed: ${res.status}`)
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    let full = ''
    // eslint-disable-next-line no-constant-condition
    while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const parts = buf.split('\n\n')
        buf = parts.pop() || '' // 末尾可能是不完整的一段，保留
        for (const part of parts) {
            const line = part.trim()
            if (!line.startsWith('data:')) continue
            const payload = line.slice(5).trim()
            if (!payload) continue
            try {
                const obj = JSON.parse(payload)
                if (obj.delta) {
                    full += obj.delta
                    if (onToken) onToken(obj.delta, full)
                }
                if (obj.done) return full
            } catch {
                /* 忽略解析失败的分片 */
            }
        }
    }
    return full
}
