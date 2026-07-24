import { useEffect } from 'react'
import * as THREE from 'three'

/**
 * useThreeScene —— 通用 Three.js 场景挂载 hook（StrictMode 安全）
 *
 * 封装渲染器 / 场景 / 相机的创建、尺寸自适应、渲染循环与彻底清理，避免在多个
 * 页面里重复编写样板；并统一处理：
 *  - StrictMode 双重挂载：由 Three.js 自建 canvas 插入容器，卸载时移除 + forceContextLoss；
 *  - prefers-reduced-motion：仅静态渲染一帧，不启动循环；
 *  - IntersectionObserver：离开视口暂停循环，节省资源；
 *  - ResizeObserver：容器尺寸变化时同步相机与渲染器。
 *
 * @param {React.RefObject<HTMLElement>} hostRef 容器 ref（canvas 铺满其中）
 * @param {(ctx) => ({update?, resize?, dispose?})} build
 *        构建回调，ctx = { THREE, scene, camera, renderer, host, width, height, reduced }
 *        返回值：update(time, dt) 每帧调用；resize(w,h) 尺寸变化；dispose() 释放自建资源。
 * @param {Array} deps 依赖数组，变化时重建场景（默认仅挂载一次）
 * @param {{ cameraZ?: number, fov?: number }} opts
 */
export function useThreeScene(hostRef, build, deps = [], opts = {}) {
    useEffect(() => {
        const host = hostRef.current
        if (!host) return

        const reduced = !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

        // —— 渲染器（自建 canvas，规避 StrictMode 复用同一 canvas 的上下文冲突）——
        let renderer
        try {
            renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'high-performance' })
        } catch {
            return
        }
        if (!renderer.getContext()) return
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
        renderer.setClearColor(0x000000, 0)
        const canvas = renderer.domElement
        canvas.className = 'absolute inset-0 block h-full w-full'
        host.appendChild(canvas)

        const scene = new THREE.Scene()
        const camera = new THREE.PerspectiveCamera(opts.fov ?? 50, 1, 0.1, 100)
        camera.position.z = opts.cameraZ ?? 6

        let width = host.clientWidth || 1
        let height = host.clientHeight || 1
        const applySize = () => {
            width = host.clientWidth || 1
            height = host.clientHeight || 1
            renderer.setSize(width, height, false)
            camera.aspect = width / height
            camera.updateProjectionMatrix()
        }
        applySize()

        // 交给调用方构建具体内容
        const api = build({ THREE, scene, camera, renderer, host, width, height, reduced }) || {}

        const ro = new ResizeObserver(() => {
            applySize()
            api.resize?.(width, height)
            if (reduced) renderer.render(scene, camera)
        })
        ro.observe(host)

        // —— 渲染循环（手动计时，避开已弃用的 THREE.Clock）——
        let raf = 0
        let running = false
        const startTime = performance.now()
        let last = startTime
        const frame = () => {
            raf = requestAnimationFrame(frame)
            const now = performance.now()
            const dt = Math.min((now - last) / 1000, 0.05)
            last = now
            api.update?.((now - startTime) / 1000, dt)
            renderer.render(scene, camera)
        }
        const start = () => {
            if (running || reduced) return
            running = true
            last = performance.now()
            raf = requestAnimationFrame(frame)
        }
        const stop = () => {
            running = false
            if (raf) cancelAnimationFrame(raf)
            raf = 0
        }

        // 视口内才渲染
        const io = new IntersectionObserver(
            ([entry]) => {
                if (entry.isIntersecting) {
                    if (reduced) renderer.render(scene, camera)
                    else start()
                } else {
                    stop()
                }
            },
            { threshold: 0.01 },
        )
        io.observe(host)

        return () => {
            stop()
            io.disconnect()
            ro.disconnect()
            api.dispose?.()
            renderer.dispose()
            renderer.forceContextLoss?.()
            if (canvas.parentNode) canvas.parentNode.removeChild(canvas)
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, deps)
}
