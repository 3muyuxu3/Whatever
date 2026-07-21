import { createBrowserRouter } from 'react-router-dom'
import App from '../App'
import Home from '../views/Home'
import MainView from '../views/MainView'
import SimulationView from '../views/SimulationView'
import SimulationRunView from '../views/SimulationRunView'
import ReportView from '../views/ReportView'
import InteractionView from '../views/InteractionView'
import NotFound from '../views/NotFound'

/**
 * 应用路由配置（createBrowserRouter）
 * 对应 AI.md 第六章的路由与页面阶段映射。
 */
const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    errorElement: <NotFound />,
    children: [
      { index: true, element: <Home /> }, // 首页
      { path: 'process/:projectId', element: <MainView /> }, // Step 1-2
      { path: 'simulation/:simulationId', element: <SimulationView /> }, // Step 2 详情
      { path: 'simulation/:simulationId/start', element: <SimulationRunView /> }, // Step 3
      { path: 'report/:reportId', element: <ReportView /> }, // Step 4
      { path: 'interaction/:reportId', element: <InteractionView /> }, // Step 5
      { path: '*', element: <NotFound /> },
    ],
  },
])

export default router
