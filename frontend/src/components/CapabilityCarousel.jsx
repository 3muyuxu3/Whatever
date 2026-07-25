import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { useGSAP } from '@gsap/react'

gsap.registerPlugin(useGSAP, ScrollTrigger)

// 自动轮播间隔（毫秒）
const AUTOPLAY_MS = 3800

/**
 * CapabilityCarousel —— 能力介绍「3D 覆盖流（coverflow）」轮播
 *
 * 卡片以 3D 透视环绕排布：中心卡片正对用户、清晰放大，两侧卡片依次缩小、
 * 后退、侧转并淡出，形成炫酷的纵深层次。支持自动轮播（悬停暂停）、左右箭头、
 * 圆点指示、点击侧卡聚焦、触摸滑动切换。
 *
 * 通过 useGSAP 自动清理补间；尊重 prefers-reduced-motion（即时切换、不自动播放）。
 */
export default function CapabilityCarousel({ items }) {
    const { t } = useTranslation()
    const n = items.length

    const wrapRef = useRef(null)
    const stageRef = useRef(null)
    const cardsRef = useRef([])
    const activeRef = useRef(0)
    const firstRunRef = useRef(true)
    const spreadRef = useRef(320) // 相邻卡片水平间距（随断点变化）
    const dragXRef = useRef(null)
    const reduceRef = useRef(
        typeof window !== 'undefined' &&
        window.matchMedia?.('(prefers-reduced-motion: reduce)').matches,
    )

    const [active, setActive] = useState(0)
    const [paused, setPaused] = useState(false)
    const [reduced, setReduced] = useState(reduceRef.current)

    // 渲染期同步最新 active，确保 useLayoutEffect(useGSAP) 与 matchMedia 重排都读到最新值
    activeRef.current = active

    // 将相对偏移归一化到 [-2, 2]，实现无限环绕
    const wrapOffset = useCallback(
        (offset) => {
            const half = n / 2
            let o = offset
            if (o > half) o -= n
            if (o < -half) o += n
            return o
        },
        [n],
    )

    // 计算并应用每张卡片的 3D 变换；animate=false 时立即定位（初始化 / 响应式重排）
    const layout = useCallback(
        (animate) => {
            const spread = spreadRef.current
            const moving = animate && !reduceRef.current
            cardsRef.current.forEach((el, i) => {
                if (!el) return
                const offset = wrapOffset(i - activeRef.current)
                const abs = Math.abs(offset)
                const hidden = abs > 1 // 仅展示中心与左右各一张，其余隐于身后
                gsap.to(el, {
                    xPercent: -50,
                    yPercent: -50,
                    x: offset * spread,
                    z: hidden ? -360 : -abs * 180,
                    rotationY: offset * -38,
                    scale: abs === 0 ? 1 : abs === 1 ? 0.8 : 0.6,
                    autoAlpha: hidden ? 0 : abs === 0 ? 1 : 0.5,
                    zIndex: 100 - abs,
                    duration: moving ? 0.7 : 0,
                    ease: 'power3.out',
                    overwrite: 'auto',
                })
            })
        },
        [wrapOffset],
    )

    // 跟随系统「减少动画」偏好变化
    useEffect(() => {
        const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
        const onChange = () => {
            reduceRef.current = mq.matches
            setReduced(mq.matches)
        }
        mq.addEventListener?.('change', onChange)
        return () => mq.removeEventListener?.('change', onChange)
    }, [])

    // 初始定位 + 滚动揭示 + 响应式间距（useGSAP 负责卸载时清理）
    useGSAP(
        () => {
            const mm = gsap.matchMedia()
            mm.add('(max-width: 640px)', () => {
                spreadRef.current = 190
                layout(false)
            })
            mm.add('(min-width: 641px) and (max-width: 1024px)', () => {
                spreadRef.current = 260
                layout(false)
            })
            mm.add('(min-width: 1025px)', () => {
                spreadRef.current = 330
                layout(false)
            })

            // 整组卡片随滚动淡入上浮（一次性）
            if (!reduceRef.current) {
                gsap.from(stageRef.current, {
                    autoAlpha: 0,
                    y: 60,
                    duration: 0.9,
                    ease: 'power3.out',
                    scrollTrigger: { trigger: wrapRef.current, start: 'top 82%', once: true },
                })
            }

            return () => mm.revert()
        },
        { scope: wrapRef },
    )

    // active 变化时以动画过渡到新布局（首次渲染跳过，避免重复动画）
    useGSAP(
        () => {
            if (firstRunRef.current) {
                firstRunRef.current = false
                return
            }
            layout(true)
        },
        { dependencies: [active], scope: wrapRef },
    )

    // 自动轮播：悬停 / 减少动画时暂停；active 变化会重置计时
    useEffect(() => {
        if (paused || reduced) return
        const id = setInterval(() => setActive((a) => (a + 1) % n), AUTOPLAY_MS)
        return () => clearInterval(id)
    }, [paused, reduced, active, n])

    const go = useCallback((dir) => setActive((a) => (a + dir + n) % n), [n])

    // 滚轮切换：在轮播区域内滚动即切换上一张 / 下一张（兼容触控板横向滑动）。
    // React 的 onWheel 为被动监听无法 preventDefault，故用原生非被动监听；
    // 累积达阈值才切换，并节流至与 0.7s 切换动画匹配的节奏，避免一滚到底连跳多张。
    useEffect(() => {
        const el = wrapRef.current
        if (!el) return
        let acc = 0
        let lockUntil = 0
        const onWheel = (e) => {
            e.preventDefault()
            const now = Date.now()
            if (now < lockUntil) return
            const delta = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY
            acc += delta
            if (Math.abs(acc) > 40) {
                go(acc > 0 ? 1 : -1)
                acc = 0
                lockUntil = now + 600
            }
        }
        el.addEventListener('wheel', onWheel, { passive: false })
        return () => el.removeEventListener('wheel', onWheel)
    }, [go])

    // 触摸滑动切换（仅限触摸 / 触控笔，避免与鼠标点击聚焦冲突）
    const onPointerDown = (e) => {
        if (e.pointerType === 'mouse') return
        dragXRef.current = e.clientX
    }
    const onPointerUp = (e) => {
        if (dragXRef.current == null) return
        const dx = e.clientX - dragXRef.current
        dragXRef.current = null
        if (Math.abs(dx) > 40) go(dx < 0 ? 1 : -1)
    }

    return (
        <div
            ref={wrapRef}
            className="relative"
            onMouseEnter={() => setPaused(true)}
            onMouseLeave={() => setPaused(false)}
        >
            {/* 3D 舞台（透视 + 溢出裁剪） */}
            <div className="overflow-hidden px-4 py-8">
                <div
                    ref={stageRef}
                    className="relative mx-auto h-[320px] w-full"
                    style={{ perspective: '1500px' }}
                    onPointerDown={onPointerDown}
                    onPointerUp={onPointerUp}
                >
                    {items.map((cap, i) => (
                        <div
                            key={cap.key}
                            ref={(el) => (cardsRef.current[i] = el)}
                            onClick={() => setActive(i)}
                            className="liquid-glass absolute left-1/2 top-1/2 flex h-[280px] w-[78vw] max-w-[300px] cursor-pointer select-none flex-col rounded-2xl p-7"
                        >
                            <img
                                src={cap.icon}
                                alt=""
                                className="mb-5 h-11 w-11 opacity-90"
                                loading="lazy"
                                draggable={false}
                            />
                            <h3 className="mb-3 text-xl font-medium">
                                {t(`capabilities.${cap.key}.title`)}
                            </h3>
                            <p className="text-sm leading-relaxed text-gray-400">
                                {t(`capabilities.${cap.key}.desc`)}
                            </p>
                        </div>
                    ))}
                </div>
            </div>

            {/* 左右切换箭头 */}
            <button
                type="button"
                onClick={() => go(-1)}
                aria-label="Previous"
                className="liquid-glass absolute left-1 top-1/2 z-20 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full text-2xl leading-none text-white/80 transition hover:text-white md:left-4"
            >
                ‹
            </button>
            <button
                type="button"
                onClick={() => go(1)}
                aria-label="Next"
                className="liquid-glass absolute right-1 top-1/2 z-20 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full text-2xl leading-none text-white/80 transition hover:text-white md:right-4"
            >
                ›
            </button>

            {/* 圆点指示器 */}
            <div className="mt-4 flex items-center justify-center gap-2.5">
                {items.map((cap, i) => (
                    <button
                        key={cap.key}
                        type="button"
                        onClick={() => setActive(i)}
                        aria-label={`Go to slide ${i + 1}`}
                        className={`h-2 rounded-full transition-all duration-300 ${i === active ? 'w-7 bg-white' : 'w-2 bg-white/30 hover:bg-white/50'
                            }`}
                    />
                ))}
            </div>
        </div>
    )
}
