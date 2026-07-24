import { Suspense } from 'react'
import { Outlet } from 'react-router-dom'
import ErrorBoundary from './components/ErrorBoundary'

/**
 * App —— 根布局组件
 * 首页与各流程页均为自带导航的全屏页面，这里渲染路由出口。
 * 外层包裹 ErrorBoundary（隔离渲染异常）与 Suspense（承接路由级懒加载）。
 */
export default function App() {
  return (
    <ErrorBoundary>
      <Suspense
        fallback={
          <div className="flex h-screen items-center justify-center bg-black text-neutral-500">
            …
          </div>
        }
      >
        <Outlet />
      </Suspense>
    </ErrorBoundary>
  )
}
