"""Zep 检索工具集（供 ReportAgent 使用）。

提供三种检索能力：
- QuickSearch     快速检索（简单事实查询）
- PanoramaSearch  广度搜索（含历史/过期内容，覆盖全局上下文）
- InsightForge    深度洞察（自动分解子问题，聚合多维度信息）
"""

from ..utils.llm_client import get_llm_client
from ..utils.logger import get_logger
from ..utils.retry import retry

logger = get_logger("zep_tools")


def _get_zep():
    from .graph_builder import _get_zep as _zep

    return _zep()


def _format_results(res) -> list[dict]:
    """将 Zep 搜索结果规整为简单字典列表。"""
    items = []
    edges = getattr(res, "edges", None) or []
    nodes = getattr(res, "nodes", None) or []
    for e in edges:
        items.append({"type": "fact", "text": getattr(e, "fact", "") or getattr(e, "name", "")})
    for n in nodes:
        items.append({"type": "entity", "text": getattr(n, "summary", "") or getattr(n, "name", "")})
    return items


@retry(max_attempts=3)
def quick_search(graph_id: str, query: str, limit: int = 5) -> list[dict]:
    """快速检索：面向简单事实查询。"""
    zep = _get_zep()
    res = zep.graph.search(graph_id=graph_id, query=query, limit=limit, scope="edges")
    return _format_results(res)


@retry(max_attempts=3)
def panorama_search(graph_id: str, query: str, limit: int = 20) -> list[dict]:
    """广度搜索：覆盖全局上下文，包含历史/过期内容。"""
    zep = _get_zep()
    res = zep.graph.search(
        graph_id=graph_id, query=query, limit=limit, scope="edges"
    )
    return _format_results(res)


def insight_forge(graph_id: str, question: str) -> list[dict]:
    """深度洞察：先用 LLM 将问题分解为子问题，再逐一检索并聚合。"""
    client = get_llm_client()
    try:
        decomposed = client.chat_json(
            [
                {
                    "role": "system",
                    "content": "将用户问题分解为 2-4 个便于检索的子问题，输出 JSON：{\"sub_questions\":[\"...\"]}",
                },
                {"role": "user", "content": question},
            ]
        )
        sub_questions = decomposed.get("sub_questions") or [question]
    except Exception:  # noqa: BLE001
        sub_questions = [question]

    aggregated = []
    for sq in sub_questions[:4]:
        aggregated.append({"question": sq, "results": quick_search(graph_id, sq, limit=5)})
    return aggregated
