import { useEffect, useRef } from 'react'
import * as THREE from 'three'

// ===== 着色器 =====
// 顶点：全屏 quad，直接透传 UV
const VERT = /* glsl */ `
    varying vec2 vUv;
    void main() {
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }
`

// 片元：将「文字纹理」按鼠标临近做碎块位移 / 故障扭曲；离开后随 uHover 平滑复位。
// 文字为黑色、背景透明（绿底由容器 CSS 提供，从位移产生的空隙中透出）。
const FRAG = /* glsl */ `
    precision highp float;

    uniform sampler2D uTex;   // 文字纹理（黑字 + 透明底）
    uniform vec2  uMouse;     // 鼠标位置（0~1，y 向上）
    uniform float uHover;     // 悬停强度（缓动 0~1）
    uniform float uTime;      // 时间（秒）
    uniform vec2  uAspect;    // 距离各向同性校正 (1.0, h/w)
    uniform vec2  uGrid;      // 碎块网格（近似方形单元）
    uniform vec3  uColor;     // 文字颜色
    uniform float uReduced;   // 1.0 = 尊重「减少动画」，关闭常态波动

    varying vec2 vUv;

    // 稳定的伪随机
    float hash21(vec2 p) {
        p = fract(p * vec2(123.34, 345.45));
        p += dot(p, p + 34.345);
        return fract(p.x * p.y);
    }

    void main() {
        vec2 uv = vUv;

        // 以宽高比校正的鼠标距离，得到局部作用力（越靠近越强）
        vec2 diff = (uv - uMouse) * uAspect;
        float force = smoothstep(0.30, 0.0, length(diff)) * uHover;

        // 碎块网格：靠近鼠标的方块沿伪随机方向位移，并随时间跳变 → 故障 / 碎裂
        vec2 cell = floor(uv * uGrid);
        float tStep = floor(uTime * 9.0);
        float rnd = hash21(cell + tStep);
        vec2 dir = normalize(vec2(hash21(cell + 1.3), hash21(cell + 7.7)) * 2.0 - 1.0 + 1e-4);
        vec2 disp = dir * force * (0.03 + 0.11 * rnd);

        // 常态呼吸波（reduced-motion 时关闭），让文字始终有细微生命感
        float idle = (1.0 - uReduced) * 0.0022;
        disp += vec2(sin(uv.y * 26.0 + uTime * 1.3), cos(uv.x * 22.0 + uTime * 1.1)) * idle;

        float a = texture2D(uTex, uv + disp).a;

        // 强扰动处偶发方块闪隐，增强故障质感
        a *= 1.0 - force * 0.18 * step(0.9, hash21(cell + tStep + 3.7));

        if (a < 0.02) discard;
        gl_FragColor = vec4(uColor, a);
    }
`

/**
 * GiantWordmark —— 首页最底部的巨型品牌字
 *
 * 以 Three.js 全屏 quad + 片元着色器实现：把文字绘制成纹理，随鼠标临近产生
 * 「碎块位移 / 故障」扭曲，离开后平滑复位。绿底黑字、宽度铺满、上下微裁切。
 * - 尊重 prefers-reduced-motion / 触摸设备：静态渲染，不做鼠标扭曲；
 * - IntersectionObserver：离开视口暂停渲染循环，节省资源；
 * - 卸载时释放 geometry / material / texture / renderer 并移除全部监听；
 * - WebGL 不可用时降级为纯文字，保证可读与无障碍。
 */
export default function GiantWordmark({ word = 'MUYU', color = '#32F08C' }) {
    const containerRef = useRef(null)
    const fallbackRef = useRef(null)

    useEffect(() => {
        const container = containerRef.current
        if (!container) return

        const reduceMq = window.matchMedia?.('(prefers-reduced-motion: reduce)')
        const fineMq = window.matchMedia?.('(pointer: fine)')
        let prefersReduced = !!reduceMq?.matches
        // 是否启用鼠标交互扭曲（精确指针 + 非减少动画）
        let interactive = !prefersReduced && !!fineMq?.matches

        // —— 初始化 Three.js（WebGL 失败则降级为纯文字）——
        let renderer
        try {
            renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true })
        } catch {
            if (fallbackRef.current) fallbackRef.current.style.opacity = '1'
            return
        }
        if (!renderer.getContext()) {
            if (fallbackRef.current) fallbackRef.current.style.opacity = '1'
            return
        }
        renderer.setClearColor(0x000000, 0)
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
        // 由 Three.js 自建 canvas 并插入容器：避免 React 复用同一 canvas
        // 在严格模式双重挂载时引发「上下文类型冲突」。
        const glCanvas = renderer.domElement
        glCanvas.className = 'absolute inset-0 block h-full w-full'
        container.appendChild(glCanvas)

        const scene = new THREE.Scene()
        const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 10)
        camera.position.z = 1

        // —— 文字纹理（用离屏 canvas 绘制，随尺寸重绘以保持清晰）——
        const texCanvas = document.createElement('canvas')
        const texCtx = texCanvas.getContext('2d')
        const texture = new THREE.CanvasTexture(texCanvas)
        texture.minFilter = THREE.LinearFilter
        texture.magFilter = THREE.LinearFilter

        const FONT = '"Arial Black", "Inter", system-ui, sans-serif'

        // 将文字按宽度铺满绘制到纹理（黑字 + 透明底）
        const drawText = (w, h) => {
            const dpr = Math.min(window.devicePixelRatio || 1, 2)
            const cw = Math.max(2, Math.floor(w * dpr))
            const ch = Math.max(2, Math.floor(h * dpr))
            texCanvas.width = cw
            texCanvas.height = ch
            texCtx.clearRect(0, 0, cw, ch)
            texCtx.fillStyle = '#000'
            texCtx.textAlign = 'center'
            texCtx.textBaseline = 'alphabetic'
            try { texCtx.letterSpacing = '-0.02em' } catch { /* 部分浏览器不支持，忽略 */ }
            // 按「实际墨迹宽度」铺满字带：
            // 以 100px 量墨迹宽度后线性放大到目标宽度；高度若超出字带则对称裁切顶/底。
            texCtx.font = `900 100px ${FONT}`
            const m0 = texCtx.measureText(word)
            const inkW0 = ((m0.actualBoundingBoxLeft || 0) + (m0.actualBoundingBoxRight || 0)) || (m0.width || 1)
            const size = (cw * 0.98 / inkW0) * 100
            texCtx.font = `900 ${size}px ${FONT}`
            // 用实际墨迹边界做水平/垂直居中，使四周留白对称、裁切自然
            const m = texCtx.measureText(word)
            const ascent = m.actualBoundingBoxAscent || size * 0.72
            const descent = m.actualBoundingBoxDescent || 0
            const bl = m.actualBoundingBoxLeft || 0
            const br = m.actualBoundingBoxRight || (m.width || 0)
            const drawX = cw / 2 + (bl - br) / 2
            const baselineY = ch / 2 + (ascent - descent) / 2
            texCtx.fillText(word, drawX, baselineY)
            texture.needsUpdate = true
        }

        const material = new THREE.ShaderMaterial({
            transparent: true,
            depthTest: false,
            depthWrite: false,
            uniforms: {
                uTex: { value: texture },
                uMouse: { value: new THREE.Vector2(0.5, 0.5) },
                uHover: { value: 0 },
                uTime: { value: 0 },
                uAspect: { value: new THREE.Vector2(1, 0.3) },
                uGrid: { value: new THREE.Vector2(20, 6) },
                uColor: { value: new THREE.Color('#000000') },
                uReduced: { value: prefersReduced ? 1 : 0 },
            },
            vertexShader: VERT,
            fragmentShader: FRAG,
        })

        const mesh = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material)
        scene.add(mesh)

        // 缓动状态：悬停强度 + 鼠标位置（手动计时，避开已弃用的 THREE.Clock）
        const startTime = performance.now()
        let lastTime = startTime
        const mouse = new THREE.Vector2(0.5, 0.5)
        const mouseTarget = new THREE.Vector2(0.5, 0.5)
        let hover = 0
        let hoverTarget = 0

        // —— 尺寸同步：重设渲染器 / 相机、重绘文字、更新网格与各向同性参数 ——
        const resize = () => {
            const w = container.clientWidth || 1
            const h = container.clientHeight || 1
            renderer.setSize(w, h, false)
            drawText(w, h)
            const hw = h / w
            material.uniforms.uAspect.value.set(1, hw)
            // 方形碎块：列数随宽度自适应，行数 = 列数 * (h/w)
            const cols = Math.max(10, Math.min(30, Math.round(w / 70)))
            material.uniforms.uGrid.value.set(cols, Math.max(2, cols * hw))
            renderOnce()
        }

        const renderOnce = () => renderer.render(scene, camera)

        // —— 渲染循环（仅在需要动画且处于视口内时运行）——
        let raf = 0
        let looping = false
        const frame = () => {
            raf = requestAnimationFrame(frame)
            const now = performance.now()
            const dt = Math.min((now - lastTime) / 1000, 0.05)
            lastTime = now
            hover += (hoverTarget - hover) * Math.min(1, dt * 8)
            mouse.x += (mouseTarget.x - mouse.x) * Math.min(1, dt * 12)
            mouse.y += (mouseTarget.y - mouse.y) * Math.min(1, dt * 12)
            material.uniforms.uHover.value = hover
            material.uniforms.uMouse.value.copy(mouse)
            material.uniforms.uTime.value = (now - startTime) / 1000
            renderer.render(scene, camera)
        }
        const startLoop = () => {
            if (looping || prefersReduced) return
            looping = true
            lastTime = performance.now() // 丢弃暂停期间累计的时间差
            raf = requestAnimationFrame(frame)
        }
        const stopLoop = () => {
            looping = false
            if (raf) cancelAnimationFrame(raf)
            raf = 0
        }

        // —— 交互：鼠标移动更新目标位置与悬停强度 ——
        const onPointerMove = (e) => {
            const r = container.getBoundingClientRect()
            mouseTarget.x = (e.clientX - r.left) / r.width
            mouseTarget.y = 1 - (e.clientY - r.top) / r.height
            hoverTarget = 1
        }
        const onPointerLeave = () => { hoverTarget = 0 }
        if (interactive) {
            container.addEventListener('pointermove', onPointerMove, { passive: true })
            container.addEventListener('pointerleave', onPointerLeave)
            container.addEventListener('pointercancel', onPointerLeave)
        }

        // —— 视口内才渲染：静态时渲染一帧，动画时启停循环 ——
        const io = new IntersectionObserver(
            ([entry]) => {
                if (entry.isIntersecting) {
                    if (prefersReduced) renderOnce()
                    else startLoop()
                } else {
                    stopLoop()
                }
            },
            { threshold: 0.01 },
        )
        io.observe(container)

        // —— 尺寸变化重绘 ——
        const ro = new ResizeObserver(resize)
        ro.observe(container)

        // 跟随「减少动画」偏好实时切换
        const onReduceChange = () => {
            prefersReduced = !!reduceMq?.matches
            interactive = !prefersReduced && !!fineMq?.matches
            material.uniforms.uReduced.value = prefersReduced ? 1 : 0
            if (prefersReduced) { stopLoop(); hover = hoverTarget = 0; renderOnce() }
            else startLoop()
        }
        reduceMq?.addEventListener?.('change', onReduceChange)

        // 初次布局（等字体就绪后再重绘一次，避免回退字体测量误差）
        resize()
        if (document.fonts?.ready) document.fonts.ready.then(resize).catch(() => { })

        // —— 清理 ——
        return () => {
            stopLoop()
            io.disconnect()
            ro.disconnect()
            reduceMq?.removeEventListener?.('change', onReduceChange)
            if (interactive) {
                container.removeEventListener('pointermove', onPointerMove)
                container.removeEventListener('pointerleave', onPointerLeave)
                container.removeEventListener('pointercancel', onPointerLeave)
            }
            mesh.geometry.dispose()
            material.dispose()
            texture.dispose()
            renderer.dispose()
            renderer.forceContextLoss?.()
            if (glCanvas.parentNode) glCanvas.parentNode.removeChild(glCanvas)
        }
    }, [word])

    return (
        <section
            ref={containerRef}
            role="img"
            aria-label={word}
            className="relative w-full select-none overflow-hidden"
            style={{ height: 'clamp(120px, 20vw, 320px)', backgroundColor: color }}
        >
            {/* 降级文字：WebGL 不可用时显示（默认隐藏，不影响视觉与无障碍） */}
            <span
                ref={fallbackRef}
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 flex items-center justify-center text-black opacity-0"
                style={{ fontFamily: '"Arial Black","Inter",system-ui,sans-serif', fontWeight: 900, fontSize: 'clamp(64px, 16vw, 240px)', letterSpacing: '-0.02em' }}
            >
                {word}
            </span>
        </section>
    )
}
