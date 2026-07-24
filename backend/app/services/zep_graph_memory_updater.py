"""模拟后图谱记忆更新（可选阶段）。

模拟结束后，将 Agent 的社交活动动态写回 Zep 图谱，丰富实体的时序记忆数据。

：为 12 种社交动作生成自然语言描述（让 Zep 能从中抽取实体与关系）。
保留本项目 FREE 计划优化：**批量合并多条活动为一次 graph.add**，并经 zep_call 全局节流，
显著降低写回阶段的 Zep 请求量（相较逐条写入）。
"""

from ..utils.logger import get_logger

logger = get_logger("memory_updater")

# 每批合并写入的活动条数（合并为一段文本，减少 graph.add 调用次数）
BATCH_SIZE = 5

# 不写回的动作（无信息量）
_SKIP_ACTIONS = {"DO_NOTHING", ""}


def _describe(action: str, agent: str, content: str) -> str:
    """将单条动作转换为自然语言描述（供 Zep 抽取实体/关系）。"""
    a = (action or "").upper()
    c = (content or "").strip()
    quoted = f"：「{c}」" if c else ""

    if a == "CREATE_POST":
        return f"{agent} 发布了一条帖子{quoted}" if c else f"{agent} 发布了一条帖子"
    if a == "CREATE_COMMENT":
        return f"{agent} 发表评论{quoted}" if c else f"{agent} 发表了评论"
    if a == "QUOTE_POST":
        return f"{agent} 引用并评论了一条帖子{quoted}" if c else f"{agent} 引用了一条帖子"
    if a == "REPOST":
        return f"{agent} 转发了一条帖子{quoted}" if c else f"{agent} 转发了一条帖子"
    if a == "LIKE_POST":
        return f"{agent} 点赞了一条帖子{quoted}" if c else f"{agent} 点赞了一条帖子"
    if a == "DISLIKE_POST":
        return f"{agent} 踩了一条帖子{quoted}" if c else f"{agent} 踩了一条帖子"
    if a == "LIKE_COMMENT":
        return f"{agent} 点赞了一条评论{quoted}" if c else f"{agent} 点赞了一条评论"
    if a == "DISLIKE_COMMENT":
        return f"{agent} 踩了一条评论{quoted}" if c else f"{agent} 踩了一条评论"
    if a == "FOLLOW":
        return f"{agent} 关注了{quoted}" if c else f"{agent} 关注了一个用户"
    if a == "MUTE":
        return f"{agent} 屏蔽了{quoted}" if c else f"{agent} 屏蔽了一个用户"
    if a in ("SEARCH_POSTS", "SEARCH_USER"):
        return f"{agent} 搜索了{quoted}" if c else f"{agent} 进行了搜索"
    if a == "INJECT":
        return f"（外部事件注入）{c}" if c else f"发生了一个新事件"
    # 通用兜底
    return f"{agent} 执行了 {a} 操作{quoted}" if c else f"{agent} 执行了 {a} 操作"


def update_graph_memory(graph_id: str, actions: list[dict]) -> int:
    """将动作日志批量写回 Zep 图谱。返回成功写入的活动条数。

    - 跳过 DO_NOTHING 等无信息量动作；
    - 每 BATCH_SIZE 条合并为一段文本，一次 graph.add 写入（减少 Zep 请求量）；
    - 所有调用经 zep_call 全局节流 + 429 重试。
    """
    from .graph_builder import _get_zep, zep_call

    zep = _get_zep()

    # 1) 生成描述并过滤
    descriptions: list[str] = []
    for a in actions:
        action = (a.get("action") or "").upper()
        if action in _SKIP_ACTIONS:
            continue
        agent = a.get("agent_name") or a.get("agent_id") or "某用户"
        desc = _describe(action, str(agent), a.get("content") or "")
        if desc:
            descriptions.append(desc)

    if not descriptions:
        logger.info("无可写回的有效动作")
        return 0

    # 2) 批量合并写入
    count = 0
    for i in range(0, len(descriptions), BATCH_SIZE):
        batch = descriptions[i:i + BATCH_SIZE]
        text = "\n".join(batch)
        try:
            zep_call(zep.graph.add, graph_id=graph_id, type="text", data=text)
            count += len(batch)
        except Exception as e:  # noqa: BLE001
            logger.warning("批量写回记忆失败（忽略该批）：%s", e)

    logger.info("已向图谱 %s 批量写回 %d 条记忆（%d 批）",
                graph_id, count, (len(descriptions) + BATCH_SIZE - 1) // BATCH_SIZE)
    return count
