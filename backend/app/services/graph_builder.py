"""知识图谱构建服务（Zep Graph）。

基于本体定义，在 Zep Cloud 中创建 Standalone Graph，分块分批写入文本，
并在处理完成后读取完整图谱数据。所有 Zep 调用均惰性导入并带重试。
"""

import random
import re
import threading
import time
import uuid

from ..config import config
from ..utils.logger import get_logger
from .text_processor import chunk_text

logger = get_logger("graph_builder")

# 分批写入 Zep 的批大小（集中到 config 便于调优）
BATCH_SIZE = config.GRAPH_BATCH_SIZE

# Zep 数据为异步入库：graph.add 后需等待 episode.processed 为真且节点可检索，
# 否则 read_entities / search 会读到空结果（导致环境准备生成 0 个人设）。
EPISODE_WAIT_TIMEOUT = config.EPISODE_WAIT_TIMEOUT  # 等待处理完成的最长秒数
EPISODE_POLL_INTERVAL = config.EPISODE_POLL_INTERVAL  # 轮询间隔（秒）

# ---- Zep 限流保护 ----
# Zep Cloud FREE 计划限流极严（约 5 次/窗口）。建图、前端轮询图谱、
# 环境准备等多处并发读写极易触发 429。因此所有 Zep 调用均经由 zep_call：
#   1) 全局节流，相邻请求至少间隔 _ZEP_MIN_INTERVAL 秒；
#   2) 遇 429 时遵循服务端的 retry-after 等待后重试。
_ZEP_LOCK = threading.Lock()
_ZEP_MIN_INTERVAL = config.ZEP_MIN_INTERVAL  # 相邻 Zep 请求的最小间隔（秒）
_zep_last_call = 0.0

# 图谱读取短时缓存（降低前端频繁轮询带来的 Zep 读取量）；带锁 + 容量上限防内存无限增长
_GRAPH_CACHE: dict[str, tuple[float, dict]] = {}
_GRAPH_CACHE_TTL = config.GRAPH_CACHE_TTL
_GRAPH_CACHE_MAX = config.GRAPH_CACHE_MAX
_GRAPH_CACHE_LOCK = threading.Lock()


def _throttle() -> None:
    """全局节流：确保相邻 Zep 调用间隔 ≥ _ZEP_MIN_INTERVAL 秒（跨线程）。

    仅在锁内计算/预占下一次可调用时间戳，sleep 放到锁外，避免持锁阻塞其他线程。
    """
    global _zep_last_call
    with _ZEP_LOCK:
        now = time.time()
        wait = _ZEP_MIN_INTERVAL - (now - _zep_last_call)
        # 预占时间槽（锁内更新），随后锁外 sleep
        _zep_last_call = now + (wait if wait > 0 else 0.0)
    if wait > 0:
        time.sleep(wait)


def _is_rate_limit(e) -> bool:
    """判断异常是否为 Zep 限流（429）。"""
    if getattr(e, "status_code", None) == 429:
        return True
    s = str(e).lower()
    return "429" in s or "rate limit" in s


def _retry_after_seconds(e, default: float = 8.0) -> float:
    """从异常的响应头提取 retry-after（秒），取不到则用默认值。"""
    headers = getattr(e, "headers", None)
    try:
        if headers is not None and hasattr(headers, "get"):
            ra = headers.get("retry-after") or headers.get("Retry-After")
            if ra:
                return float(ra) + 0.5
    except Exception:  # noqa: BLE001
        pass
    return default


def zep_call(fn, *args, **kwargs):
    """统一的 Zep 调用入口：全局节流 + 遵循 429 retry-after 的重试。

    - 429 限流：按 retry-after 等待后重试（最多 4 次；超过则抛出，由调用方优雅降级）；
    - 其他错误：指数退避重试（最多 3 次）。
    """
    rl_retries = 0
    err_retries = 0
    while True:
        _throttle()
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            if _is_rate_limit(e):
                rl_retries += 1
                if rl_retries > 4:
                    # 多次仍限流：不再长时间阻塞，抛出交由调用方降级（返回空/跳过）
                    logger.warning("Zep 限流重试超过上限，放弃本次请求（降级处理）")
                    raise
                delay = _retry_after_seconds(e)
                # 加入拖动（≥ retry-after），避免多线程同时到点重试再次打满配额
                delay = delay * (1.0 + 0.4 * random.random())
                logger.warning("Zep 触发限流(429)，%.1fs 后重试（第 %d/4 次）",
                               delay, rl_retries)
                time.sleep(delay)
            else:
                err_retries += 1
                if err_retries >= 3:
                    raise
                time.sleep(min(1.0 * (2 ** (err_retries - 1)), 6.0))


def _invalidate_graph_cache(graph_id: str) -> None:
    """丢弃某图谱的读取缓存（写入后调用）。"""
    with _GRAPH_CACHE_LOCK:
        _GRAPH_CACHE.pop(graph_id, None)


class ZepUnavailable(RuntimeError):
    """Zep 不可用：未配置 ZEP_API_KEY，或未安装 zep-cloud 依赖。

    这是一种预期内的降级情形（而非意外错误），供上层优雅处理。
    """


def _get_zep():
    """惰性创建 Zep 客户端；未配置/未安装时抛出 ZepUnavailable。"""
    if not config.has_zep():
        raise ZepUnavailable("未配置 ZEP_API_KEY（Zep 记忆图谱未启用）")
    try:
        from zep_cloud.client import Zep  # 惰性导入，避免无依赖时无法启动
    except ModuleNotFoundError as e:
        raise ZepUnavailable(
            "未安装 zep-cloud 依赖，请在 backend 目录执行 `uv sync` 安装完整依赖后重试"
        ) from e
    return Zep(api_key=config.ZEP_API_KEY)


def _add_text(zep, graph_id: str, text: str):
    """向图谱追加一段文本（带限流保护与重试），返回 Zep Episode 对象（含 uuid_）。"""
    return zep_call(zep.graph.add, graph_id=graph_id, type="text", data=text)


def _add_text_batch(zep, graph_id: str, chunks: list) -> list:
    """批量向图谱追加多段文本：一次请求提交多个 episode，显著减少 Zep 调用次数。

     的 graph.add_batch 写法；SDK 不支持时回退逐条写入。返回 Episode 列表。
    """
    from zep_cloud import EpisodeData

    episodes = [EpisodeData(data=c, type="text") for c in chunks if c]
    if not episodes:
        return []
    result = zep_call(zep.graph.add_batch,
                      graph_id=graph_id, episodes=episodes)
    return result if isinstance(result, list) else []


def _episode_uuid(ep):
    """兼容不同 SDK 字段，取 episode 的 uuid。"""
    return getattr(ep, "uuid_", None) or getattr(ep, "uuid", None)


def _graph_has_nodes(zep, graph_id: str) -> bool:
    """轻量探测：图谱是否已有可检索的节点。"""
    try:
        res = zep_call(zep.graph.node.get_by_graph_id, graph_id, limit=1)
        return bool(_as_list(res))
    except Exception as e:  # noqa: BLE001
        logger.warning("查询节点可用性失败：%s", e)
        return False


def _wait_for_processing(zep, graph_id: str, episodes, on_progress=None,
                         timeout: float = EPISODE_WAIT_TIMEOUT) -> bool:
    """等待 Zep 异步处理完成（仅轮询最后一个 episode 的 processed 标志）。

    ：只看 episode.processed，不再每轮额外调 node.get_by_graph_id
    探测节点（减少建图期间一半的 Zep 请求）。processed 后可能仍有短暂索引
    延迟，由后续「环境准备」阶段对空实体的重试兑底。超时则告警并放行。
    """
    uuids = [u for u in (_episode_uuid(e) for e in episodes) if u]
    if not uuids:
        return False
    last_uuid = uuids[-1]  # 大致按提交顺序处理，等最后一个完成即可
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            ep = zep_call(zep.graph.episode.get, uuid_=last_uuid)
            if getattr(ep, "processed", False):
                logger.info("Zep 已完成异步处理（episode=%s）", last_uuid)
                return True
        except Exception as e:  # noqa: BLE001
            logger.warning("查询 episode 处理状态失败（忽略继续等待）：%s", e)
        if on_progress:
            frac = 1 - max(0.0, (deadline - time.time()) / max(1.0, timeout))
            on_progress(88 + int(6 * min(1.0, frac)))
        time.sleep(EPISODE_POLL_INTERVAL)
    logger.warning("等待 Zep 处理超时（%ss），继续后续流程", timeout)
    return False


def to_screaming_snake_case(name: str) -> str:
    """转换为 SCREAMING_SNAKE_CASE。

    Zep 要求边（关系）类型名必须为该格式（全大写、下划线分词），
    例如 RELATES_TO、CREATED_BY。兼容 PascalCase/camelCase/空格/连字符等输入。
    """
    s = (name or "").strip()
    # 在小写/数字与大写字母边界插入下划线：RelatesTo -> Relates_To
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", s)
    # 其余非字母数字（空格、连字符等）统一替换为下划线
    s = re.sub(r"[^0-9A-Za-z]+", "_", s)
    # 合并多余下划线、去除首尾，最终全部大写
    return re.sub(r"_+", "_", s).strip("_").upper()


def _sanitize_identifier(name: str) -> str:
    """将任意名称转为合法的 Python 类名（仅用于动态类 __name__，不影响 Zep 侧名称）。"""
    ident = re.sub(r"\W|^(?=\d)", "_", (name or "").strip())
    return ident or "T"


# Zep 保留名称，不能作为实体/边的属性名（命中时加前缀规避）
_RESERVED_ATTR_NAMES = {
    "uuid", "name", "group_id", "name_embedding", "summary", "created_at",
}


def _safe_attr_name(attr_name: str) -> str:
    """将 Zep 保留名转为安全属性名（如 name -> entity_name）。"""
    if (attr_name or "").lower() in _RESERVED_ATTR_NAMES:
        return f"entity_{attr_name}"
    return attr_name


def _build_model(base, zep_name: str, description: str, attributes, attr_annotation):
    """动态创建带属性的实体/边模型类。

    Pydantic v2：属性需同时提供 Field 与类型注解，否则不会生效。
    :param base:            EntityModel 或 EdgeModel
    :param attr_annotation: 属性类型注解（实体用 Optional[EntityText]，边用 Optional[str]）
    """
    from pydantic import Field

    # description 为空会被 Zep 拒绝，这里兜底一个非空说明。
    doc = (description or "").strip() or f"{zep_name}（自动生成描述）"
    attrs: dict = {"__doc__": doc}
    annotations: dict = {}
    for attr in (attributes or []):
        raw = (attr or {}).get("name")
        if not raw:
            continue
        an = _safe_attr_name(raw)
        adesc = (attr or {}).get("description") or an
        # Zep 要求属性 Field 必须带 description
        attrs[an] = Field(description=adesc, default=None)
        annotations[an] = attr_annotation
    attrs["__annotations__"] = annotations
    model = type(_sanitize_identifier(zep_name), (base,), attrs)
    model.__doc__ = doc
    return model


def _apply_ontology(zep, graph_id: str, ontology: dict) -> None:
    """根据本体定义为图谱设置实体/边类型（含属性与 source_targets 约束）。

    ：
    - 实体/边类型均按本体定义动态创建**带属性**的 Pydantic 模型（属性会被 Zep 抽取填充）；
    - 边类型附带 source_targets（EntityEdgeSourceTarget），约束其连接的源/目标实体类型，
      从而让 Zep 抽取到更强类型化、更高质量的关系。

    Zep 侧硬性约束（否则返回 400）：
    - 每个实体/边类型必须有非空 description（SDK 通过类 docstring 读取）；
    - 边（关系）类型名必须为 SCREAMING_SNAKE_CASE（如 RELATES_TO）；
    - 属性名不能为保留字（已由 _safe_attr_name 规避）。
    """
    try:
        import warnings
        from typing import Optional

        from zep_cloud import EntityEdgeSourceTarget
        from zep_cloud.external_clients.ontology import (
            EdgeModel, EntityModel, EntityText,
        )

        # 动态创建实体类型（带属性，注解为 Optional[EntityText]）
        entity_models = {}
        for et in ontology.get("entity_types", []):
            name = (et or {}).get("name")
            if name:
                entity_models[name] = _build_model(
                    EntityModel, name, (et or {}).get("description"),
                    (et or {}).get("attributes"), Optional[EntityText])

        # 动态创建边类型（带属性 + source_targets 约束）
        edge_models = {}
        for edg in ontology.get("edge_types", []):
            # 边名统一规范为 SCREAMING_SNAKE_CASE，兼容历史 PascalCase 数据
            name = to_screaming_snake_case((edg or {}).get("name"))
            if not name:
                continue
            edge_cls = _build_model(
                EdgeModel, name, (edg or {}).get("description"),
                (edg or {}).get("attributes"), Optional[str])
            # 构建 source_targets（仅采用已定义的实体类型）
            source_targets = []
            for st in ((edg or {}).get("source_targets") or []):
                src = (st or {}).get("source")
                tgt = (st or {}).get("target")
                if src in entity_models and tgt in entity_models:
                    source_targets.append(
                        EntityEdgeSourceTarget(source=src, target=tgt))
            # 有约束用 (类, [约束]) 元组；无约束回退为裸类（仍注册该边类型）
            edge_models[name] = (
                (edge_cls, source_targets) if source_targets else edge_cls)

        # 抑制 Pydantic v2 关于 Field(default=None) 的无害告警：default 实际由
        # EntityText 的 Annotated 元数据提供，此处 Field 仅用于传递 description（Zep 必需）。
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=UserWarning)
            zep_call(
                zep.graph.set_ontology,
                graph_ids=[graph_id],
                entities=entity_models,
                edges=edge_models,
            )
        logger.info(
            "已设置本体：%d 个实体类型、%d 个关系类型（含 source_targets 的边 %d 个）",
            len(entity_models), len(edge_models),
            sum(1 for v in edge_models.values() if isinstance(v, tuple)),
        )
    except Exception as e:  # noqa: BLE001
        # 本体设置失败不阻断构建（Zep 仍可用默认 Entity 抽取）
        logger.warning("设置本体失败（忽略）：%s", e)


def build_graph(project, text: str, on_progress=None, on_graph_created=None) -> str:
    """在 Zep 中构建知识图谱，返回 graph_id。

    :param project:          Project 对象（含 ontology）
    :param text:             文档全文
    :param on_progress:      进度回调 (percent: int) -> None
    :param on_graph_created: 图谱创建后立即回调 (graph_id: str) -> None，
                             供前端在构建过程中实时可视化图谱（边构建边填充）。
    """
    zep = _get_zep()

    # 1) 创建 standalone graph
    # 新版 Zep SDK 要求由调用方显式提供 graph_id（必填关键字参数）。
    graph_id = f"g-{uuid.uuid4().hex}"
    graph = zep_call(
        zep.graph.create,
        graph_id=graph_id,
        name=(project.name or project.id)[:80],
        description=(project.requirement or "")[:200],
    )
    # 以服务端返回的 id 为准（若有），否则回退到本地生成的 graph_id。
    graph_id = (
        getattr(graph, "graph_id", None)
        or getattr(graph, "id", None)
        or graph_id
    )
    logger.info("已创建 Zep 图谱：%s", graph_id)
    # 尽早告知调用方 graph_id，便于前端在构建期间轮询展示图谱逐渐填充。
    if on_graph_created:
        try:
            on_graph_created(graph_id)
        except Exception:  # noqa: BLE001
            pass
    if on_progress:
        on_progress(10)

    # 2) 设置本体
    _apply_ontology(zep, graph_id, project.ontology or {})
    if on_progress:
        on_progress(20)

    # 3) 分块并批量写入（一次请求提交一批 chunk，大幅减少 Zep 调用次数）
    chunks = chunk_text(text)
    total = max(1, len(chunks))
    episodes = []
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i: i + BATCH_SIZE]
        try:
            eps = _add_text_batch(zep, graph_id, batch)
            episodes.extend(e for e in eps if e is not None)
        except Exception as e:  # noqa: BLE001
            # 批量接口不可用时回退逐条写入
            logger.warning("批量写入失败，回退逐条：%s", e)
            for chunk in batch:
                ep = _add_text(zep, graph_id, chunk)
                if ep is not None:
                    episodes.append(ep)
        done = min(i + BATCH_SIZE, total)
        if on_progress:
            on_progress(20 + int(65 * done / total))

    # 4) 等待 Zep 异步抽取完成，确保实体/边可被检索
    #    （否则「环境准备」会读到空实体，进而生成 0 个人设、模拟无法启动）
    if on_progress:
        on_progress(88)
    _wait_for_processing(zep, graph_id, episodes, on_progress=on_progress)

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
        # Zep SDK 的 pydantic 模型将 uuid 字段命名为 uuid_（alias="uuid"），
        # 直接 getattr(n, "uuid") 会取不到值。必须优先取 uuid_。
        "uuid": getattr(n, "uuid_", None) or getattr(n, "uuid", None) or getattr(n, "id", None),
        "name": getattr(n, "name", "") or "",
        "labels": getattr(n, "labels", None) or [],
        "summary": getattr(n, "summary", "") or "",
        # 属性：由富属性本体驱动 Zep 抽取填充（供人设/报告上下文使用）
        "attributes": getattr(n, "attributes", None) or {},
    }


def _edge_to_dict(e) -> dict:
    return {
        "uuid": getattr(e, "uuid_", None) or getattr(e, "uuid", None) or getattr(e, "id", None),
        "name": getattr(e, "name", "") or getattr(e, "type", "") or "",
        "source": getattr(e, "source_node_uuid", None),
        "target": getattr(e, "target_node_uuid", None),
        "fact": getattr(e, "fact", "") or "",
        "attributes": getattr(e, "attributes", None) or {},
        # 时序字段（Zep 时序知识图谱）：支撑「当前有效 vs 历史/已失效」的演变分析
        "created_at": getattr(e, "created_at", None),
        "valid_at": getattr(e, "valid_at", None),
        "invalid_at": getattr(e, "invalid_at", None),
        "expired_at": getattr(e, "expired_at", None),
    }


def get_graph_data(graph_id: str, use_cache: bool = True) -> dict:
    """读取图谱的全部节点与边，返回前端可用结构。

    带 5 秒短时缓存：前端在建图/模拟期间会频繁轮询，缓存可大幅减少
    对 Zep 的重复读取，避免 FREE 计划限流（429）。
    """
    now = time.time()
    if use_cache:
        with _GRAPH_CACHE_LOCK:
            cached = _GRAPH_CACHE.get(graph_id)
        if cached and now - cached[0] < _GRAPH_CACHE_TTL:
            return cached[1]

    zep = _get_zep()
    from ..utils.zep_paging import paginate

    def fetch_nodes(cursor, size):
        res = zep_call(zep.graph.node.get_by_graph_id,
                       graph_id, limit=size, uuid_cursor=cursor)
        items = _as_list(res)
        next_cursor = ((getattr(items[-1], "uuid_", None) or getattr(items[-1], "uuid", None))
                       if items and len(items) == size else None)
        return items, next_cursor

    def fetch_edges(cursor, size):
        res = zep_call(zep.graph.edge.get_by_graph_id,
                       graph_id, limit=size, uuid_cursor=cursor)
        items = _as_list(res)
        next_cursor = ((getattr(items[-1], "uuid_", None) or getattr(items[-1], "uuid", None))
                       if items and len(items) == size else None)
        return items, next_cursor

    nodes = paginate(fetch_nodes)
    edges = paginate(fetch_edges)
    result = {
        "graph_id": graph_id,
        "nodes": [_node_to_dict(n) for n in nodes],
        "edges": [_edge_to_dict(e) for e in edges],
    }
    with _GRAPH_CACHE_LOCK:
        # 容量上限：超过则淘汰最旧条目，防止长时间运行内存无限增长
        if len(_GRAPH_CACHE) >= _GRAPH_CACHE_MAX and graph_id not in _GRAPH_CACHE:
            oldest = min(_GRAPH_CACHE, key=lambda k: _GRAPH_CACHE[k][0])
            _GRAPH_CACHE.pop(oldest, None)
        _GRAPH_CACHE[graph_id] = (time.time(), result)
    return result
