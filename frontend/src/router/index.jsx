import { lazy } from 'react'
import { createBrowserRouter } from 'react-router-dom'
import App from '../App'
import NotFound from '../views/NotFound'

// 路由级代码分割：各页面按需懒加载，减小首屏 bundle 体积。
// App 作为布局壳、NotFound 作为错误/兜底页保持同步导入，确保始终可用。
const Home = lazy(() => import('../views/Home'))
const MainView = lazy(() => import('../views/MainView'))
const SimulationView = lazy(() => import('../views/SimulationView'))
const SimulationRunView = lazy(() => import('../views/SimulationRunView'))
const ReportView = lazy(() => import('../views/ReportView'))
const InteractionView = lazy(() => import('../views/InteractionView'))

/**
 * 应用路由配置（createBrowserRouter）
 * 对应各阶段页面：首页 / 图谱构建 / 环境搭建 / 模拟运行 / 报告 / 深度互动。
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
