import { Navigate, useParams } from 'react-router-dom'

/**
 * SimulationView —— 环境搭建详情（Step 2）
 * 新流程中环境准备已并入 Step 1-2 工作台，这里直接进入模拟运行页。
 */
export default function SimulationView() {
  const { simulationId } = useParams()
  return <Navigate to={`/simulation/${simulationId}/start`} replace />
}
