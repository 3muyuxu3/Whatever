"""本体生成服务。

使用 LLM 分析文档内容，自动提取实体类型与关系类型。
约束：正好生成 10 个实体类型（8 个具体类型 + Person + Organization 兜底类型）。
"""

from ..utils.llm_client import get_llm_client
from ..utils.logger import get_logger
from .graph_builder import to_screaming_snake_case

logger = get_logger("ontology")

# 兜底实体类型（必须包含）
FALLBACK_TYPES = ["Person", "Organization"]

# 目标实体类型总数
TARGET_ENTITY_COUNT = 10

SYSTEM_PROMPT = """你是一名知识本体（ontology）设计专家。
请根据用户的预测需求与文档内容，设计一套用于构建知识图谱的本体。

严格要求：
1. 必须输出正好 10 个实体类型（entity_types）：其中 8 个是与文档强相关的具体类型，
   另外 2 个固定为 "Person" 和 "Organization" 作为兜底类型。
2. 设计 5-10 个关系类型（edge_types），描述实体之间可能的关系。
3. 命名规范（必须严格遵守，否则建图会失败）：
   - 实体类型 name：英文 PascalCase，例如 PolicyDocument、MarketTrend。
   - 关系类型 name：英文 SCREAMING_SNAKE_CASE（全大写、下划线分词），例如 RELATES_TO、ISSUED_BY、WORKS_FOR。
4. 每个类型都必须包含非空的 description（简要中文说明，不得留空）。
5. 额外输出 analysis_summary：用 2-4 句话概述文档要点、关键议题与本体设计思路。

仅输出 JSON，格式如下：
{
  "entity_types": [{"name": "PolicyDocument", "description": "..."}, ...],
  "edge_types": [{"name": "ISSUED_BY", "description": "..."}, ...],
  "analysis_summary": "..."
}
"""


def generate_ontology(text: str, requirement: str) -> dict:
    """调用 LLM 生成本体定义，并保证约束（10 个实体类型且含兜底类型）。"""
    client = get_llm_client()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"【预测需求】\n{requirement}\n\n"
                f"【文档内容（节选）】\n{text[:6000]}"
            ),
        },
    ]
    data = client.chat_json(messages)

    entity_types = data.get("entity_types") or []
    # 规范化并去重（保证 description 非空）
    seen = set()
    normalized = []
    for item in entity_types:
        name = (item or {}).get("name")
        if name and name not in seen:
            seen.add(name)
            desc = ((item or {}).get("description")
                    or "").strip() or f"{name} 实体类型"
            normalized.append({"name": name, "description": desc})

    # 确保包含兜底类型
    for fb in FALLBACK_TYPES:
        if fb not in seen:
            normalized.append({"name": fb, "description": f"{fb}（兜底实体类型）"})
            seen.add(fb)

    # 截断到 10 个（保证兜底类型在内）
    if len(normalized) > TARGET_ENTITY_COUNT:
        specific = [e for e in normalized if e["name"] not in FALLBACK_TYPES]
        fallback = [e for e in normalized if e["name"] in FALLBACK_TYPES]
        normalized = specific[: TARGET_ENTITY_COUNT - len(fallback)] + fallback

    # 规范化关系类型：name 转 SCREAMING_SNAKE_CASE、description 非空、去重
    edge_seen = set()
    edges = []
    for edg in (data.get("edge_types") or []):
        name = to_screaming_snake_case((edg or {}).get("name"))
        if not name or name in edge_seen:
            continue
        edge_seen.add(name)
        desc = ((edg or {}).get("description") or "").strip() or f"{name} 关系类型"
        edges.append({"name": name, "description": desc})

    data["entity_types"] = normalized
    data["edge_types"] = edges
    data["analysis_summary"] = data.get("analysis_summary") or ""
    logger.info("生成本体：%d 个实体类型，%d 个关系类型", len(
        normalized), len(edges))
    return data
