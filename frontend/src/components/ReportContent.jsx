import { useTranslation } from 'react-i18next'

// 极简 Markdown 解析：标题 / 引言 / 章节（## 开头）/ 引用（>）/ 段落
function parseReport(content) {
    const lines = (content || '').split('\n')
    let title = ''
    const intro = []
    const sections = []
    let cur = null
    for (const raw of lines) {
        const line = raw.trim()
        if (!line) continue
        if (line.startsWith('## ')) {
            cur = { title: line.slice(3).trim(), body: [] }
            sections.push(cur)
            continue
        }
        if (line.startsWith('# ')) {
            title = line.slice(2).trim()
            continue
        }
        const bucket = cur ? cur.body : intro
        if (line.startsWith('> ')) bucket.push({ type: 'quote', text: line.slice(2) })
        else bucket.push({ type: 'p', text: line.replace(/^#{1,6}\s*/, '') })
    }
    return { title, intro, sections }
}

function Block({ item }) {
    if (item.type === 'quote') {
        return (
            <blockquote className="my-3 border-l-2 border-neutral-300 pl-4 italic text-neutral-500">
                {item.text}
            </blockquote>
        )
    }
    return <p className="my-2 text-sm leading-relaxed text-neutral-700">{item.text}</p>
}

/**
 * ReportContent —— 预测报告正文渲染（供 Step4 / Step5 复用）
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
