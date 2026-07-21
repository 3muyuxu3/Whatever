import api from './index'

/**
 * 报告相关 API（对应后端 /api/report 蓝图）
 */

// 异步生成模拟分析报告
export const generateReport = (payload) => api.post('/report/generate', payload)

// 查询报告生成进度
export const getReportStatus = (payload) =>
    api.post('/report/generate/status', payload)

// 获取 / 删除报告
export const getReport = (id) => api.get(`/report/${id}`)
export const deleteReport = (id) => api.delete(`/report/${id}`)

// 按模拟 ID 获取报告
export const getReportBySimulation = (simId) =>
    api.get(`/report/by-simulation/${simId}`)

// 列出所有报告
export const listReports = () => api.get('/report/list')

// 下载 Markdown 报告（二进制流）
export const downloadReport = (id) =>
    api.get(`/report/${id}/download`, { responseType: 'blob' })

// 与 Report Agent 对话（深度互动）
export const chatWithReport = (payload) => api.post('/report/chat', payload)
