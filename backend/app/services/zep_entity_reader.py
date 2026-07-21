"""Zep 实体读取与过滤。

从 Zep 图谱读取全部节点与边，过滤出符合预定义实体类型的节点
（排除只带默认 Entity 标签的节点），并附带每个实体的关联边信息。
"""

from ..utils.logger import get_logger
from .graph_builder import get_graph_data

logger = get_logger("zep_entity_reader")

# 默认标签：仅带这些标签的节点视为「未被具体分类」，需要排除
DEFAULT_LABELS = {"Entity"}


def read_entities(graph_id: str, entity_types: list[str] | None = None) -> list[dict]:
    """读取并过滤实体列表。

    :param graph_id:     图谱 ID
    :param entity_types: 允许的实体类型（None 表示不额外限制）
    """
    data = get_graph_data(graph_id)
    nodes = data["nodes"]
    edges = data["edges"]
    allowed = set(entity_types or [])

    result = []
    for node in nodes:
        labels = set(node.get("labels") or [])
        specific = labels - DEFAULT_LABELS
        if not specific:
            # 排除只有默认 Entity 标签的节点
            continue
        if allowed and not (specific & allowed):
            continue
        # 收集与该实体相关的边
        related = [
            e
            for e in edges
            if e.get("source") == node["uuid"] or e.get("target") == node["uuid"]
        ]
        result.append(
            {
                "uuid": node["uuid"],
                "name": node["name"],
                "type": next(iter(specific), "Entity"),
                "labels": list(labels),
                "summary": node.get("summary", ""),
                "related_edges": related,
            }
        )
    logger.info("图谱 %s 过滤得到 %d 个实体", graph_id, len(result))
    return result


def get_entity_detail(graph_id: str, uuid: str) -> dict | None:
    """获取单个实体的详情（节点 + 关联边）。"""
    data = get_graph_data(graph_id)
    node = next((n for n in data["nodes"] if n["uuid"] == uuid), None)
    if not node:
        return None
    edges = [
        e
        for e in data["edges"]
        if e.get("source") == uuid or e.get("target") == uuid
    ]
    return {"node": node, "edges": edges}
