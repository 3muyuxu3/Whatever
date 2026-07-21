import { useEffect, useState } from 'react'

/**
 * FadeIn —— 淡入包装组件
 * 初始状态 opacity:0，在 delay 毫秒后过渡到 opacity:1。
 * 过渡时长由 duration 控制，使用 Tailwind 的 transition-opacity + 内联 transitionDuration。
 *
 * @param {number} delay    动画开始前的延迟（毫秒）
 * @param {number} duration 淡入过渡时长（毫秒）
 */
export default function FadeIn({
    children,
    delay = 0,
    duration = 1000,
    className = '',
}) {
    const [visible, setVisible] = useState(false)

    useEffect(() => {
        const timer = setTimeout(() => setVisible(true), delay)
        return () => clearTimeout(timer)
    }, [delay])

    return (
        <div
            className={`transition-opacity ${className}`}
            style={{
                opacity: visible ? 1 : 0,
                transitionDuration: `${duration}ms`,
            }}
        >
            {children}
        </div>
    )
}
