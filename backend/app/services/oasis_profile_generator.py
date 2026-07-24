"""OASIS Agent 人设（Profile）生成服务。

 的人设丰富度，同时保留本项目 FREE 计划优化：
- 复用 read_entities 已获取的 summary / related_edges / related_nodes 构建上下文，
  **不为每个实体单独发 Zep 检索**（避免 N 实体 = N 请求触发 429）；
- 区分「个人」与「机构/群体」实体，分别用详细提示词生成 2000 字级人设；
- LLM 失败/截断时：先尝试 JSON 修复，再按实体类型规则兜底；
- 补齐 OASIS 加载所需字段；输出 Reddit JSON 与 Twitter CSV 两种格式。
"""

import csv
import io
import json
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..utils.llm_client import get_llm_client
from ..utils.logger import get_logger

logger = get_logger("profile")

# 默认并发数（3-5）
DEFAULT_CONCURRENCY = 3

# MBTI 与国家候选（规则兜底用）
MBTI_TYPES = [
    "INTJ", "INTP", "ENTJ", "ENTP", "INFJ", "INFP", "ENFJ", "ENFP",
    "ISTJ", "ISFJ", "ESTJ", "ESFJ", "ISTP", "ISFP", "ESTP", "ESFP",
]
COUNTRIES = ["中国", "美国", "英国", "日本", "德国", "法国", "加拿大", "澳大利亚"]

# 个人类实体（生成具体人物人设）
INDIVIDUAL_ENTITY_TYPES = {
    "student", "alumni", "professor", "person", "publicfigure", "celebrity",
    "expert", "faculty", "official", "journalist", "activist", "lawyer",
    "doctor", "executive", "ceo", "employee",
}
# 机构/群体类实体（生成官方账号人设）
GROUP_ENTITY_TYPES = {
    "university", "governmentagency", "organization", "ngo", "school",
    "mediaoutlet", "company", "institution", "group", "community", "hospital",
}

SYSTEM_PROMPT_BASE = (
    "你是社交媒体用户画像生成专家，为舆论模拟生成详细、真实的人设，"
    "最大程度还原已有现实情况。必须返回有效 JSON，所有字符串值不得包含未转义换行符。"
    "请使用中文（gender 字段除外）。"
)


def _entity_type(entity: dict) -> str:
    """取实体的具体类型（排除默认标签）。"""
    t = (entity.get("type") or "").strip()
    if t and t not in ("Entity", "Node"):
        return t
    for lb in (entity.get("labels") or []):
        if lb not in ("Entity", "Node"):
            return lb
    return t or "Entity"


def _is_individual(entity_type: str) -> bool:
    return (entity_type or "").lower() in INDIVIDUAL_ENTITY_TYPES


def _is_group(entity_type: str) -> bool:
    return (entity_type or "").lower() in GROUP_ENTITY_TYPES


def _enrich_context(entity: dict) -> str:
    """构建实体上下文（复用已读取的 summary / 关联事实 / 关联节点，零额外 Zep）。"""
    parts: list[str] = []
    summary = (entity.get("summary") or "").strip()
    if summary:
        parts.append(f"### 实体摘要\n{summary}")

    facts = []
    for e in (entity.get("related_edges") or [])[:12]:
        fact = (e.get("fact") or e.get("edge_name")
                or e.get("name") or "").strip()
        if fact:
            direction = e.get("direction")
            facts.append(
                f"- {fact}" if not direction else f"- [{direction}] {fact}")
    if facts:
        parts.append("### 相关事实与关系\n" + "\n".join(facts))

    related_nodes = entity.get("related_nodes") or []
    if related_nodes:
        infos = []
        for n in related_nodes[:10]:
            nm = n.get("name", "")
            sm = (n.get("summary") or "").strip()
            infos.append(f"- {nm}：{sm}" if sm else f"- {nm}")
        if infos:
            parts.append("### 关联实体\n" + "\n".join(infos))
    return "\n\n".join(parts)


def _individual_prompt(name: str, etype: str, summary: str, context: str) -> str:
    return f"""为下列个人实体生成详细的社交媒体用户人设，最大程度还原已有现实情况。

实体名称：{name}
实体类型：{etype}
实体摘要：{summary or '（无）'}

上下文信息：
{context[:3000] or '（无额外上下文）'}

请生成 JSON，包含字段：
1. bio：社交媒体简介（约 200 字）
2. persona：详细人设（约 1500-2000 字纯文本，包含：基本信息/年龄职业教育所在地、人物背景与事件关联、性格特征与情绪表达、社媒行为与语言风格、立场观点、独特特征、个人记忆——该个体在事件中的已有动作与反应）
3. age：整数年龄
4. gender：英文 "male" 或 "female"
5. mbti：MBTI 类型（如 INTJ）
6. country：国家（中文，如"中国"）
7. profession：职业
8. interested_topics：感兴趣话题数组
9. activity_level：0.0-1.0 之间的活跃度

重要：字段值为字符串或数字，不用换行符；persona 为连贯文字；gender 用英文；内容与实体信息保持一致。"""


def _group_prompt(name: str, etype: str, summary: str, context: str) -> str:
    return f"""为下列机构/群体实体生成详细的社交媒体官方账号设定，最大程度还原已有现实情况。

实体名称：{name}
实体类型：{etype}
实体摘要：{summary or '（无）'}

上下文信息：
{context[:3000] or '（无额外上下文）'}

请生成 JSON，包含字段：
1. bio：官方账号简介（约 200 字，专业得体）
2. persona：详细账号设定（约 1500-2000 字纯文本，包含：机构基本信息/性质/职能、账号定位与受众、发言风格与禁忌、发布内容特点、对核心话题的官方立场与争议处理、代表的群体画像、机构记忆——该机构在事件中的已有动作与反应）
3. age：固定 30（机构虚拟年龄）
4. gender：固定 "other"
5. mbti：描述账号风格的 MBTI（如 ISTJ 代表严谨保守）
6. country：国家（中文）
7. profession：机构职能描述
8. interested_topics：关注领域数组
9. activity_level：0.0-1.0 之间的活跃度

重要：字段值为字符串或数字，不用 null；persona 为连贯文字；gender 用英文 "other"；age 为整数 30。"""


def _repair_json(content: str) -> dict | None:
    """尝试修复被截断/包裹的 JSON。"""
    if not content:
        return None
    s = content.strip()
    # 去除 markdown 代码块围栏
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```$", "", s)
    s = s.strip()
    # 直接解析
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        pass
    # 截取首个 { 到末个 }
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(s[start:end + 1])
        except json.JSONDecodeError:
            pass
    # 截断修复：补齐未闭合的引号/括号
    fixed = s[start:] if start != -1 else s
    if fixed and fixed[-1] not in '"}]':
        fixed += '"'
    fixed += "]" * max(0, fixed.count("[") - fixed.count("]"))
    fixed += "}" * max(0, fixed.count("{") - fixed.count("}"))
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        return None


def _rule_based(name: str, etype: str, summary: str) -> dict:
    """按实体类型的规则兜底人设。"""
    et = (etype or "").lower()
    if et in ("student", "alumni"):
        return {"bio": f"{name}，关注学业与社会议题的{etype}。",
                "persona": f"{name} 是一名{etype}，活跃于校园与社会话题讨论，乐于分享观点、与同龄人交流。",
                "age": random.randint(18, 30), "gender": random.choice(["male", "female"]),
                "mbti": random.choice(MBTI_TYPES), "country": "中国",
                "profession": "学生", "interested_topics": ["教育", "社会议题", "科技"],
                "activity_level": 0.7}
    if et in ("publicfigure", "celebrity", "expert", "faculty", "professor"):
        return {"bio": f"{name}，在其领域具有影响力的意见领袖。",
                "persona": f"{name} 是受认可的{etype}，在公共讨论中分享专业见解与立场，具有较强影响力。",
                "age": random.randint(35, 60), "gender": random.choice(["male", "female"]),
                "mbti": random.choice(["ENTJ", "INTJ", "ENTP", "INTP"]), "country": "中国",
                "profession": etype, "interested_topics": ["政治", "经济", "文化与社会"],
                "activity_level": 0.8}
    if et in ("mediaoutlet",):
        return {"bio": f"{name} 官方账号，发布新闻与动态。",
                "persona": f"{name} 是媒体机构，报道新闻、促进公共讨论，及时发布更新并与受众互动。",
                "age": 30, "gender": "other", "mbti": "ISTJ", "country": "中国",
                "profession": "媒体", "interested_topics": ["新闻", "时事", "公共事务"],
                "activity_level": 0.9}
    if et in GROUP_ENTITY_TYPES:
        return {"bio": f"{name} 的官方账号。",
                "persona": f"{name} 是机构主体，发布官方立场与公告，就相关议题与利益相关方互动。",
                "age": 30, "gender": "other", "mbti": "ISTJ", "country": "中国",
                "profession": etype, "interested_topics": ["公共政策", "社区", "官方公告"],
                "activity_level": 0.6}
    return {"bio": (summary[:150] if summary else f"{name}"),
            "persona": summary or f"{name} 参与社会讨论。",
            "age": random.randint(25, 50), "gender": random.choice(["male", "female"]),
            "mbti": random.choice(MBTI_TYPES), "country": "中国",
            "profession": etype, "interested_topics": ["综合", "社会议题"],
            "activity_level": 0.5}


def _generate_one(entity: dict, graph_id: str | None = None) -> dict:
    """为单个实体生成人设（LLM → JSON 修复 → 规则兜底）。"""
    name = entity.get("name") or "Agent"
    etype = _entity_type(entity)
    summary = entity.get("summary") or ""
    context = _enrich_context(entity)

    data: dict | None = None
    try:
        # 人设生成量大且可并行，优先走加速模型（未配置时自动回落主模型）
        client = get_llm_client(boost=True)
        prompt = (_individual_prompt if _is_individual(etype) else _group_prompt)(
            name, etype, summary, context)
        # 用 chat + json_object，便于对截断/包裹做修复（persona 较长，放宽 max_tokens）
        raw = client.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT_BASE},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=3000,
        )
        data = _repair_json(raw)
    except Exception as e:  # noqa: BLE001
        logger.warning("生成人设 LLM 调用失败：%s", e)

    if not isinstance(data, dict) or not (data.get("bio") or data.get("persona")):
        logger.info("实体 %s 使用规则兜底人设", name)
        data = _rule_based(name, etype, summary)

    data["name"] = name
    data["entity_uuid"] = entity.get("uuid")
    data["source_entity_type"] = etype
    return _normalize_for_oasis(data, entity)


def _normalize_for_oasis(data: dict, entity: dict) -> dict:
    """补齐 OASIS 加载 Agent 图所需的字段（Twitter/Reddit 双平台）。"""
    name = (entity.get("name") or data.get("name") or "").strip()
    uid = (entity.get("uuid") or "")[:6] or "x"
    data["name"] = name or "Agent"
    data["username"] = data.get("username") or name or f"user_{uid}"
    data["bio"] = (data.get("bio") or entity.get("summary")
                   or f"{data['name']}，模拟世界中的一员。").strip()
    data["persona"] = (data.get("persona") or data["bio"]).strip()
    data["mbti"] = (data.get("mbti") or "INTJ").strip() or "INTJ"
    # profession → occupation（兼容下游），interested_topics → interests
    data["occupation"] = (data.get("occupation")
                          or data.get("profession") or "").strip()
    interests = data.get("interests")
    if not isinstance(interests, list) or not interests:
        interests = data.get("interested_topics")
    data["interests"] = interests if isinstance(interests, list) else []
    data["gender"] = _normalize_gender(data.get("gender"))
    try:
        data["age"] = int(data.get("age") or 30)
    except (ValueError, TypeError):
        data["age"] = 30
    data["country"] = (str(data.get("country") or "中国")).strip() or "中国"
    try:
        data["activity_level"] = float(data.get("activity_level", 0.5))
    except (ValueError, TypeError):
        data["activity_level"] = 0.5
    return data


def _normalize_gender(gender) -> str:
    """标准化性别为 OASIS 要求的 male/female/other。"""
    g = str(gender or "").lower().strip()
    mapping = {"男": "male", "女": "female", "机构": "other", "其他": "other",
               "male": "male", "female": "female", "other": "other"}
    return mapping.get(g, "other" if not g else g if g in ("male", "female") else "other")


def generate_profiles(entities: list[dict], graph_id: str | None = None,
                      concurrency: int = DEFAULT_CONCURRENCY,
                      on_each=None) -> list[dict]:
    """并行为多个实体生成人设。

    :param on_each: 可选回调 (profile:dict) -> None，每完成一个人设即回调，
        供环境搭建阶段实时流式展示（ 的人设实时生成）。
    """
    if not entities:
        return []
    profiles: list[dict | None] = [None] * len(entities)  # 预分配保持顺序
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as executor:
        futures = {executor.submit(_generate_one, e, graph_id): i
                   for i, e in enumerate(entities)}
        # 按完成顺序消费，便于实时回调（最终列表仍按原始顺序）
        for f in as_completed(futures):
            i = futures[f]
            try:
                profiles[i] = f.result()
            except Exception as e:  # noqa: BLE001
                logger.warning("人设生成异常，使用规则兑底：%s", e)
                ent = entities[i]
                profiles[i] = _normalize_for_oasis(
                    _rule_based(ent.get("name") or "Agent",
                                _entity_type(ent), ent.get("summary") or ""),
                    ent,
                )
            if on_each:
                try:
                    on_each(profiles[i])
                except Exception:  # noqa: BLE001
                    pass
    logger.info("共生成 %d 个 Agent 人设", len(profiles))
    # 防御性过滤：剔除极端情况下可能残留的 None，保证返回均为 dict
    return [p for p in profiles if p]


def to_reddit_json(profiles: list[dict]) -> list[dict]:
    """输出 Reddit JSON 格式（对齐 OASIS generate_reddit_agent_graph 所需字段）。"""
    out = []
    for idx, p in enumerate(profiles):
        q = dict(p)
        q["user_id"] = p.get("user_id", idx)  # OASIS 匹配 poster_agent_id 的关键字段
        q["username"] = p.get("username") or p.get("name") or f"user_{idx}"
        q["bio"] = p.get("bio") or ""
        q["persona"] = p.get("persona") or q["bio"] or ""
        q["mbti"] = p.get("mbti") or "INTJ"
        q["gender"] = p.get("gender") or "other"
        try:
            q["age"] = int(p.get("age") or 30)
        except (ValueError, TypeError):
            q["age"] = 30
        q["country"] = p.get("country") or "中国"
        out.append(q)
    return out


def to_twitter_csv(profiles: list[dict]) -> str:
    """输出 Twitter CSV 格式（列名与 OASIS generate_twitter_agent_graph 对齐）。"""
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
        # user_char：OASIS 用作 Agent 的人物画像，务必非空；换行替换为空格
        parts = [persona or bio or f"{name}，社交媒体用户。"]
        if occupation:
            parts.append(f"职业：{occupation}")
        if p.get("mbti"):
            parts.append(f"MBTI：{p['mbti']}")
        if interests:
            parts.append(f"兴趣：{interests}")
        user_char = "，".join(parts).replace("\n", " ").replace("\r", " ")
        description = (bio or persona or f"{name}，社交媒体用户。").replace(
            "\n", " ").replace("\r", " ")
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
                p.get("gender", "other"),
                p.get("age", 30),
                p.get("country", "中国"),
            ]
        )
    return buf.getvalue()
