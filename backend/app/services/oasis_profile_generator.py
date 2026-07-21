"""OASIS Agent 人设（Profile）生成服务。

对每个过滤后的实体，可选地调用 Zep 混合搜索获取丰富上下文，
再用 LLM 生成详细的 Agent 人设；支持并行生成；输出 Reddit JSON 与 Twitter CSV 两种格式。
"""

import csv
import io
from concurrent.futures import ThreadPoolExecutor

from ..utils.llm_client import get_llm_client
from ..utils.logger import get_logger

logger = get_logger("profile")

# 默认并发数（3-5）
DEFAULT_CONCURRENCY = 3

PROFILE_PROMPT = """你是一名社会学专家，请根据给定实体信息，为其生成一个可用于社交媒体模拟的 Agent 人设。
仅输出 JSON，字段包括：
{
  "bio": "人物传记（1-2 句）",
  "persona": "人格描述",
  "mbti": "MBTI 类型（如 INTJ）",
  "occupation": "职业",
  "interests": ["兴趣标签", "..."],
  "activity_level": 0.0-1.0 之间的活跃度
}
"""


def _enrich_context(graph_id: str | None, entity: dict) -> str:
    """可选：用 Zep 混合搜索为实体补充上下文。"""
    if not graph_id:
        return entity.get("summary", "")
    try:
        from .zep_tools import quick_search

        hits = quick_search(graph_id, entity.get("name", ""), limit=5)
        extra = "\n".join(h.get("text", "") for h in hits)
        return f"{entity.get('summary', '')}\n{extra}".strip()
    except Exception:  # noqa: BLE001
        return entity.get("summary", "")


def _generate_one(entity: dict, graph_id: str | None = None) -> dict:
    """为单个实体生成人设。"""
    client = get_llm_client()
    context = _enrich_context(graph_id, entity)
    prompt = (
        f"名称：{entity.get('name')}\n"
        f"类型：{entity.get('type')}\n"
        f"背景信息：{context}"
    )
    try:
        data = client.chat_json(
            [
                {"role": "system", "content": PROFILE_PROMPT},
                {"role": "user", "content": prompt},
            ]
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("生成人设失败，使用兜底：%s", e)
        data = {
            "bio": entity.get("summary", ""),
            "persona": "",
            "mbti": "INTJ",
            "occupation": "",
            "interests": [],
            "activity_level": 0.5,
        }
    data["name"] = entity.get("name")
    data["entity_uuid"] = entity.get("uuid")
    return data


def generate_profiles(entities: list[dict], graph_id: str | None = None,
                      concurrency: int = DEFAULT_CONCURRENCY) -> list[dict]:
    """并行为多个实体生成人设。"""
    if not entities:
        return []
    profiles: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as executor:
        futures = [executor.submit(_generate_one, e, graph_id) for e in entities]
        for f in futures:
            profiles.append(f.result())
    logger.info("共生成 %d 个 Agent 人设", len(profiles))
    return profiles


def to_reddit_json(profiles: list[dict]) -> list[dict]:
    """输出 Reddit JSON 格式（直接返回结构化人设列表）。"""
    return profiles


def to_twitter_csv(profiles: list[dict]) -> str:
    """输出 Twitter CSV 格式的人设。"""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["user_id", "name", "bio", "persona", "mbti", "occupation", "interests", "activity_level"]
    )
    for idx, p in enumerate(profiles):
        writer.writerow(
            [
                idx,
                p.get("name", ""),
                p.get("bio", ""),
                p.get("persona", ""),
                p.get("mbti", ""),
                p.get("occupation", ""),
                ";".join(p.get("interests", []) or []),
                p.get("activity_level", 0.5),
            ]
        )
    return buf.getvalue()
