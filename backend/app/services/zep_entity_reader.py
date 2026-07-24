"""Zep 实体读取与过滤。

从 Zep 图谱读取全部节点与边，过滤出符合预定义实体类型的节点
（排除只带默认 Entity 标签的节点），并附带每个实体的关联边与关联节点信息。

 的实体上下文丰富度（边方向标注 + 关联节点摘要），
全部基于 graph_builder.get_graph_data 的 15s 缓存数据构建，**零额外 Zep 请求**。
"""

from ..utils.logger import get_logger
from .graph_builder import get_graph_data

logger = get_logger("zep_entity_reader")

# 默认标签：仅带这些标签的节点视为「未被具体分类」，需要排除
DEFAULT_LABELS = {"Entity", "Node"}


def _specific_labels(node: dict) -> set:
    """取节点的具体类型标签（排除默认标签）。"""
    return set(node.get("labels") or []) - DEFAULT_LABELS


def _build_edge_index(edges: list[dict]) -> dict[str, list[dict]]:
    """预建 node_uuid -> 相关边列表 的索引。

    避免 read_entities 对每个节点都全量扫描所有边（整体复杂度由 O(N×E) 降为 O(N+E)）。
    自环边只登记一次，避免同一节点关联边重复。
    """
    index: dict[str, list[dict]] = {}
    for e in edges:
        src, tgt = e.get("source"), e.get("target")
        if src:
            index.setdefault(src, []).append(e)
        if tgt and tgt != src:
            index.setdefault(tgt, []).append(e)
    return index


def _collect_related(node_uuid: str, edges: list[dict], node_map: dict):
    """收集与某节点相关的边（含方向）与关联节点（去重）。"""
    related_edges = []
    related_uuids = set()
    for e in edges:
        src, tgt = e.get("source"), e.get("target")
        if src == node_uuid:
            related_edges.append({
                "direction": "outgoing",
                "edge_name": e.get("name", ""),
                "name": e.get("name", ""),
                "fact": e.get("fact", ""),
                "source": src,
                "target": tgt,
                "target_node_uuid": tgt,
            })
            if tgt:
                related_uuids.add(tgt)
        elif tgt == node_uuid:
            related_edges.append({
                "direction": "incoming",
                "edge_name": e.get("name", ""),
                "name": e.get("name", ""),
                "fact": e.get("fact", ""),
                "source": src,
                "target": tgt,
                "source_node_uuid": src,
            })
            if src:
                related_uuids.add(src)
    related_nodes = []
    for ruid in related_uuids:
        rn = node_map.get(ruid)
        if rn:
            related_nodes.append({
                "uuid": rn["uuid"],
                "name": rn.get("name", ""),
                "labels": rn.get("labels", []),
                "summary": rn.get("summary", ""),
            })
    return related_edges, related_nodes


def read_entities(graph_id: str, entity_types: list[str] | None = None,
                  use_cache: bool = True) -> list[dict]:
    """读取并过滤实体列表（附带边方向与关联节点，零额外 Zep）。

    :param graph_id:     图谱 ID
    :param entity_types: 允许的实体类型（None 表示不额外限制）
    :param use_cache:    是否使用图谱读取缓存（等待实体就绪时传 False 拉最新）
    """
    data = get_graph_data(graph_id, use_cache=use_cache)
    nodes = data["nodes"]
    edges = data["edges"]
    allowed = set(entity_types or [])
    node_map = {n["uuid"]: n for n in nodes}
    edge_index = _build_edge_index(edges)  # 预建边索引，避免逐节点全量扫描边

    result = []
    for node in nodes:
        specific = _specific_labels(node)
        if not specific:
            # 排除只有默认 Entity 标签的节点
            continue
        if allowed and not (specific & allowed):
            continue
        related_edges, related_nodes = _collect_related(
            node["uuid"], edge_index.get(node["uuid"], []), node_map)
        result.append(
            {
                "uuid": node["uuid"],
                "name": node["name"],
                "type": next(iter(specific), "Entity"),
                "labels": list(node.get("labels") or []),
                "summary": node.get("summary", ""),
                "attributes": node.get("attributes", {}) or {},
                "related_edges": related_edges,
                "related_nodes": related_nodes,
            }
        )
    logger.info("图谱 %s 过滤得到 %d 个实体", graph_id, len(result))
    return result


def get_entity_detail(graph_id: str, uuid: str) -> dict | None:
    """获取单个实体的详情（节点 + 关联边 + 关联节点）。"""
    data = get_graph_data(graph_id)
    node = next((n for n in data["nodes"] if n["uuid"] == uuid), None)
    if not node:
        return None
    node_map = {n["uuid"]: n for n in data["nodes"]}
    related_edges, related_nodes = _collect_related(
        uuid, data["edges"], node_map)
    return {"node": node, "edges": related_edges, "related_nodes": related_nodes}
