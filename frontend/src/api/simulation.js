import api from './index'

/**
 * 模拟相关 API（对应后端 /api/simulation 蓝图）
 */

// 获取图谱实体（已过滤）
export const getEntities = (graphId) => api.get(`/simulation/entities/${graphId}`)

// 获取单个实体详情
export const getEntity = (graphId, uuid) =>
    api.get(`/simulation/entities/${graphId}/${uuid}`)

// 创建新模拟
export const createSimulation = (payload) => api.post('/simulation/create', payload)

// 异步准备模拟环境（生成 Profile、模拟配置等）
export const prepareSimulation = (payload) =>
    api.post('/simulation/prepare', payload)

// 查询准备进度
export const getPrepareStatus = (payload) =>
    api.post('/simulation/prepare/status', payload)

// 启动模拟运行
export const startSimulation = (payload) => api.post('/simulation/start', payload)

// 获取模拟运行状态
export const getSimulationStatus = (payload) =>
    api.post('/simulation/status', payload)

// 获取动作历史（actions.jsonl 内容）
export const getActions = (payload) => api.post('/simulation/actions', payload)

// 采访单个 Agent
export const interviewAgent = (payload) =>
    api.post('/simulation/interview', payload)

// 批量采访 Agent（问卷调查）
export const interviewBatch = (payload) =>
    api.post('/simulation/interview/batch', payload)
