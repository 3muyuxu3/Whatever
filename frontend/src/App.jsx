import { Outlet } from 'react-router-dom'

/**
 * App —— 根布局组件
 * 首页与各流程页均为自带导航的全屏页面，这里只渲染路由出口。
 */
export default function App() {
  return <Outlet />
}
