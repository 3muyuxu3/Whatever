"""模拟后图谱记忆更新（可选阶段）。

模拟结束后，将 Agent 的社交活动动态写回 Zep 图谱，丰富实体的时序记忆数据。
"""

from ..utils.logger import get_logger

logger = get_logger("memory_updater")


def update_graph_memory(graph_id: str, actions: list[dict]) -> int:
    """将动作日志写回 Zep 图谱。返回成功写入的条数。"""
    from .graph_builder import _add_text, _get_zep

    zep = _get_zep()
    count = 0
    for a in actions:
        agent = a.get("agent_name") or a.get("agent_id") or "agent"
        text = (
            f"[{a.get('platform', '')}] {agent} 执行 {a.get('action', '')}"
            f"：{a.get('content', '')}"
        )
        try:
            _add_text(zep, graph_id, text)
            count += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("写回记忆失败（忽略）：%s", e)
    logger.info("已向图谱 %s 写回 %d 条记忆", graph_id, count)
    return count
