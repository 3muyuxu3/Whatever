import api from './index'

/**
 * 图谱相关 API（对应后端 /api/graph 蓝图）
 */

// 上传文件 + 预测需求，由 LLM 生成本体定义（entity_types / edge_types）
export const generateOntology = (formData) =>
    api.post('/graph/ontology/generate', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
    })

// 异步构建 Zep 知识图谱
export const buildGraph = (payload) => api.post('/graph/build', payload)

// 查询图谱构建进度
export const getBuildStatus = (payload) => api.post('/graph/build/status', payload)

// 获取完整图谱数据（节点 + 边）
export const getGraphData = (graphId) => api.get(`/graph/data/${graphId}`)

// 项目管理
export const listProjects = () => api.get('/graph/project/list')
export const getProject = (id) => api.get(`/graph/project/${id}`)
export const deleteProject = (id) => api.delete(`/graph/project/${id}`)
export const resetProject = (id) => api.post(`/graph/project/${id}/reset`)
