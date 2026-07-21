import { useEffect, useMemo, useRef, useState } from 'react'
import * as d3 from 'd3'

// 10 色调色板：按实体类型着色
const COLOR_PALETTE = [
    '#60a5fa', '#f472b6', '#34d399', '#fbbf24', '#a78bfa',
    '#f87171', '#22d3ee', '#fb923c', '#4ade80', '#e879f9',
]

/**
 * GraphPanel —— D3 力导向知识图谱可视化（核心组件）
 *
 * 特性：
 * - forceSimulation + forceManyBody + forceCenter + forceLink 布局
 * - 节点按实体类型着色（10 色），支持拖拽与缩放
 * - 支持自环边（self-loop）与多重边曲线偏移
 * - 边标签可开关，带背景矩形避免与连线重叠
 * - 点击节点/边展示详情面板；动态生成图例
 *
 * @param {Object}  data        { nodes: [...], edges: [...] }
 * @param {boolean} loading     是否加载中
 * @param {string}  statusText  顶部状态提示（构建中/模拟中/完成）
 */
export default function GraphPanel({ data, loading = false, statusText = '' }) {
    const svgRef = useRef(null)
    const wrapRef = useRef(null)
    const [selected, setSelected] = useState(null) // 选中的节点或边
    const [showEdgeLabels, setShowEdgeLabels] = useState(true)

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
        svg.selectAll('*').remove() // 清理旧内容
        svg.attr('viewBox', [0, 0, width, height])

        const root = svg.append('g')

        // 缩放与平移
        const zoom = d3
            .zoom()
            .scaleExtent([0.2, 4])
            .on('zoom', (event) => root.attr('transform', event.transform))
        svg.call(zoom)

        // 统计相同 source-target 之间的边数量，用于多重边曲线偏移
        const pairCount = {}
        graph.edges.forEach((e) => {
            const key = [e.source, e.target].sort().join('--')
            pairCount[key] = (pairCount[key] || 0) + 1
        })
        const pairIndex = {}

        // 力导向仿真
        const simulation = d3
            .forceSimulation(graph.nodes)
            .force(
                'link',
                d3
                    .forceLink(graph.edges)
                    .id((d) => d.id)
                    .distance(120)
            )
            .force('charge', d3.forceManyBody().strength(-320))
            .force('center', d3.forceCenter(width / 2, height / 2))
            .force('collide', d3.forceCollide().radius(28))

        // 边（使用 path 以支持曲线与自环）
        const link = root
            .append('g')
            .attr('fill', 'none')
            .attr('stroke', 'rgba(255,255,255,0.25)')
            .attr('stroke-width', 1.4)
            .selectAll('path')
            .data(graph.edges)
            .join('path')
            .style('cursor', 'pointer')
            .on('click', (event, d) => {
                event.stopPropagation()
                setSelected({ kind: 'edge', data: d })
            })

        // 边标签（含背景矩形）
        const edgeLabelG = root.append('g').style('display', showEdgeLabels ? null : 'none')
        const edgeLabel = edgeLabelG
            .selectAll('g')
            .data(graph.edges)
            .join('g')
        edgeLabel
            .append('rect')
            .attr('fill', 'rgba(0,0,0,0.6)')
            .attr('rx', 3)
        const edgeLabelText = edgeLabel
            .append('text')
            .text((d) => d.name)
            .attr('fill', '#cbd5e1')
            .attr('font-size', 10)
            .attr('text-anchor', 'middle')
            .attr('dy', '0.32em')
        // 根据文字宽度调整背景矩形
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
            .attr('r', 12)
            .attr('fill', (d) => color(d.type))
            .attr('stroke', '#0b0b0f')
            .attr('stroke-width', 1.5)

        node
            .append('text')
            .text((d) => d.name)
            .attr('x', 16)
            .attr('y', 4)
            .attr('fill', '#e5e7eb')
            .attr('font-size', 11)

        // 计算边路径（自环 + 多重边曲线偏移）
        const linkPath = (d) => {
            const x1 = d.source.x
            const y1 = d.source.y
            const x2 = d.target.x
            const y2 = d.target.y
            const key = [d.source.id, d.target.id].sort().join('--')
            if (d.source.id === d.target.id) {
                // 自环
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

        // 每帧更新位置
        simulation.on('tick', () => {
            // 重置多重边索引
            Object.keys(pairIndex).forEach((k) => (pairIndex[k] = 0))
            link.attr('d', linkPath)
            node.attr('transform', (d) => `translate(${d.x},${d.y})`)
            edgeLabel.attr('transform', (d) => {
                const mx = (d.source.x + d.target.x) / 2
                const my = (d.source.y + d.target.y) / 2
                return `translate(${mx},${my})`
            })
        })

        // 点击空白处取消选中
        svg.on('click', () => setSelected(null))

        return () => simulation.stop()
    }, [graph, color, showEdgeLabels])

    return (
        <div className="relative" ref={wrapRef}>
            {/* 顶部状态与控制条 */}
            <div className="mb-3 flex items-center justify-between">
                <span className="text-sm text-gray-400">{statusText}</span>
                <button
                    type="button"
                    onClick={() => setShowEdgeLabels((v) => !v)}
                    className="liquid-glass rounded-lg px-3 py-1.5 text-xs text-gray-200"
                >
                    {showEdgeLabels ? '隐藏边标签' : '显示边标签'}
                </button>
            </div>

            <div className="relative h-[520px] w-full overflow-hidden rounded-xl border border-white/10 bg-black/40">
                {loading && (
                    <div className="absolute inset-0 z-10 flex items-center justify-center text-gray-400">
                        加载中……
                    </div>
                )}
                {!loading && !graph.nodes.length && (
                    <div className="absolute inset-0 z-10 flex items-center justify-center text-gray-500">
                        暂无图谱数据
                    </div>
                )}
                <svg ref={svgRef} className="h-full w-full" />

                {/* 图例：动态生成 */}
                {graph.nodes.length > 0 && (
                    <div className="liquid-glass absolute left-3 top-3 max-w-[40%] rounded-lg p-3 text-xs">
                        {Array.from(new Set(graph.nodes.map((n) => n.type))).map((type) => (
                            <div key={type} className="mb-1 flex items-center gap-2">
                                <span
                                    className="inline-block h-3 w-3 rounded-full"
                                    style={{ background: color(type) }}
                                />
                                <span className="text-gray-300">{type}</span>
                            </div>
                        ))}
                    </div>
                )}

                {/* 详情面板 */}
                {selected && (
                    <div className="liquid-glass absolute right-3 top-3 w-64 rounded-lg p-4 text-sm">
                        <div className="mb-2 font-medium text-white">
                            {selected.kind === 'node' ? '节点详情' : '关系详情'}
                        </div>
                        {selected.kind === 'node' ? (
                            <>
                                <p className="text-gray-300">
                                    名称：{selected.data.name}
                                </p>
                                <p className="text-gray-400">类型：{selected.data.type}</p>
                            </>
                        ) : (
                            <p className="text-gray-300">关系：{selected.data.name || '—'}</p>
                        )}
                    </div>
                )}
            </div>
        </div>
    )
}
