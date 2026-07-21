import { useEffect, useState } from 'react'

/**
 * AnimatedHeading —— 逐字入场动画标题
 *
 * 将文本按 \n 拆分为多行，每行再拆分为单个字符；每个字符是一个
 * inline-block 的 <span>，通过 React state 在初始延迟后触发：
 *   - opacity: 0 -> 1
 *   - transform: translateX(-18px) -> translateX(0)
 *
 * 每个字符的交错延迟计算公式：
 *   (lineIndex * lineLength * charDelay) + (charIndex * charDelay)
 *
 * 空格渲染为不换行空格（\u00A0）。
 *
 * @param {string} text          原始文本（可包含 \n 换行）
 * @param {number} charDelay     单字符延迟增量（毫秒，默认 30）
 * @param {number} initialDelay  整体动画初始延迟（毫秒，默认 200）
 * @param {number} charDuration  单字符过渡时长（毫秒，默认 500）
 */
export default function AnimatedHeading({
    text,
    className = '',
    style = {},
    charDelay = 30,
    initialDelay = 200,
    charDuration = 500,
}) {
    const [started, setStarted] = useState(false)

    useEffect(() => {
        const timer = setTimeout(() => setStarted(true), initialDelay)
        return () => clearTimeout(timer)
    }, [initialDelay])

    const lines = text.split('\n')

    return (
        <h1 className={className} style={style}>
            {lines.map((line, lineIndex) => (
                <span key={lineIndex} className="block">
                    {Array.from(line).map((char, charIndex) => {
                        // 交错延迟：行偏移量 + 字符偏移量
                        const delay =
                            lineIndex * line.length * charDelay + charIndex * charDelay
                        return (
                            <span
                                key={charIndex}
                                className="inline-block"
                                style={{
                                    opacity: started ? 1 : 0,
                                    transform: started ? 'translateX(0)' : 'translateX(-18px)',
                                    transition: `opacity ${charDuration}ms ease, transform ${charDuration}ms ease`,
                                    transitionDelay: `${delay}ms`,
                                }}
                            >
                                {/* 空格使用不换行空格，避免被浏览器折叠 */}
                                {char === ' ' ? '\u00A0' : char}
                            </span>
                        )
                    })}
                </span>
            ))}
        </h1>
    )
}
