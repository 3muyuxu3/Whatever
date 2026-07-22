import { useTranslation } from 'react-i18next'

// 行内格式：**加粗** / `代码` / *斜体*
function renderInline(text, keyPrefix = 'i') {
    const nodes = []
    let rest = String(text ?? '')
    let k = 0
    const re = /(\*\*([^*]+)\*\*|`([^`]+)`|\*([^*]+)\*)/
    while (rest) {
        const m = rest.match(re)
        if (!m) {
            nodes.push(rest)
            break
        }
        if (m.index > 0) nodes.push(rest.slice(0, m.index))
        if (m[2] !== undefined) {
            nodes.push(
                <strong key={`${keyPrefix}-${k++}`} className="font-semibold text-neutral-900">
                    {m[2]}
                </strong>,
            )
        } else if (m[3] !== undefined) {
            nodes.push(
                <code
                    key={`${keyPrefix}-${k++}`}
                    className="rounded bg-neutral-100 px-1 py-0.5 font-mono text-[0.85em] text-neutral-700"
                >
                    {m[3]}
                </code>,
            )
        } else if (m[4] !== undefined) {
            nodes.push(<em key={`${keyPrefix}-${k++}`}>{m[4]}</em>)
        }
        rest = rest.slice(m.index + m[0].length)
    }
    return nodes
}

// 富文本 Markdown 解析：标题 / 引言 / 章节(##) / 子标题(###) / 引用(>) / 列表 / 表格 / 段落
function parseReport(content) {
    const lines = (content || '').split('\n')
    let title = ''
    const intro = []
    const sections = []
    let cur = null
    const bucket = () => (cur ? cur.body : intro)

    let i = 0
    while (i < lines.length) {
        const line = (lines[i] || '').trim()
        if (!line) {
            i++
            continue
        }
        if (line.startsWith('## ')) {
            cur = { title: line.slice(3).trim(), body: [] }
            sections.push(cur)
            i++
            continue
        }
        if (line.startsWith('# ')) {
            title = line.slice(2).trim()
            i++
            continue
        }
        if (line.startsWith('### ')) {
            bucket().push({ type: 'h3', text: line.slice(4).trim() })
            i++
            continue
        }
        if (line.startsWith('> ')) {
            bucket().push({ type: 'quote', text: line.slice(2) })
            i++
            continue
        }

        // 表格：当前行含 |，且下一行是分隔行（含 - 与 |）
        const next = lines[i + 1]
        if (
            line.includes('|') &&
            next &&
            next.includes('-') &&
            /^\s*\|?[\s:|-]+\|?\s*$/.test(next)
        ) {
            const splitRow = (r) =>
                r.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim())
            const headers = splitRow(line)
            const rows = []
            i += 2
            while (i < lines.length && lines[i].includes('|') && lines[i].trim()) {
                rows.push(splitRow(lines[i]))
                i++
            }
            bucket().push({ type: 'table', headers, rows })
            continue
        }

        // 列表（无序 / 有序）
        const isUl = /^[-*]\s+/.test(line)
        const isOl = /^\d+\.\s+/.test(line)
        if (isUl || isOl) {
            const type = isUl ? 'ul' : 'ol'
            const items = []
            while (i < lines.length) {
                const l = (lines[i] || '').trim()
                const m = type === 'ul' ? l.match(/^[-*]\s+(.*)$/) : l.match(/^\d+\.\s+(.*)$/)
                if (!m) break
                items.push(m[1])
                i++
            }
            bucket().push({ type, items })
            continue
        }

        bucket().push({ type: 'p', text: line.replace(/^#{1,6}\s*/, '') })
        i++
    }
    return { title, intro, sections }
}

function Block({ item }) {
    switch (item.type) {
        case 'quote':
            return (
                <blockquote className="my-3 border-l-2 border-neutral-300 pl-4 italic text-neutral-500">
                    {renderInline(item.text)}
                </blockquote>
            )
        case 'h3':
            return <h3 className="mb-1 mt-4 text-base font-semibold text-neutral-800">{renderInline(item.text)}</h3>
        case 'ul':
            return (
                <ul className="my-2 list-disc space-y-1 pl-5 text-sm leading-relaxed text-neutral-700">
                    {item.items.map((it, i) => (
                        <li key={i}>{renderInline(it, `ul${i}`)}</li>
                    ))}
                </ul>
            )
        case 'ol':
            return (
                <ol className="my-2 list-decimal space-y-1 pl-5 text-sm leading-relaxed text-neutral-700">
                    {item.items.map((it, i) => (
                        <li key={i}>{renderInline(it, `ol${i}`)}</li>
                    ))}
                </ol>
            )
        case 'table':
            return (
                <div className="my-3 overflow-x-auto">
                    <table className="w-full border-collapse text-sm">
                        <thead>
                            <tr>
                                {item.headers.map((h, i) => (
                                    <th
                                        key={i}
                                        className="border border-neutral-200 bg-neutral-50 px-3 py-2 text-left font-semibold text-neutral-700"
                                    >
                                        {renderInline(h, `th${i}`)}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {item.rows.map((row, r) => (
                                <tr key={r}>
                                    {row.map((cell, c) => (
                                        <td key={c} className="border border-neutral-200 px-3 py-2 text-neutral-600">
                                            {renderInline(cell, `td${r}-${c}`)}
                                        </td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )
        default:
            return <p className="my-2 text-sm leading-relaxed text-neutral-700">{renderInline(item.text)}</p>
    }
}

/**
 * ReportContent —— 预测报告正文渲染（供 Step4 / Step5 复用）
 *
 * 支持标题、引言、章节、子标题、引用、有序/无序列表、表格与行内格式（加粗/代码/斜体）。
 *
 * @param {string} reportId  报告 ID
 * @param {string} content   Markdown 内容
 * @param {boolean} generating 是否生成中
 * @param {Array}  outline    生成中时的章节骨架（字符串数组）
 */
export default function ReportContent({ reportId, content, generating = false, outline = [] }) {
    const { t } = useTranslation()
    const { title, intro, sections } = parseReport(content)

    return (
        <div className="p-8">
            <div className="mb-4 flex items-center gap-3">
                <span className="rounded bg-neutral-900 px-2 py-1 text-[11px] font-semibold tracking-widest text-white">
                    {t('process.predictionReport')}
                </span>
                {reportId && <span className="font-mono text-xs text-neutral-400">ID: {reportId}</span>}
            </div>

            <h1 className="text-3xl font-bold leading-tight tracking-tight text-neutral-900">
                {title || t('process.reportGenerating')}
            </h1>

            {intro.length > 0 && (
                <div className="mt-4 border-b border-neutral-200 pb-6 italic text-neutral-500">
                    {intro.map((b, i) => (
                        <Block key={i} item={b} />
                    ))}
                </div>
            )}

            {/* 已生成章节 */}
            <div className="mt-6 space-y-8">
                {sections.map((sec, i) => (
                    <section key={i}>
                        <div className="flex items-baseline gap-3">
                            <span className="font-mono text-sm text-neutral-300">
                                {String(i + 1).padStart(2, '0')}
                            </span>
                            <h2 className="text-xl font-bold text-neutral-900">{sec.title}</h2>
                        </div>
                        <div className="mt-3 pl-8">
                            {sec.body.map((b, j) => (
                                <Block key={j} item={b} />
                            ))}
                        </div>
                    </section>
                ))}

                {/* 生成中：展示未完成章节骨架 */}
                {generating &&
                    outline.slice(sections.length).map((titleText, i) => (
                        <section key={`sk-${i}`} className="opacity-40">
                            <div className="flex items-baseline gap-3">
                                <span className="font-mono text-sm text-neutral-300">
                                    {String(sections.length + i + 1).padStart(2, '0')}
                                </span>
                                <h2 className="text-xl font-bold text-neutral-400">{titleText}</h2>
                            </div>
                            <div className="mt-3 flex items-center gap-2 pl-8 text-sm text-neutral-400">
                                <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-neutral-300 border-t-transparent" />
                                {t('process.reportGenerating')}…
                            </div>
                        </section>
                    ))}

                {!content && !generating && (
                    <p className="text-sm text-neutral-400">{t('common.loading')}</p>
                )}
            </div>
        </div>
    )
}
