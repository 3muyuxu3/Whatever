import { Outlet, useLocation, Link } from 'react-router-dom'
import LanguageSwitcher from './components/LanguageSwitcher'

/**
 * App —— 根布局组件
 * 首页（/）为全屏视频页，自带导航栏；其余页面渲染统一的顶部栏 + <Outlet />。
 */
export default function App() {
  const { pathname } = useLocation()
  const isHome = pathname === '/'

  return (
    <div className="min-h-screen bg-black text-white">
      {!isHome && (
        <header className="flex items-center justify-between border-b border-white/10 px-6 py-4 md:px-12">
          <Link to="/" className="text-xl font-semibold tracking-tight">
            SimulMirror
          </Link>
          <LanguageSwitcher />
        </header>
      )}
      <Outlet />
    </div>
  )
}
