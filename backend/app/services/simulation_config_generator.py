"""模拟配置智能生成服务。

 的分步 LLM 生成策略，同时保持对 oasis_runner / action_logger 的后向兼容：
1. 时间配置（模拟周期、时间粒度、活跃度曲线、高峰/低谷时段）
2. 事件配置（热点话题、舆论引导方向、初始种子帖，按实体类型智能分配发布者）
3. Agent 活跃配置（逐 Agent 的活跃度/发言频率/情感倾向/立场/影响力权重，规则派生）
4. 平台配置（Twitter / Reddit 推荐权重、病毒阈值、回声室强度）

基于中国作息建模：高峰 19-22 点，低谷 0-5 点。

输出结构在 丰富度基础上保留兼容键：
- time.max_rounds / time.activity_curve
- events[].content / events[].author_uuid
- agents.twitter / agents.reddit（Agent id 列表）
- platforms.twitter / platforms.reddit
"""

from ..config import config
from ..utils.llm_client import get_llm_client
from ..utils.logger import get_logger

logger = get_logger("sim_config")

# 中国作息活跃度曲线（24 小时，0-1），高峰 19-22 点，低谷 0-5 点
ACTIVITY_CURVE = [
    0.15, 0.08, 0.05, 0.05, 0.05, 0.08,  # 0-5 低谷
    0.20, 0.45, 0.60, 0.55, 0.55, 0.60,  # 6-11
    0.65, 0.55, 0.55, 0.60, 0.62, 0.70,  # 12-17
    0.80, 0.95, 1.00, 0.95, 0.70, 0.40,  # 18-23 高峰在 19-22
]

PEAK_HOURS = [19, 20, 21, 22]
OFF_PEAK_HOURS = [0, 1, 2, 3, 4, 5]

# 机构/意见领袖类实体（初始帖发布者优先、影响力更高）
_ORG_TYPES = {"organization", "governmentagency", "mediaoutlet", "company",
              "university", "ngo", "institution", "school", "hospital"}
_LEADER_TYPES = {"official", "publicfigure", "celebrity", "expert",
                 "professor", "journalist", "executive", "ceo"}


def _profile_type(p: dict) -> str:
    return (p.get("source_entity_type") or p.get("type") or "").lower()


def _gen_event_config(client, requirement: str, profiles: list[dict]) -> dict:
    """LLM 生成事件配置：热点话题、舆论方向、初始种子帖（含建议发布者）。"""
    names = [p.get("name") for p in profiles if p.get("name")][:20]
    default = {
        "hot_topics": [],
        "narrative_direction": "",
        "posts": [{"content": requirement, "suggested_author": names[0] if names else None}],
    }
    if not client:
        return default
    try:
        data = client.chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "你是舆论模拟事件设计专家。根据预测需求设计模拟初始事件，输出 JSON：\n"
                        '{"hot_topics":["话题1","话题2"],"narrative_direction":"舆论引导方向一句话",'
                        '"posts":[{"content":"初始种子帖文本","suggested_author":"从候选人中选择最合适的发布者"}]}\n'
                        "要求：hot_topics 3-6 个；posts 2-3 条，内容贴合预测需求、具备引爆性；"
                        "suggested_author 必须从候选发布者中选择。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"预测需求：{requirement}\n候选发布者：{names}",
                },
            ]
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("事件配置生成失败，使用兜底：%s", e)
        return default

    posts = data.get("posts")
    if not isinstance(posts, list):
        posts = []
    posts = [p for p in posts if isinstance(
        p, dict) and (p.get("content") or "").strip()]
    if not posts:
        posts = default["posts"]
    return {
        "hot_topics": [str(t) for t in (data.get("hot_topics") or []) if str(t).strip()][:6],
        "narrative_direction": (data.get("narrative_direction") or "").strip(),
        "posts": posts,
    }


def _assign_seed_authors(posts: list[dict], profiles: list[dict]) -> list[dict]:
    """将种子帖的建议作者映射到实际 profile，并标注发布者类型；无匹配时优先机构/意见领袖。"""
    name_to_profile = {p.get("name"): p for p in profiles}
    # 优先发布者候选（机构 > 意见领袖 > 其他）
    ordered = sorted(
        profiles,
        key=lambda p: (0 if _profile_type(p) in _ORG_TYPES else
                       1 if _profile_type(p) in _LEADER_TYPES else 2),
    )
    fallback_idx = 0
    out = []
    for post in posts:
        author = post.get("suggested_author")
        prof = name_to_profile.get(author)
        if not prof and ordered:
            prof = ordered[min(fallback_idx, len(ordered) - 1)]
            fallback_idx += 1
        out.append({
            "content": post.get("content", ""),
            "suggested_author": (prof or {}).get("name") if prof else author,
            "author_uuid": (prof or {}).get("entity_uuid"),
            "poster_type": _profile_type(prof) if prof else "",
        })
    return out


def _agent_configs(profiles: list[dict]) -> list[dict]:
    """逐 Agent 派生活跃配置：活跃度/发言频率/情感/立场/影响力（规则派生，零 LLM）。"""
    configs = []
    for i, p in enumerate(profiles):
        etype = _profile_type(p)
        try:
            activity = float(p.get("activity_level", 0.5))
        except (ValueError, TypeError):
            activity = 0.5
        # 影响力：机构/意见领袖更高
        if etype in _ORG_TYPES:
            influence = 1.6
        elif etype in _LEADER_TYPES:
            influence = 1.4
        else:
            influence = 1.0
        configs.append({
            "agent_id": i,
            "entity_uuid": p.get("entity_uuid"),
            "entity_name": p.get("name"),
            "entity_type": etype,
            "activity_level": round(activity, 2),
            "posts_per_hour": round(0.5 + activity * 1.5, 2),
            "comments_per_hour": round(1.0 + activity * 2.0, 2),
            "sentiment_bias": 0.0,      # 中性默认，交由 LLM Agent 在模拟中自主表达
            "stance": "neutral",         # supportive / opposing / neutral / observer
            "influence_weight": influence,
            "active_hours": list(range(8, 23)),
        })
    return configs


def _assign_agents(profiles: list[dict]) -> dict:
    """按平台分配 Agent（交替分配到 Twitter / Reddit）。"""
    twitter, reddit = [], []
    for i, p in enumerate(profiles):
        (twitter if i % 2 == 0 else reddit).append(
            p.get("entity_uuid") or p.get("name"))
    return {"twitter": twitter, "reddit": reddit}


def _platform_config(name: str, recsys: str) -> dict:
    """平台配置（保留 enabled/recsys/max_rec_post，并补充推荐权重与传播参数）。"""
    return {
        "enabled": True,
        "recsys": recsys,
        "max_rec_post": 20,
        "recency_weight": 0.4,
        "popularity_weight": 0.3,
        "relevance_weight": 0.3,
        "viral_threshold": 10,
        "echo_chamber_strength": 0.5,
    }


def generate_config(project, profiles: list[dict], requirement: str,
                    max_rounds: int | None = None) -> dict:
    """生成完整模拟配置（LLM 分步 + 规则派生，保持后向兼容）。"""
    # 事件/热点等非质量关键生成，优先走加速模型（未配置时自动回落主模型）
    client = get_llm_client(boost=True) if config.has_llm() else None
    max_rounds = max_rounds or config.OASIS_DEFAULT_MAX_ROUNDS

    # 1) 时间配置
    minutes_per_round = 60
    time_config = {
        "max_rounds": max_rounds,
        "time_granularity_minutes": minutes_per_round,
        "activity_curve": ACTIVITY_CURVE,
        "total_simulation_hours": int(max_rounds * minutes_per_round / 60),
        "minutes_per_round": minutes_per_round,
        "peak_hours": PEAK_HOURS,
        "off_peak_hours": OFF_PEAK_HOURS,
    }

    # 2) 事件配置（热点话题 + 舆论方向 + 种子帖）
    ev = _gen_event_config(client, requirement, profiles)
    events = _assign_seed_authors(ev["posts"], profiles) if profiles else [
        {"content": requirement, "author_uuid": None, "poster_type": ""}
    ]
    event_config = {
        "hot_topics": ev["hot_topics"],
        "narrative_direction": ev["narrative_direction"],
        "scheduled_events": [],
    }

    # 3) Agent 活跃配置 + 平台分配
    agent_configs = _agent_configs(profiles)
    agents = _assign_agents(profiles)

    # 4) 平台配置
    platforms = {
        "twitter": _platform_config("twitter", "twhin-bert"),
        "reddit": _platform_config("reddit", "reddit"),
    }

    reasoning = (
        f"依据预测需求「{requirement[:60]}」与 {len(profiles)} 个 Agent 生成："
        f"共 {len(events)} 条种子帖、{len(event_config['hot_topics'])} 个热点话题；"
        f"按中国作息建模活跃度（高峰 19-22 点），机构/意见领袖影响力权重更高。"
    )

    return {
        "time": time_config,
        "events": events,
        "event_config": event_config,
        "agents": agents,
        "agent_configs": agent_configs,
        "platforms": platforms,
        "generation_reasoning": reasoning,
    }
