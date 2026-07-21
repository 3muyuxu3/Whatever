"""模拟配置智能生成服务。

完全自动化，无需人工设置参数。采用分步生成策略：
1. 时间配置（模拟周期、时间粒度）
2. 事件配置（初始事件、种子帖子）
3. Agent 配置分批（按平台分配 Agent）
4. 平台配置（Twitter / Reddit 参数）

基于中国作息时间建模：高峰 19-22 点，低谷 0-5 点。
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


def _gen_events(client, requirement: str, profiles: list[dict]) -> list[dict]:
    """生成初始事件/种子帖子，并为其分配合适的发布者 Agent。"""
    names = [p.get("name") for p in profiles][:20]
    try:
        data = client.chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "根据预测需求生成 2-3 条初始种子帖子，输出 JSON："
                        '{"posts":[{"content":"...","suggested_author":"从候选人中选择"}]}'
                    ),
                },
                {
                    "role": "user",
                    "content": f"预测需求：{requirement}\n候选发布者：{names}",
                },
            ]
        )
        posts = data.get("posts") or []
    except Exception as e:  # noqa: BLE001
        logger.warning("事件生成失败，使用兜底：%s", e)
        posts = [{"content": requirement, "suggested_author": names[0] if names else None}]

    # 将建议作者映射到实际 profile
    name_to_uuid = {p.get("name"): p.get("entity_uuid") for p in profiles}
    for post in posts:
        author = post.get("suggested_author")
        post["author_uuid"] = name_to_uuid.get(author)
    return posts


def _assign_agents(profiles: list[dict]) -> dict:
    """按平台分配 Agent（简单交替分配到 Twitter / Reddit）。"""
    twitter, reddit = [], []
    for i, p in enumerate(profiles):
        (twitter if i % 2 == 0 else reddit).append(p.get("entity_uuid") or p.get("name"))
    return {"twitter": twitter, "reddit": reddit}


def generate_config(project, profiles: list[dict], requirement: str,
                    max_rounds: int | None = None) -> dict:
    """生成完整模拟配置。"""
    client = get_llm_client() if config.has_llm() else None
    max_rounds = max_rounds or config.OASIS_DEFAULT_MAX_ROUNDS

    # 1) 时间配置
    time_config = {
        "max_rounds": max_rounds,
        "time_granularity_minutes": 60,
        "activity_curve": ACTIVITY_CURVE,
    }

    # 2) 事件配置
    events = _gen_events(client, requirement, profiles) if client else [
        {"content": requirement, "author_uuid": None}
    ]

    # 3) Agent 分批
    agents = _assign_agents(profiles)

    # 4) 平台配置
    platforms = {
        "twitter": {"enabled": True, "recsys": "twhin-bert", "max_rec_post": 20},
        "reddit": {"enabled": True, "recsys": "reddit", "max_rec_post": 20},
    }

    return {
        "time": time_config,
        "events": events,
        "agents": agents,
        "platforms": platforms,
    }
