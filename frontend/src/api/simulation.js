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

// 停止正在运行的模拟
export const stopSimulation = (payload) => api.post('/simulation/stop', payload)

// 上帝视角：向模拟世界动态注入新事件 / 变量
export const injectVariable = (payload) => api.post('/simulation/inject', payload)

// 获取模拟详情（配置 + 人设 + 状态）
export const getSimulationDetail = (simId) =>
    api.get(`/simulation/detail/${simId}`)

// 编辑模拟配置（轮次 / 平台开关）
export const updateSimConfig = (payload) => api.post('/simulation/config', payload)

// 列出可对话 / 可调查的 Agent（基于已生成人设）
export const listAgents = (simId) => api.get(`/simulation/agents/${simId}`)

// 采访单个 Agent
export const interviewAgent = (payload) =>
    api.post('/simulation/interview', payload)

// 批量采访 Agent（问卷调查）
export const interviewBatch = (payload) =>
    api.post('/simulation/interview/batch', payload)
