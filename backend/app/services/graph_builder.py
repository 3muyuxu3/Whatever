"""知识图谱构建服务（Zep Graph）。

基于本体定义，在 Zep Cloud 中创建 Standalone Graph，分块分批写入文本，
并在处理完成后读取完整图谱数据。所有 Zep 调用均惰性导入并带重试。
"""

from ..config import config
from ..utils.logger import get_logger
from ..utils.retry import retry
from .text_processor import chunk_text

logger = get_logger("graph_builder")

# 分批写入 Zep 的批大小
BATCH_SIZE = 3


def _get_zep():
    """惰性创建 Zep 客户端。"""
    if not config.has_zep():
        raise RuntimeError("Zep 未配置（缺少 ZEP_API_KEY）")
    from zep_cloud.client import Zep  # 惰性导入，避免无依赖时无法启动

    return Zep(api_key=config.ZEP_API_KEY)


@retry(max_attempts=3)
def _add_text(zep, graph_id: str, text: str) -> None:
    """向图谱追加一段文本（带重试）。"""
    zep.graph.add(graph_id=graph_id, type="text", data=text)


def _apply_ontology(zep, graph_id: str, ontology: dict) -> None:
    """根据本体定义为图谱设置实体/边类型（不同 SDK 版本 API 可能略有差异）。"""
    try:
        from zep_cloud.external_clients.ontology import EntityModel, EdgeModel

        entity_models = {}
        for et in ontology.get("entity_types", []):
            name = et.get("name")
            if name:
                entity_models[name] = type(name, (EntityModel,), {})
        edge_models = {}
        for edg in ontology.get("edge_types", []):
            name = edg.get("name")
            if name:
                edge_models[name] = type(name, (EdgeModel,), {})
        zep.graph.set_ontology(
            graph_ids=[graph_id],
            entities=entity_models,
            edges=edge_models,
        )
    except Exception as e:  # noqa: BLE001
        # 本体设置失败不阻断构建（Zep 仍可用默认 Entity 抽取）
        logger.warning("设置本体失败（忽略）：%s", e)


def build_graph(project, text: str, on_progress=None) -> str:
    """在 Zep 中构建知识图谱，返回 graph_id。

    :param project:     Project 对象（含 ontology）
    :param text:        文档全文
    :param on_progress: 进度回调 (percent: int) -> None
    """
    zep = _get_zep()

    # 1) 创建 standalone graph
    graph = zep.graph.create(
        name=(project.name or project.id)[:80],
        description=(project.requirement or "")[:200],
    )
    graph_id = getattr(graph, "graph_id", None) or getattr(graph, "id", None)
    logger.info("已创建 Zep 图谱：%s", graph_id)
    if on_progress:
        on_progress(10)

    # 2) 设置本体
    _apply_ontology(zep, graph_id, project.ontology or {})
    if on_progress:
        on_progress(20)

    # 3) 分块并分批写入
    chunks = chunk_text(text)
    total = max(1, len(chunks))
    for i in range(0, len(chunks), BATCH_SIZE):
        for chunk in chunks[i : i + BATCH_SIZE]:
            _add_text(zep, graph_id, chunk)
        done = min(i + BATCH_SIZE, total)
        if on_progress:
            on_progress(20 + int(70 * done / total))

    if on_progress:
        on_progress(95)
    return graph_id


def _as_list(result):
    """兼容 Zep 返回对象或列表。"""
    if result is None:
        return []
    if isinstance(result, list):
        return result
    for attr in ("nodes", "edges", "data", "results"):
        if hasattr(result, attr):
            return getattr(result, attr) or []
    return list(result) if hasattr(result, "__iter__") else [result]


def _node_to_dict(n) -> dict:
    return {
        "uuid": getattr(n, "uuid", None) or getattr(n, "id", None),
        "name": getattr(n, "name", "") or "",
        "labels": getattr(n, "labels", None) or [],
        "summary": getattr(n, "summary", "") or "",
    }


def _edge_to_dict(e) -> dict:
    return {
        "uuid": getattr(e, "uuid", None) or getattr(e, "id", None),
        "name": getattr(e, "name", "") or getattr(e, "type", "") or "",
        "source": getattr(e, "source_node_uuid", None),
        "target": getattr(e, "target_node_uuid", None),
        "fact": getattr(e, "fact", "") or "",
    }


def get_graph_data(graph_id: str) -> dict:
    """读取图谱的全部节点与边，返回前端可用结构。"""
    zep = _get_zep()
    from ..utils.zep_paging import paginate

    def fetch_nodes(cursor, size):
        res = zep.graph.node.get_by_graph_id(graph_id, limit=size, uuid_cursor=cursor)
        items = _as_list(res)
        next_cursor = items[-1].uuid if items and len(items) == size else None
        return items, next_cursor

    def fetch_edges(cursor, size):
        res = zep.graph.edge.get_by_graph_id(graph_id, limit=size, uuid_cursor=cursor)
        items = _as_list(res)
        next_cursor = items[-1].uuid if items and len(items) == size else None
        return items, next_cursor

    nodes = paginate(fetch_nodes)
    edges = paginate(fetch_edges)
    return {
        "graph_id": graph_id,
        "nodes": [_node_to_dict(n) for n in nodes],
        "edges": [_edge_to_dict(e) for e in edges],
    }
