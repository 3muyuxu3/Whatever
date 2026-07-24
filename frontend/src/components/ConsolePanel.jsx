import { useEffect, useRef } from 'react'

/**
 * ConsolePanel —— 黑色终端日志面板
 *
 * 用于流程页底部展示系统 / 模拟 / 报告的实时日志。
 *
 * @param {string} title  面板标题（左上）
 * @param {string} id      右上角的运行标识（等宽字体）
 * @param {Array}  lines   日志行：{ time?, level?, text }
 */
export default function ConsolePanel({ title = 'CONSOLE OUTPUT', id, lines = [], className = '' }) {
    const bodyRef = useRef(null)

    // 新日志到达时自动滚动到底部
    useEffect(() => {
        if (bodyRef.current) {
            bodyRef.current.scrollTop = bodyRef.current.scrollHeight
        }
    }, [lines])

    return (
        <div className={`flex flex-col overflow-hidden bg-[#0a0a0c] text-neutral-200 ${className}`}>
            <div className="flex items-center justify-between border-b border-white/10 px-4 py-2">
                <span className="text-[11px] font-semibold tracking-[0.2em] text-neutral-400">
                    {title}
                </span>
                {id && <span className="font-mono text-[11px] text-neutral-500">{id}</span>}
            </div>
            <div
                ref={bodyRef}
                className="flex-1 overflow-auto px-4 py-2 font-mono text-[12px] leading-relaxed"
            >
                {lines.length === 0 && <div className="text-neutral-600">…</div>}
                {lines.map((l, i) => (
                    <div key={i} className="whitespace-pre-wrap break-all">
                        {l.time && <span className="text-neutral-500">[{l.time}] </span>}
                        {l.level && <span className={l.level === 'ERROR' ? 'text-red-400' : 'text-emerald-400'}>{l.level} </span>}
                        <span className={l.tone === 'accent' ? 'text-sky-300' : ''}>{l.text}</span>
                    </div>
                ))}
            </div>
        </div>
    )
}
