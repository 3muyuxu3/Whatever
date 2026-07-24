import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// SimulMirror 前端 Vite 配置
// 开发服务器端口固定为 3001，并将 /api 请求代理到后端 Flask 服务（5001）
export default defineConfig({
  plugins: [react()],
  // 生产构建分包：将体积较大的 d3 与 react 全家桶拆为独立 chunk，
  // 改善首屏加载与浏览器缓存命中率（d3 约 500KB，变更频率低）
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          d3: ['d3'],
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
        },
      },
    },
  },
  server: {
    port: 3001,
    proxy: {
      '/api': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
    },
  },
  // 生产预览（vite preview）同样将 /api 代理到后端，供 Docker 一体化镜像使用
  preview: {
    port: 3001,
    host: true,
    proxy: {
      '/api': {
        target: process.env.BACKEND_URL || 'http://localhost:5001',
        changeOrigin: true,
      },
    },
  },
})
