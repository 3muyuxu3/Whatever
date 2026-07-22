import { useEffect, useMemo, useRef, useState } from 'react'
import * as d3 from 'd3'
import { useTranslation } from 'react-i18next'
import { getEntity } from '../api/simulation'

// 10 色调色板：按实体类型着色
const COLOR_PALETTE = [
    '#f97316', '#2563eb', '#7c3aed', '#059669', '#dc2626',
    '#fb923c', '#0ea5e9', '#9333ea', '#65a30d', '#e11d48',
]

/**
 * GraphPanel —— D3 力导向知识图谱可视化（浅色主题，参考 MiroFish）
 *
 * 特性：白色点阵画布、标题、Refresh/全屏、Show Edge Labels 开关、实体图例、记忆更新提示；
 * forceSimulation 布局 + 拖拽/缩放 + 自环边 + 多重边曲线 + 节点/边详情。
 *
 * @param {Object}   data        { nodes, edges }
 * @param {boolean}  loading     是否加载中
 * @param {string}   memoryLabel 底部提示药丸文案（可选）
 * @param {Function} onRefresh   点击刷新回调（可选）
 */
export default function GraphPanel({ data, loading = false, memoryLabel, onRefresh, graphId }) {
    const { t } = useTranslation()
    const svgRef = useRef(null)
    const wrapRef = useRef(null)
    const [selected, setSelected] = useState(null)
    const [detail, setDetail] = useState(null)
    const [detailLoading, setDetailLoading] = useState(false)
    const [showEdgeLabels, setShowEdgeLabels] = useState(true)

    // 选中节点后，从后端拉取实体详情（摘要 + 关联事实）
    useEffect(() => {
        if (!graphId || !selected || selected.kind !== 'node') {
            setDetail(null)
            return
        }
        const uuid = selected.data.id
        if (!uuid) return
        let alive = true
        setDetail(null)
        setDetailLoading(true)
        getEntity(graphId, uuid)
            .then((res) => { if (alive) setDetail(res.data || null) })
            .catch(() => { if (alive) setDetail(null) })
            .finally(() => { if (alive) setDetailLoading(false) })
        return () => { alive = false }
    }, [selected, graphId])

    // 归一化数据：兼容后端不同字段命名
    const graph = useMemo(() => {
        const nodes = (data?.nodes || []).map((n) => ({
            id: n.uuid || n.id,
            name: n.name || n.label || n.id,
            type: n.type || (Array.isArray(n.labels) ? n.labels[0] : 'Entity'),
            raw: n,
        }))
        const edges = (data?.edges || data?.links || []).map((e) => ({
            source: e.source || e.source_node_uuid || e.from,
            target: e.target || e.target_node_uuid || e.to,
            name: e.name || e.type || e.relation || '',
            raw: e,
        }))
        return { nodes, edges }
    }, [data])

    // 实体类型 -> 颜色
    const color = useMemo(() => {
        const types = Array.from(new Set(graph.nodes.map((n) => n.type)))
        return d3.scaleOrdinal().domain(types).range(COLOR_PALETTE)
    }, [graph])

    useEffect(() => {
        if (!svgRef.current || !graph.nodes.length) return
        const width = wrapRef.current?.clientWidth || 800
        const height = wrapRef.current?.clientHeight || 520

        const svg = d3.select(svgRef.current)
        svg.selectAll('*').remove()
        svg.attr('viewBox', [0, 0, width, height])

        const root = svg.append('g')

        // 缩放与平移
        const zoom = d3
            .zoom()
            .scaleExtent([0.2, 4])
            .on('zoom', (event) => root.attr('transform', event.transform))
        svg.call(zoom)

        // 统计多重边，用于曲线偏移
        const pairCount = {}
        graph.edges.forEach((e) => {
            const key = [e.source, e.target].sort().join('--')
            pairCount[key] = (pairCount[key] || 0) + 1
        })
        const pairIndex = {}

        const simulation = d3
            .forceSimulation(graph.nodes)
            .force('link', d3.forceLink(graph.edges).id((d) => d.id).distance(120))
            .force('charge', d3.forceManyBody().strength(-320))
            .force('center', d3.forceCenter(width / 2, height / 2))
            .force('collide', d3.forceCollide().radius(28))

        // 边（path 支持曲线与自环）
        const link = root
            .append('g')
            .attr('fill', 'none')
            .attr('stroke', 'rgba(100,116,139,0.35)')
            .attr('stroke-width', 1.2)
            .selectAll('path')
            .data(graph.edges)
            .join('path')
            .style('cursor', 'pointer')
            .on('click', (event, d) => {
                event.stopPropagation()
                setSelected({ kind: 'edge', data: d })
            })

        // 边标签（含白色背景矩形）
        const edgeLabelG = root.append('g').style('display', showEdgeLabels ? null : 'none')
        const edgeLabel = edgeLabelG.selectAll('g').data(graph.edges).join('g')
        edgeLabel.append('rect').attr('fill', 'rgba(255,255,255,0.85)').attr('rx', 3)
        const edgeLabelText = edgeLabel
            .append('text')
            .text((d) => d.name)
            .attr('fill', '#64748b')
            .attr('font-size', 9)
            .attr('text-anchor', 'middle')
            .attr('dy', '0.32em')
        edgeLabelText.each(function () {
            const bbox = this.getBBox()
            const rect = this.previousSibling
            d3.select(rect)
                .attr('x', bbox.x - 3)
                .attr('y', bbox.y - 1)
                .attr('width', bbox.width + 6)
                .attr('height', bbox.height + 2)
        })

        // 节点
        const node = root
            .append('g')
            .selectAll('g')
            .data(graph.nodes)
            .join('g')
            .style('cursor', 'pointer')
            .on('click', (event, d) => {
                event.stopPropagation()
                setSelected({ kind: 'node', data: d })
            })
            .call(
                d3
                    .drag()
                    .on('start', (event, d) => {
                        if (!event.active) simulation.alphaTarget(0.3).restart()
                        d.fx = d.x
                        d.fy = d.y
                    })
                    .on('drag', (event, d) => {
                        d.fx = event.x
                        d.fy = event.y
                    })
                    .on('end', (event, d) => {
                        if (!event.active) simulation.alphaTarget(0)
                        d.fx = null
                        d.fy = null
                    })
            )

        node
            .append('circle')
            .attr('r', 11)
            .attr('fill', (d) => color(d.type))
            .attr('stroke', '#ffffff')
            .attr('stroke-width', 2)

        node
            .append('text')
            .text((d) => d.name)
            .attr('x', 15)
            .attr('y', 4)
            .attr('fill', '#334155')
            .attr('font-size', 11)

        // 边路径（自环 + 多重边曲线）
        const linkPath = (d) => {
            const x1 = d.source.x
            const y1 = d.source.y
            const x2 = d.target.x
            const y2 = d.target.y
            const key = [d.source.id, d.target.id].sort().join('--')
            if (d.source.id === d.target.id) {
                const r = 24
                return `M${x1},${y1} C${x1 - r * 2},${y1 - r * 2} ${x1 + r * 2},${y1 - r * 2} ${x1},${y1}`
            }
            const total = pairCount[key]
            if (total > 1) {
                pairIndex[key] = (pairIndex[key] || 0) + 1
                const idx = pairIndex[key]
                const dx = x2 - x1
                const dy = y2 - y1
                const dr = Math.sqrt(dx * dx + dy * dy) * (1.5 / idx)
                return `M${x1},${y1} A${dr},${dr} 0 0,1 ${x2},${y2}`
            }
            return `M${x1},${y1} L${x2},${y2}`
        }

        simulation.on('tick', () => {
            Object.keys(pairIndex).forEach((k) => (pairIndex[k] = 0))
            link.attr('d', linkPath)
            node.attr('transform', (d) => `translate(${d.x},${d.y})`)
            edgeLabel.attr('transform', (d) => {
                const mx = (d.source.x + d.target.x) / 2
                const my = (d.source.y + d.target.y) / 2
                return `translate(${mx},${my})`
            })
        })

        svg.on('click', () => setSelected(null))
        return () => simulation.stop()
    }, [graph, color, showEdgeLabels])

    const enterFullscreen = () => {
        const el = wrapRef.current
        if (el?.requestFullscreen) el.requestFullscreen()
    }

    const types = Array.from(new Set(graph.nodes.map((n) => n.type)))

    return (
        <div
            ref={wrapRef}
            className="relative h-full w-full overflow-hidden bg-white"
            style={{
                backgroundImage: 'radial-gradient(#e5e7eb 1px, transparent 1px)',
                backgroundSize: '18px 18px',
            }}
        >
            {/* 标题 */}
            <div className="pointer-events-none absolute left-5 top-4 z-10 text-sm font-medium text-neutral-700">
                {t('process.graphTitle')}
            </div>

            {/* 右上：Refresh + 全屏 */}
            <div className="absolute right-4 top-4 z-10 flex items-center gap-2">
                <button
                    type="button"
                    onClick={onRefresh}
                    className="flex items-center gap-1.5 rounded-lg border border-neutral-200 bg-white px-3 py-1.5 text-sm text-neutral-600 shadow-sm transition hover:bg-neutral-50"
                >
                    <span>↻</span>
                    {t('process.refresh')}
                </button>
                <button
                    type="button"
                    onClick={enterFullscreen}
                    aria-label="Fullscreen"
                    className="flex h-8 w-8 items-center justify-center rounded-lg border border-neutral-200 bg-white text-neutral-500 shadow-sm transition hover:bg-neutral-50"
                >
                    ⛶
                </button>
            </div>

            {/* Show Edge Labels 开关 */}
            <button
                type="button"
                onClick={() => setShowEdgeLabels((v) => !v)}
                className="absolute right-4 top-14 z-10 flex items-center gap-2 rounded-full border border-neutral-200 bg-white px-3 py-1.5 text-sm text-neutral-600 shadow-sm"
            >
                <span
                    className={`relative inline-block h-5 w-9 rounded-full transition ${showEdgeLabels ? 'bg-violet-500' : 'bg-neutral-300'
                        }`}
                >
                    <span
                        className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all ${showEdgeLabels ? 'left-[18px]' : 'left-0.5'
                            }`}
                    />
                </span>
                {t('process.showEdgeLabels')}
            </button>

            {loading && (
                <div className="absolute inset-0 z-10 flex items-center justify-center text-neutral-400">
                    …
                </div>
            )}
            {!loading && !graph.nodes.length && (
                <div className="absolute inset-0 z-10 flex items-center justify-center text-neutral-400">
                    {t('process.noGraphData')}
                </div>
            )}

            <svg ref={svgRef} className="h-full w-full" />

            {/* 图例 */}
            {types.length > 0 && (
                <div className="absolute bottom-4 left-4 z-10 max-w-[45%] rounded-xl border border-neutral-200 bg-white/95 p-3 text-xs shadow-sm">
                    <div className="mb-2 font-semibold tracking-wide text-neutral-700">
                        {t('process.entityTypes')}
                    </div>
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                        {types.map((type) => (
                            <div key={type} className="flex items-center gap-2">
                                <span
                                    className="inline-block h-2.5 w-2.5 rounded-full"
                                    style={{ background: color(type) }}
                                />
                                <span className="text-neutral-600">{type}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* 记忆更新提示药丸 */}
            {memoryLabel && (
                <div className="absolute bottom-5 left-1/2 z-10 -translate-x-1/2 rounded-full bg-neutral-900/90 px-4 py-2 text-xs font-medium text-white shadow-lg">
                    {memoryLabel}
                </div>
            )}

            {/* 详情面板 */}
            {selected && (
                <div className="absolute right-4 top-28 z-10 max-h-[68%] w-72 overflow-auto rounded-xl border border-neutral-200 bg-white p-4 text-sm shadow-md">
                    <div className="mb-2 font-medium text-neutral-800">
                        {selected.kind === 'node' ? t('process.nodeDetail') : t('process.edgeDetail')}
                    </div>
                    {selected.kind === 'node' ? (
                        <>
                            <p className="font-semibold text-neutral-800">{selected.data.name}</p>
                            <p className="mb-2 text-xs text-neutral-400">{selected.data.type}</p>
                            {detailLoading && (
                                <p className="text-xs text-neutral-400">{t('common.loading')}</p>
                            )}
                            {detail?.node?.summary && (
                                <p className="mb-2 text-xs leading-relaxed text-neutral-600">
                                    {detail.node.summary}
                                </p>
                            )}
                            {detail?.edges?.length > 0 && (
                                <div className="mt-2 border-t border-neutral-100 pt-2">
                                    <div className="mb-1 text-xs font-semibold text-neutral-500">
                                        {t('process.relatedFacts')} ({detail.edges.length})
                                    </div>
                                    <ul className="space-y-1">
                                        {detail.edges.slice(0, 10).map((e, i) => (
                                            <li key={i} className="text-xs leading-relaxed text-neutral-600">
                                                · {e.fact || e.name}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                        </>
                    ) : (
                        <>
                            <p className="text-neutral-700">{selected.data.name || '—'}</p>
                            {selected.data.raw?.fact && (
                                <p className="mt-2 text-xs leading-relaxed text-neutral-500">{selected.data.raw.fact}</p>
                            )}
                        </>
                    )}
                </div>
            )}
        </div>
    )
}
