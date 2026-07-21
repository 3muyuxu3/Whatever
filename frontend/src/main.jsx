import { StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { I18nextProvider } from 'react-i18next'
import i18n from './i18n'
import router from './router'
import { UploadProvider } from './store/UploadContext'
import './index.css'

// 应用入口：挂载 i18n、全局上传状态与路由
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <I18nextProvider i18n={i18n}>
      <UploadProvider>
        {/* Suspense 兜底 i18n 资源异步加载 */}
        <Suspense fallback={null}>
          <RouterProvider router={router} />
        </Suspense>
      </UploadProvider>
    </I18nextProvider>
  </StrictMode>
)
