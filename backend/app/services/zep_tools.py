"""图谱检索工具集（供 ReportAgent 使用）。

：优先调用**真实的 Zep 语义搜索**（graph.search，混合语义 + BM25 + cross_encoder 重排），
在 Zep 不可用 / 限流 / 无结果时降级为本地内存关键词检索（复用 graph_builder 的 15s 缓存），
保证端到端始终可用且不至于打满 Zep FREE 计划配额。

三种检索工具：
- QuickSearch     快速检索：直接 Zep 语义搜索（面向事实/边）
- PanoramaSearch  广度全景：读取全图节点+边（缓存），分类当前/历史事实
- InsightForge    深度洞察：LLM 分解子问题 -> 逐个 Zep 语义搜索 -> 聚合事实/实体/关系链
"""

import re

from ..config import config
from ..utils.llm_client import get_llm_client
from ..utils.logger import get_logger

logger = get_logger("zep_tools")

# 单次深度洞察的最大子问题数（ 的分解式检索，控制 Zep 请求量）
MAX_SUB_QUERIES = 3


# ═══════════════════ 本地图谱读取与关键词检索（降级方案） ═══════════════════

def _load_graph(graph_id: str):
    """读取图谱数据（带缓存），返回 (nodes, edges)。失败/不可用时返回空。"""
    try:
        from .graph_builder import get_graph_data

        data = get_graph_data(graph_id)
        return data.get("nodes", []) or [], data.get("edges", []) or []
    except Exception as e:  # noqa: BLE001
        logger.warning("读取图谱数据失败（检索降级为空）：%s", e)
        return [], []


def _terms(query: str) -> list[str]:
    """从查询中切出关键词（长度 ≥ 2，兼容中英文标点）。"""
    parts = re.split(r"[\s,，。、；;:：!！?？（）()\[\]【】\"'“”\-—/\\]+", query or "")
    return [p for p in parts if len(p) >= 2]


def _score(text: str, terms: list[str]) -> int:
    if not text:
        return 0
    if not terms:
        return 1
    low = text.lower()
    return sum(1 for w in terms if w.lower() in low)


def _is_historical(edge: dict) -> bool:
    """判定一条边（事实）是否已失效/过期（带 invalid_at 或 expired_at），用于区分当前/历史事实。"""
    return bool(edge.get("expired_at") or edge.get("invalid_at"))


def _node_type(node: dict) -> str:
    for lb in (node.get("labels") or []):
        if lb not in ("Entity", "Node"):
            return lb
    return "实体"


def _entity_text(node: dict) -> str:
    """实体文本：名称（类型）：摘要 [属性]。"""
    name = node.get("name") or ""
    summary = (node.get("summary") or "").strip()
    base = f"{name}（{_node_type(node)}）"
    if summary:
        base += f"：{summary}"
    attrs = node.get("attributes") or {}
    kvs = [f"{k}: {v}" for k, v in attrs.items()
           if v not in (None, "", [], {})]
    if kvs:
        base += f" [{'; '.join(kvs[:5])}]"
    return base


def _search_facts(edges: list[dict], terms: list[str], limit: int) -> list[dict]:
    """检索事实（边）。"""
    scored = []
    for e in edges:
        text = (e.get("fact") or e.get("name") or "").strip()
        if text:
            scored.append(
                (_score(text, terms), {"type": "fact", "text": text}))
    scored.sort(key=lambda x: -x[0])
    matched = [it for s, it in scored if s > 0]
    return (matched or [it for _, it in scored])[:limit]


def _search_entities(nodes: list[dict], terms: list[str], limit: int) -> list[dict]:
    """检索实体（节点），文本含属性摘要。"""
    scored = []
    for n in nodes:
        if not (set(n.get("labels") or []) - {"Entity", "Node"}):
            continue  # 跳过未分类节点
        text = _entity_text(n)
        blob = f"{n.get('name', '')} {n.get('summary', '')}"
        scored.append((_score(blob, terms), {"type": "entity", "text": text}))
    scored.sort(key=lambda x: -x[0])
    matched = [it for s, it in scored if s > 0]
    return (matched or [it for _, it in scored])[:limit]


def _relationship_chains(edges: list[dict], nodes: list[dict],
                         terms: list[str], limit: int) -> list[dict]:
    """构建关系链：源名 --[关系]--> 目标名。"""
    name_map = {n.get("uuid"): (n.get("name") or "?") for n in nodes}
    scored = []
    for e in edges:
        src = name_map.get(e.get("source"), "?")
        tgt = name_map.get(e.get("target"), "?")
        rel = e.get("name") or ""
        if src == "?" and tgt == "?":
            continue
        chain = f"{src} --[{rel}]--> {tgt}"
        blob = f"{chain} {e.get('fact', '')}"
        scored.append((_score(blob, terms), {"type": "chain", "text": chain}))
    scored.sort(key=lambda x: -x[0])
    matched = [it for s, it in scored if s > 0]
    # 关系链去重
    seen, out = set(), []
    for it in (matched or [it for _, it in scored]):
        if it["text"] in seen:
            continue
        seen.add(it["text"])
        out.append(it)
        if len(out) >= limit:
            break
    return out


# ═══════════════════ 真实 Zep 语义搜索 ═══════════════════

def _search_zep(graph_id: str, query: str, scope: str, limit: int):
    """调用真实 Zep 语义搜索（graph.search），返回 (facts, edges, nodes)。

    facts: list[str]；edges/nodes: list[dict]。失败/不可用时抛出异常，由调用方降级。
    """
    from .graph_builder import _get_zep, zep_call

    zep = _get_zep()  # 未配置 Zep 时抛 ZepUnavailable

    def _do(**extra):
        return zep.graph.search(graph_id=graph_id, query=query,
                                limit=limit, scope=scope, **extra)

    try:
        res = zep_call(_do, reranker="cross_encoder")
    except TypeError:
        # 兼容不支持 reranker 参数的 SDK 版本
        res = zep_call(_do)

    facts: list[str] = []
    edges: list[dict] = []
    nodes: list[dict] = []
    for edge in (getattr(res, "edges", None) or []):
        fact = (getattr(edge, "fact", "") or "").strip()
        if fact:
            facts.append(fact)
        edges.append({
            "uuid": getattr(edge, "uuid_", None) or getattr(edge, "uuid", ""),
            "name": getattr(edge, "name", "") or "",
            "fact": fact,
            "source": getattr(edge, "source_node_uuid", "") or "",
            "target": getattr(edge, "target_node_uuid", "") or "",
            "invalid_at": getattr(edge, "invalid_at", None),
            "expired_at": getattr(edge, "expired_at", None),
        })
    for node in (getattr(res, "nodes", None) or []):
        name = getattr(node, "name", "") or ""
        summary = (getattr(node, "summary", "") or "").strip()
        labels = getattr(node, "labels", None) or []
        nodes.append({
            "uuid": getattr(node, "uuid_", None) or getattr(node, "uuid", ""),
            "name": name,
            "summary": summary,
            "labels": labels,
        })
        if summary:
            facts.append(f"[{name}]：{summary}")
    return facts, edges, nodes


def _gen_sub_queries(question: str) -> list[str]:
    """用 LLM 将复杂问题分解为多个可独立检索的子问题（ InsightForge）。"""
    if not config.has_llm():
        return []
    try:
        # 子问题分解为高频轻量调用，优先走加速模型（未配置时自动回落主模型）
        client = get_llm_client(boost=True)
        data = client.chat_json(
            [
                {"role": "system", "content": (
                    "你是问题分析专家。将复杂问题分解为多个可在模拟世界中独立检索的子问题，"
                    "覆盖不同维度（谁/什么/为什么/如何/影响）。"
                    '仅输出 JSON：{"sub_queries":["子问题1","子问题2"]}')},
                {"role": "user", "content": (
                    f"请将以下问题分解为最多 {MAX_SUB_QUERIES} 个子问题：\n{question}")},
            ],
            temperature=0.3,
        )
        subs = [str(s).strip()
                for s in (data.get("sub_queries") or []) if str(s).strip()]
        return subs[:MAX_SUB_QUERIES]
    except Exception as e:  # noqa: BLE001
        logger.info("子问题分解失败（跳过）：%s", e)
        return []


def _insight_from_zep(graph_id: str, question: str) -> list[dict]:
    """深度洞察（真实 Zep）：子问题分解 + 逐个语义搜索 + 聚合事实/实体/关系链。"""
    subs = _gen_sub_queries(question)
    seen_facts: set[str] = set()
    facts: list[str] = []
    all_edges: list[dict] = []
    for q in [*subs, question]:
        f, e, _ = _search_zep(graph_id, q, "edges", 15)
        for x in f:
            if x not in seen_facts:
                seen_facts.add(x)
                facts.append(x)
        all_edges.extend(e)

    if not facts and not all_edges:
        raise RuntimeError("Zep 深度检索无结果")

    # 复用缓存图谱数据构建 uuid -> 名称/摘要 映射（供实体洞察与关系链，零额外 Zep）
    nodes, _ = _load_graph(graph_id)
    name_map = {n.get("uuid"): n for n in nodes}

    results: list[dict] = [{"type": "fact", "text": f} for f in facts[:20]]

    # 实体洞察：从命中边的端点提取实体
    entity_uuids: list[str] = []
    for e in all_edges:
        for uid in (e.get("source"), e.get("target")):
            if uid and uid not in entity_uuids:
                entity_uuids.append(uid)
    for uid in entity_uuids[:8]:
        n = name_map.get(uid)
        if n:
            results.append({"type": "entity", "text": _entity_text(n)})

    # 关系链
    chain_seen: set[str] = set()
    for e in all_edges:
        src = (name_map.get(e.get("source")) or {}).get("name") or "?"
        tgt = (name_map.get(e.get("target")) or {}).get("name") or "?"
        rel = e.get("name") or ""
        if src == "?" and tgt == "?":
            continue
        chain = f"{src} --[{rel}]--> {tgt}"
        if chain not in chain_seen:
            chain_seen.add(chain)
            results.append({"type": "chain", "text": chain})
        if len(chain_seen) >= 8:
            break
    return results


# ═══════════════════ 对外工具（真实 Zep 优先，本地降级） ═══════════════════

def quick_search(graph_id: str, query: str, limit: int = 5) -> list[dict]:
    """快速检索：优先真实 Zep 语义搜索（面向事实/边），失败降级本地关键词匹配。"""
    try:
        facts, _edges, _nodes = _search_zep(
            graph_id, query, "edges", max(limit, 10))
        items = [{"type": "fact", "text": f} for f in facts[:limit] if f]
        if items:
            return items
    except Exception as e:  # noqa: BLE001
        logger.info("Zep 快速检索不可用，降级本地：%s", e)
    _nodes, edges = _load_graph(graph_id)
    return _search_facts(edges, _terms(query), limit)


def panorama_search(graph_id: str, query: str, limit: int = 20) -> list[dict]:
    """广度全景：读取全图（缓存）覆盖事实（边）与实体（节点），并区分「当前有效」与「历史/已失效」事实。

    ：利用 Zep 边的时序字段（invalid_at/expired_at），让报告能描述观点/关系
    随模拟推进的演变过程（而非静态快照）。复用 15s 缓存，避免全景检索打满 Zep 配额。
    """
    nodes, edges = _load_graph(graph_id)
    terms = _terms(query)
    # 全部边按相关性排序
    scored = []
    for e in edges:
        text = (e.get("fact") or e.get("name") or "").strip()
        if text:
            scored.append((_score(text, terms), e, text))
    scored.sort(key=lambda x: -x[0])
    matched = [(e, txt) for s, e, txt in scored if s > 0] or [
        (e, txt) for _, e, txt in scored]
    # 分流：当前有效 vs 历史/已失效
    active: list[dict] = []
    historical: list[dict] = []
    for e, txt in matched:
        if _is_historical(e):
            historical.append({"type": "historical_fact", "text": txt})
        else:
            active.append({"type": "fact", "text": txt})
    entities = _search_entities(nodes, terms, max(5, limit // 2))
    # 当前有效优先 -> 实体 -> 历史事实（供 LLM 对比演变）
    return active[:limit] + entities + historical[:max(5, limit // 2)]


def insight_forge(graph_id: str, question: str) -> list[dict]:
    """深度洞察：优先真实 Zep（LLM 子问题分解 + 语义搜索 + 实体/关系链），失败降级本地聚合。"""
    try:
        results = _insight_from_zep(graph_id, question)
        if results:
            return [{"question": question, "results": results}]
    except Exception as e:  # noqa: BLE001
        logger.info("Zep 深度洞察不可用，降级本地：%s", e)
    nodes, edges = _load_graph(graph_id)
    terms = _terms(question)
    results = (
        _search_facts(edges, terms, 10)
        + _search_entities(nodes, terms, 6)
        + _relationship_chains(edges, nodes, terms, 8)
    )
    return [{"question": question, "results": results}]
