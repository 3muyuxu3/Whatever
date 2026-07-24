"""本体生成服务（接口 01）。

分析文档内容与预测需求，生成适合「社交媒体舆论模拟」的实体类型与关系类型定义。

设计目标：
- 实体必须是现实中可在社媒发声、互动、传播信息的真实主体（个人 / 公司 / 机构 /
  媒体 / 政府 / 平台 / 群体代表等），而非抽象概念（如「舆论」「趋势」「学术诚信」）。
- 正好 10 个实体类型：8 个与文档强相关的具体类型 + Person / Organization 两个兜底类型。
- 每个实体类型带 attributes（1-3 个关键属性）与 examples（示例实体）。
- 每个关系类型带 source_targets（源/目标实体类型约束）与 description。

上述结构会被接口 02（图谱构建）用于设置 Zep 本体，从而让 Zep 抽取到更丰富、
更强类型化的图谱（节点带属性、边受源/目标约束），最终显著提升人设生成与报告质量。
"""

import re

from ..utils.llm_client import get_llm_client
from ..utils.logger import get_logger
from .graph_builder import to_screaming_snake_case

logger = get_logger("ontology")

# 兜底实体类型（必须包含，放在实体列表末尾）
FALLBACK_TYPES = ["Person", "Organization"]

# 目标实体类型总数与关系类型上限（Zep：自定义实体/边类型各上限 10）
TARGET_ENTITY_COUNT = 10
MAX_EDGE_TYPES = 10

# 传给 LLM 的文档最大长度（，5 万字；仅影响本体分析，不影响建图）
MAX_TEXT_LENGTH_FOR_LLM = 50000

# 描述字段最大长度（Zep 侧偏好简短描述）
MAX_DESC_LENGTH = 100

# 系统保留属性名（不能作为实体/关系的属性名，命中时提示词会要求改用替代名）
RESERVED_ATTR_NAMES = {
    "name", "uuid", "group_id", "created_at", "summary", "name_embedding",
}


SYSTEM_PROMPT = """你是一个专业的知识图谱本体设计专家。你的任务是分析给定的文本内容和模拟需求，\
设计适合**社交媒体舆论模拟**的实体类型和关系类型。

**重要：你必须输出有效的 JSON 格式数据，不要输出任何其他内容。**

## 核心任务背景

我们正在构建一个**社交媒体舆论模拟系统**。在这个系统中：
- 每个实体都是一个可以在社交媒体上发声、互动、传播信息的「账号」或「主体」；
- 实体之间会相互影响、转发、评论、回应；
- 我们需要模拟舆论事件中各方的反应和信息传播路径。

因此，**实体必须是现实中真实存在的、可以在社媒上发声和互动的主体**：

**可以是**：
- 具体的个人（公众人物、当事人、意见领袖、专家学者、普通人）
- 公司、企业（包括其官方账号）
- 组织机构（大学、协会、NGO、工会等）
- 政府部门、监管机构
- 媒体机构（报纸、电视台、自媒体、网站）
- 社交媒体平台本身
- 特定群体代表（如校友会、粉丝团、维权群体等）

**不可以是**：
- 抽象概念（如「舆论」「情绪」「趋势」）
- 主题 / 话题（如「学术诚信」「教育改革」）
- 观点 / 态度（如「支持方」「反对方」）

## 输出格式

请输出 JSON，包含以下结构：
{
  "entity_types": [
    {
      "name": "实体类型名称（英文 PascalCase）",
      "description": "简短中文描述（不超过 100 字符）",
      "attributes": [
        {"name": "属性名（英文 snake_case）", "type": "text", "description": "属性中文说明"}
      ],
      "examples": ["示例实体1", "示例实体2"]
    }
  ],
  "edge_types": [
    {
      "name": "关系类型名称（英文 SCREAMING_SNAKE_CASE）",
      "description": "简短中文描述（不超过 100 字符）",
      "source_targets": [{"source": "源实体类型", "target": "目标实体类型"}],
      "attributes": []
    }
  ],
  "analysis_summary": "对文本内容的简要中文分析说明"
}

## 设计指南（极其重要！）

### 1. 实体类型设计 —— 必须严格遵守

**数量要求：必须正好 10 个实体类型。**

**层次结构要求（必须同时包含具体类型与兜底类型）**：
A. 兜底类型（必须包含，放在列表最后 2 个）：
   - `Person`：任何自然人个体的兜底类型。当一个人不属于其他更具体的人物类型时归入此类。
   - `Organization`：任何组织机构的兜底类型。当一个组织不属于其他更具体的组织类型时归入此类。
B. 具体类型（8 个，根据文本内容设计）：
   - 针对文本中出现的主要角色设计更具体的类型；
   - 例如学术事件可有 `Student`/`Professor`/`University`；商业事件可有 `Company`/`Executive`/`Employee`；
   - 每个具体类型边界清晰、避免重叠，description 要说明与兜底类型的区别。

### 2. 关系类型设计
- 数量：6-10 个；
- 关系应反映社媒互动中的真实联系；
- **每个关系必须给出 source_targets**，且 source / target 必须来自你上面定义的实体类型名称。

### 3. 属性设计
- 每个实体类型 1-3 个关键属性；
- 属性名不能使用 name、uuid、group_id、created_at、summary（系统保留字），\
可用 full_name、org_name、title、role、position、location 等替代。

## 实体类型参考
- 个人（具体）：Student、Professor、Journalist、Celebrity、Executive、Official、Lawyer、Doctor
- 个人（兜底）：Person
- 组织（具体）：University、Company、GovernmentAgency、MediaOutlet、Hospital、School、NGO
- 组织（兜底）：Organization

## 关系类型参考
WORKS_FOR、STUDIES_AT、AFFILIATED_WITH、REPRESENTS、REGULATES、REPORTS_ON、\
COMMENTS_ON、RESPONDS_TO、SUPPORTS、OPPOSES、COLLABORATES_WITH、COMPETES_WITH

IMPORTANT: Entity type names MUST be English PascalCase (e.g. MediaOutlet); \
relationship type names MUST be English SCREAMING_SNAKE_CASE (e.g. WORKS_FOR); \
attribute names MUST be English snake_case. Only description / examples / \
analysis_summary use Chinese.
"""


def _to_pascal_case(name: str) -> str:
    """将任意格式名称转为 PascalCase（'works_for' -> 'WorksFor'，'person' -> 'Person'）。"""
    parts = re.split(r"[^a-zA-Z0-9]+", name or "")
    words = []
    for part in parts:
        # 拆分 camelCase 边界：'camelCase' -> ['camel', 'Case']
        words.extend(re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", part).split("_"))
    result = "".join(w.capitalize() for w in words if w)
    return result or "Unknown"


def _cap_desc(desc: str, fallback: str) -> str:
    """规整描述：为空则回退，超长则截断到 MAX_DESC_LENGTH。"""
    d = (desc or "").strip() or fallback
    if len(d) > MAX_DESC_LENGTH:
        d = d[: MAX_DESC_LENGTH - 3] + "..."
    return d


def _clean_attributes(attrs) -> list[dict]:
    """规整实体/关系属性列表：仅保留含 name 的字典项，补齐 type / description 并去重。"""
    if not isinstance(attrs, list):
        return []
    out, seen = [], set()
    for a in attrs:
        if not isinstance(a, dict):
            continue
        name = (a.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append({
            "name": name,
            "type": (str(a.get("type") or "text").strip() or "text"),
            "description": (a.get("description") or "").strip() or f"{name}",
        })
    return out


def _clean_examples(examples) -> list[str]:
    """规整示例列表：仅保留非空字符串，最多 5 个。"""
    if not isinstance(examples, list):
        return []
    out = []
    for e in examples:
        s = str(e).strip()
        if s:
            out.append(s)
        if len(out) >= 5:
            break
    return out


def _clean_source_targets(source_targets, name_map: dict, valid_names: set) -> list[dict]:
    """规整边的 source_targets：把实体名改写为规范化后的 PascalCase，且必须落在已定义实体内。"""
    if not isinstance(source_targets, list):
        return []
    out, seen = [], set()
    for st in source_targets:
        if not isinstance(st, dict):
            continue
        src = st.get("source")
        tgt = st.get("target")
        src = name_map.get(src, _to_pascal_case(src) if src else None)
        tgt = name_map.get(tgt, _to_pascal_case(tgt) if tgt else None)
        # 源/目标必须是已定义的实体类型，否则跳过（避免 Zep 400）
        if not src or not tgt or src not in valid_names or tgt not in valid_names:
            continue
        key = (src, tgt)
        if key in seen:
            continue
        seen.add(key)
        out.append({"source": src, "target": tgt})
    return out


def _build_user_message(text: str, requirement: str) -> str:
    """构建用户消息：模拟需求 + 文档内容（超长按 5 万字截断）。"""
    combined = (text or "").strip()
    original_len = len(combined)
    if original_len > MAX_TEXT_LENGTH_FOR_LLM:
        combined = combined[:MAX_TEXT_LENGTH_FOR_LLM]
        combined += (f"\n\n...(原文共 {original_len} 字，已截取前 "
                     f"{MAX_TEXT_LENGTH_FOR_LLM} 字用于本体分析)...")
    return (
        f"## 模拟需求\n\n{requirement}\n\n"
        f"## 文档内容\n\n{combined}\n\n"
        "请根据以上内容，设计适合社会舆论模拟的实体类型和关系类型。\n\n"
        "**必须遵守的规则**：\n"
        "1. 必须正好输出 10 个实体类型；\n"
        "2. 最后 2 个必须是兜底类型：Person（个人兜底）和 Organization（组织兜底）；\n"
        "3. 前 8 个是根据文本内容设计的具体类型；\n"
        "4. 所有实体类型必须是现实中可以发声的主体，不能是抽象概念；\n"
        "5. 每个关系类型必须给出 source_targets，且引用已定义的实体类型；\n"
        "6. 属性名不能使用 name、uuid、group_id 等保留字，用 full_name、org_name 等替代。"
    )


# 兜底实体类型定义（带属性与示例，供缺失时补齐）
_PERSON_FALLBACK = {
    "name": "Person",
    "description": "任何不属于其他具体人物类型的自然人个体（兜底类型）。",
    "attributes": [
        {"name": "full_name", "type": "text", "description": "人物全名"},
        {"name": "role", "type": "text", "description": "身份或职业角色"},
    ],
    "examples": ["普通市民", "匿名网友"],
}

_ORGANIZATION_FALLBACK = {
    "name": "Organization",
    "description": "任何不属于其他具体组织类型的组织机构（兜底类型）。",
    "attributes": [
        {"name": "org_name", "type": "text", "description": "组织名称"},
        {"name": "org_type", "type": "text", "description": "组织类型"},
    ],
    "examples": ["小型企业", "社区团体"],
}


def generate_ontology(text: str, requirement: str) -> dict:
    """调用 LLM 生成本体定义，并保证约束（10 个实体类型且含兜底类型、边含 source_targets）。"""
    client = get_llm_client()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_message(text, requirement)},
    ]
    # 输出结构较大（含 attributes/examples/source_targets），放宽 max_tokens 避免截断
    data = client.chat_json(messages, temperature=0.3, max_tokens=4096)

    # ---- 1) 规范化实体类型：PascalCase、清洗属性/示例、去重、限制描述长度 ----
    name_map: dict[str, str] = {}   # 原始名 -> PascalCase 名（用于修正 edge 引用）
    seen: set[str] = set()
    normalized: list[dict] = []
    for item in (data.get("entity_types") or []):
        raw_name = (item or {}).get("name")
        if not raw_name:
            continue
        pas = _to_pascal_case(raw_name)
        name_map[raw_name] = pas
        if pas in seen:
            continue
        seen.add(pas)
        normalized.append({
            "name": pas,
            "description": _cap_desc((item or {}).get("description"), f"{pas} 实体类型"),
            "attributes": _clean_attributes((item or {}).get("attributes")),
            "examples": _clean_examples((item or {}).get("examples")),
        })

    # ---- 2) 补齐兜底类型（Person / Organization）----
    for fb in (_PERSON_FALLBACK, _ORGANIZATION_FALLBACK):
        if fb["name"] not in seen:
            normalized.append(dict(fb))
            seen.add(fb["name"])

    # ---- 3) 截断到 10 个（保证兜底类型保留在末尾）----
    if len(normalized) > TARGET_ENTITY_COUNT:
        specific = [e for e in normalized if e["name"] not in FALLBACK_TYPES]
        fallback = [e for e in normalized if e["name"] in FALLBACK_TYPES]
        keep = TARGET_ENTITY_COUNT - len(fallback)
        normalized = specific[:keep] + fallback

    valid_names = {e["name"] for e in normalized}

    # ---- 4) 规范化关系类型：SCREAMING_SNAKE_CASE、修正 source_targets 引用、去重 ----
    edge_seen: set[str] = set()
    edges: list[dict] = []
    for edg in (data.get("edge_types") or []):
        ename = to_screaming_snake_case((edg or {}).get("name"))
        if not ename or ename in edge_seen:
            continue
        edge_seen.add(ename)
        edges.append({
            "name": ename,
            "description": _cap_desc((edg or {}).get("description"), f"{ename} 关系类型"),
            "source_targets": _clean_source_targets(
                (edg or {}).get("source_targets"), name_map, valid_names),
            "attributes": _clean_attributes((edg or {}).get("attributes")),
        })
        if len(edges) >= MAX_EDGE_TYPES:
            break

    data["entity_types"] = normalized
    data["edge_types"] = edges
    data["analysis_summary"] = (data.get("analysis_summary") or "").strip()
    logger.info(
        "生成本体：%d 个实体类型，%d 个关系类型（含 source_targets 的边 %d 个）",
        len(normalized), len(edges),
        sum(1 for e in edges if e["source_targets"]),
    )
    return data
