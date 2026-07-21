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
