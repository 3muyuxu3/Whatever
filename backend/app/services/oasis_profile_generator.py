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
  "activity_level": 0.0-1.0 之间的活跃度,
  "gender": "male / female / other",
  "age": 18-80 之间的整数,
  "country": "国家或地区"
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
            "gender": "unknown",
            "age": 30,
            "country": "China",
        }
    data["name"] = entity.get("name")
    data["entity_uuid"] = entity.get("uuid")
    return _normalize_for_oasis(data, entity)


def _normalize_for_oasis(data: dict, entity: dict) -> dict:
    """补齐 OASIS 加载 Agent 图所需的字段。

    缺字段会导致真实 OASIS 直接报错（KeyError）并回退到降级模拟循环：
    - Twitter 需要：username / description / user_char
    - Reddit 需要：username / bio / persona / mbti / gender / age / country
    """
    name = (entity.get("name") or data.get("name") or "").strip()
    uid = (entity.get("uuid") or "")[:6] or "x"
    data["name"] = name or "Agent"
    data["username"] = data.get("username") or name or f"user_{uid}"
    data["bio"] = (data.get("bio") or entity.get("summary")
                   or f"{data['name']}，模拟世界中的一员。").strip()
    data["persona"] = (data.get("persona") or data["bio"]).strip()
    data["mbti"] = (data.get("mbti") or "INTJ").strip() or "INTJ"
    data.setdefault("occupation", "")
    if not isinstance(data.get("interests"), list):
        data["interests"] = []
    data["gender"] = (str(data.get("gender") or "unknown")
                      ).strip() or "unknown"
    try:
        data["age"] = int(data.get("age") or 30)
    except (ValueError, TypeError):
        data["age"] = 30
    data["country"] = (str(data.get("country") or "China")).strip() or "China"
    try:
        data["activity_level"] = float(data.get("activity_level", 0.5))
    except (ValueError, TypeError):
        data["activity_level"] = 0.5
    return data


def generate_profiles(entities: list[dict], graph_id: str | None = None,
                      concurrency: int = DEFAULT_CONCURRENCY) -> list[dict]:
    """并行为多个实体生成人设。"""
    if not entities:
        return []
    profiles: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as executor:
        futures = [executor.submit(_generate_one, e, graph_id)
                   for e in entities]
        for f in futures:
            profiles.append(f.result())
    logger.info("共生成 %d 个 Agent 人设", len(profiles))
    return profiles


def to_reddit_json(profiles: list[dict]) -> list[dict]:
    """输出 Reddit JSON 格式（对齐 OASIS generate_reddit_agent_graph 所需字段）。

    OASIS 会读取 username / bio / persona / mbti / gender / age / country，
    缺任意一个都会报错，因此这里保底补齐。
    """
    out = []
    for idx, p in enumerate(profiles):
        q = dict(p)
        q["username"] = p.get("username") or p.get("name") or f"user_{idx}"
        q["bio"] = p.get("bio") or ""
        q["persona"] = p.get("persona") or q["bio"] or ""
        q["mbti"] = p.get("mbti") or "INTJ"
        q["gender"] = p.get("gender") or "unknown"
        try:
            q["age"] = int(p.get("age") or 30)
        except (ValueError, TypeError):
            q["age"] = 30
        q["country"] = p.get("country") or "China"
        out.append(q)
    return out


def to_twitter_csv(profiles: list[dict]) -> str:
    """输出 Twitter CSV 格式（列名与 OASIS generate_twitter_agent_graph 对齐）。

    OASIS 会读取 username / description / user_char 三列构建 Agent，
    其余列为附加信息（便于调试与人工查看）。user_char / description 务必非空。
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["user_id", "username", "name", "description", "user_char",
         "bio", "persona", "mbti", "occupation", "interests",
         "activity_level", "gender", "age", "country"]
    )
    for idx, p in enumerate(profiles):
        name = p.get("name", "") or f"user_{idx}"
        bio = (p.get("bio") or "").strip()
        persona = (p.get("persona") or "").strip()
        occupation = p.get("occupation", "") or ""
        interests = ";".join(p.get("interests", []) or [])
        # user_char：OASIS 用作 Agent 的人物画像，务必非空
        parts = [persona or bio or f"{name}，社交媒体用户。"]
        if occupation:
            parts.append(f"职业：{occupation}")
        if p.get("mbti"):
            parts.append(f"MBTI：{p['mbti']}")
        if interests:
            parts.append(f"兴趣：{interests}")
        user_char = "，".join(parts)
        description = bio or persona or f"{name}，社交媒体用户。"
        writer.writerow(
            [
                idx,
                p.get("username") or name,
                name,
                description,
                user_char,
                bio,
                persona,
                p.get("mbti", ""),
                occupation,
                interests,
                p.get("activity_level", 0.5),
                p.get("gender", "unknown"),
                p.get("age", 30),
                p.get("country", "China"),
            ]
        )
    return buf.getvalue()
