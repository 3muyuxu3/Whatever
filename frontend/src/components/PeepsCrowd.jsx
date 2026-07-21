import { useEffect, useMemo, useState } from 'react'

// public/image 下共有 openpeeps1.svg ... openpeeps105.svg
const TOTAL = 105
// 同时在场的人物数量（越多越密集，兼顾性能）
const CROWD_SIZE = 64

// SVG 原始尺寸（宽高比 ≈ 20:27）
const SVG_W = 240
const SVG_H = 324

// 景深参数（对齐 MiroFish：深度 0.30~0.85，缩放 0.5~1.8，焦点 0.75，最大模糊 4px）
const MIN_Z = 0.3
const MAX_Z = 0.85
const MIN_SCALE = 0.5
const MAX_SCALE = 1.8
const FOCAL = 0.75
const MAX_BLUR = 4

/**
 * 稳定的伪随机（基于种子），保证每次渲染人群一致，避免闪烁。
 */
function seeded(i) {
    const x = Math.sin(i * 999.13) * 10000
    return x - Math.floor(x)
}

/**
 * 依据深度 z 计算单个人物的展示属性。
 * 深度越大：越靠前、越大、越清晰、越靠下（z-index 越高）。
 */
function buildPeep(i) {
    const z = MIN_Z + seeded(i * 3 + 1) * (MAX_Z - MIN_Z)
    // 非线性缩放，贴近真实透视
    const nonLinear = (1 / (5 - 4 * z) - 0.2) / 0.8
    const scale = MIN_SCALE + (MAX_SCALE - MIN_SCALE) * nonLinear
    // 景深模糊：焦点(0.75)处最清晰，越远离越模糊
    const blur = (MAX_BLUR * Math.abs(z - FOCAL)) / 0.75
    const width = SVG_W * scale
    const height = SVG_H * scale
    const zIndex = Math.floor(z * 100) // 30~85
    const top = z * 100 // 深度决定垂直位置（近处更靠下）
    const toRight = seeded(i * 3 + 2) > 0.5 // 一半向右、一半向左
    // 行走速度 3~12 vw/s（二次方偏向慢速），行走距离约 136vw
    const speed = 3 + Math.pow(seeded(i * 3 + 3), 2) * 9
    const duration = 136 / speed // ≈ 11~45s
    const delay = -seeded(i * 5 + 7) * duration // 负延迟：分散初始位置
    const idx = 1 + (Math.floor(seeded(i * 7 + 11) * TOTAL) % TOTAL) // 1..105
    return { idx, width, height, blur, zIndex, top, toRight, duration, delay }
}

/**
 * PeepsCrowd —— 首页底部「行走的人群」（景深纵深版）
 *
 * - 单一容器内放置数十个人物，按深度 z 决定大小/模糊/层级/垂直位置，营造人群纵深；
 * - 一半人物从左向右走、一半从右向左走（镜像朝向），速度各异并循环；
 * - 底部渐深，人群仿佛从黑暗中浮现；
 * - 页面向下滚动时整体淡出下沉消失（向上滚动恢复）。
 */
export default function PeepsCrowd() {
    const [progress, setProgress] = useState(0)

    useEffect(() => {
        const onScroll = () => {
            const h = window.innerHeight || 800
            // 下滑约 0.4 屏即完全消失
            const p = Math.min(Math.max(window.scrollY / (h * 0.4), 0), 1)
            setProgress(p)
        }
        onScroll()
        window.addEventListener('scroll', onScroll, { passive: true })
        return () => window.removeEventListener('scroll', onScroll)
    }, [])

    const peeps = useMemo(
        () => Array.from({ length: CROWD_SIZE }, (_, i) => buildPeep(i)),
        []
    )

    return (
        <div
            className="peeps-crowd pointer-events-none absolute inset-x-0 bottom-0 z-[6] h-[38vh] overflow-hidden"
            style={{
                opacity: 1 - progress,
                transform: `translateY(${progress * 100}px)`,
                transition: 'opacity 0.2s linear, transform 0.2s linear',
            }}
            aria-hidden="true"
        >
            {/* 底部渐深：让白色线条人群更清晰，并呈现「从黑暗中走来」的观感 */}
            <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/25 to-transparent" />

            {peeps.map((p, i) => (
                <div
                    key={i}
                    className="absolute left-0 will-change-transform"
                    style={{
                        top: `${p.top}%`,
                        width: `${p.width}px`,
                        height: `${p.height}px`,
                        zIndex: p.zIndex,
                        animation: `${p.toRight ? 'peep-walk-right' : 'peep-walk-left'} ${p.duration.toFixed(2)}s linear ${p.delay.toFixed(2)}s infinite`,
                    }}
                >
                    <img
                        src={`/image/openpeeps${p.idx}.svg`}
                        alt=""
                        draggable="false"
                        loading="lazy"
                        className="h-full w-full select-none"
                        style={{
                            filter: `blur(${p.blur.toFixed(2)}px)`,
                            // 向左行走的人物水平翻转，朝向行进方向
                            transform: p.toRight ? 'none' : 'scaleX(-1)',
                        }}
                    />
                </div>
            ))}
        </div>
    )
}
