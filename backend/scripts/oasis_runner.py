"""真实 OASIS 模拟运行器（独立子进程内使用）。

基于 CAMEL-AI 的 OASIS 引擎运行真实的社交模拟：读取环境准备阶段生成的
Agent 人设（profiles_twitter.csv / profiles_reddit.json），构建 Agent 图谱，
以 LLM 驱动多轮社交交互，并将动作实时桥接写入 actions.jsonl，供前端流式展示
与报告生成复用。同时支持：
- 上帝视角动态注入（每轮消费 injections 目录，作为新种子帖子注入）；
- 运行中实时采访（复用文件系统 IPC）。

任何环节失败都会抛出异常，交由调用方回退到降级模拟循环（保证端到端可运行）。

注意：本模块被独立子进程运行/导入，因此不依赖 app 包；camel / oasis 均惰性导入。
"""

import asyncio
import json
import os
import sqlite3
import time

from action_logger import ActionLogger, _handle_interviews, _maybe_llm, _poll_injections


def _build_model():
    """依据环境变量构建 camel 模型后端（OpenAI 兼容格式）。"""
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType

    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 LLM_API_KEY，无法运行真实 OASIS 模拟")
    base_url = os.getenv(
        "LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    model_name = os.getenv("LLM_MODEL_NAME", "qwen-plus")
    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type=model_name,
        url=base_url,
        api_key=api_key,
        model_config_dict={"temperature": 0.8, "max_tokens": 512},
    )


def _available_actions(platform: str):
    """各平台可用动作集合（映射到 OASIS ActionType）。"""
    from oasis import ActionType as A

    common = [
        A.CREATE_POST, A.LIKE_POST, A.REPOST, A.FOLLOW,
        A.CREATE_COMMENT, A.LIKE_COMMENT, A.DO_NOTHING,
    ]
    if platform == "twitter":
        return common + [A.QUOTE_POST]
    return common + [
        A.DISLIKE_POST, A.DISLIKE_COMMENT, A.SEARCH_POSTS,
        A.SEARCH_USER, A.TREND, A.REFRESH, A.MUTE,
    ]


def _profile_path(platform: str, work_dir: str) -> str:
    name = "profiles_twitter.csv" if platform == "twitter" else "profiles_reddit.json"
    path = os.path.join(work_dir, name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"未找到人设文件：{path}")
    return path


def _table_columns(conn, table: str) -> list[str]:
    try:
        cur = conn.execute(f"PRAGMA table_info({table})")
        return [row[1] for row in cur.fetchall()]
    except sqlite3.Error:
        return []


def _load_user_names(conn) -> dict:
    """从 user 表构建 user_id -> 展示名 的映射（尽力而为）。"""
    cols = _table_columns(conn, "user")
    if not cols:
        return {}
    id_col = "user_id" if "user_id" in cols else (
        "agent_id" if "agent_id" in cols else cols[0])
    name_col = next(
        (c for c in ("user_name", "name", "real_name") if c in cols), None)
    if not name_col:
        return {}
    names = {}
    try:
        for uid, uname in conn.execute(f"SELECT {id_col}, {name_col} FROM user"):
            names[uid] = uname
    except sqlite3.Error:
        pass
    return names


def _bridge_new_actions(db_path: str, logger: ActionLogger, platform: str,
                        rnd: int, last_rowid: int) -> int:
    """将 OASIS 数据库 trace 表中的新动作桥接写入 actions.jsonl，返回新的 rowid 游标。"""
    if not os.path.exists(db_path):
        return last_rowid
    conn = sqlite3.connect(db_path)
    try:
        if not _table_columns(conn, "trace"):
            return last_rowid
        names = _load_user_names(conn)
        rows = conn.execute(
            "SELECT rowid, user_id, action, info FROM trace WHERE rowid > ? ORDER BY rowid",
            (last_rowid,),
        ).fetchall()
        for rowid, user_id, action, info in rows:
            last_rowid = max(last_rowid, rowid)
            content = ""
            if info:
                try:
                    parsed = json.loads(info) if isinstance(
                        info, str) else info
                    if isinstance(parsed, dict):
                        content = parsed.get(
                            "content") or parsed.get("text") or ""
                except (ValueError, TypeError):
                    content = str(info)[:280] if not str(
                        info).startswith("{") else ""
            logger.log(
                round=rnd,
                platform=platform,
                agent_id=str(user_id),
                agent_name=str(names.get(user_id, user_id)),
                action=str(action or "").upper(),
                content=content,
            )
    finally:
        conn.close()
    return last_rowid


async def _run_platform_async(platform: str, sim_id: str, cfg: dict, work_dir: str) -> None:
    """在单一平台上运行真实 OASIS 模拟。"""
    import oasis
    from oasis import (
        ActionType,
        DefaultPlatformType,
        LLMAction,
        ManualAction,
        generate_reddit_agent_graph,
        generate_twitter_agent_graph,
    )

    model = _build_model()
    profile_path = _profile_path(platform, work_dir)
    available = _available_actions(platform)

    if platform == "twitter":
        agent_graph = await generate_twitter_agent_graph(
            profile_path=profile_path, model=model, available_actions=available
        )
        ptype = DefaultPlatformType.TWITTER
    else:
        agent_graph = await generate_reddit_agent_graph(
            profile_path=profile_path, model=model, available_actions=available
        )
        ptype = DefaultPlatformType.REDDIT

    db_path = os.path.join(work_dir, f"oasis_{platform}.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    env = oasis.make(agent_graph=agent_graph,
                     platform=ptype, database_path=db_path)
    await env.reset()

    logger = ActionLogger(os.path.join(work_dir, "actions.jsonl"))
    llm = _maybe_llm()
    last_rowid = 0

    time_cfg = cfg.get("time", {})
    max_rounds = int(time_cfg.get("max_rounds", 10))

    # 初始种子帖子：由第一个 Agent 以 ManualAction 发布
    first_agent = agent_graph.get_agent(0)
    for event in cfg.get("events", []) or []:
        content = event.get("content", "")
        if not content:
            continue
        await env.step({
            first_agent: ManualAction(
                action_type=ActionType.CREATE_POST, action_args={
                    "content": content}
            )
        })
        logger.log(round=0, platform=platform, agent_id="seed",
                   agent_name="seed", action="CREATE_POST", content=content)

    for rnd in range(max_rounds):
        # 上帝视角：将新注入作为种子帖子注入真实模拟
        for inj in _poll_injections(work_dir):
            c = (inj.get("content") or "").strip()
            if not c:
                continue
            await env.step({
                first_agent: ManualAction(
                    action_type=ActionType.CREATE_POST, action_args={
                        "content": c}
                )
            })
            logger.log(round=rnd, platform=inj.get("platform") or platform,
                       agent_id="godview", agent_name="God View",
                       action="INJECT", content=c)

        # LLM 驱动的一轮社交交互
        actions = {agent: LLMAction() for _, agent in agent_graph.get_agents()}
        await env.step(actions)

        # 将本轮真实动作桥接到 actions.jsonl
        last_rowid = _bridge_new_actions(
            db_path, logger, platform, rnd, last_rowid)

        # 运行中实时采访（复用文件系统 IPC）
        _handle_interviews(work_dir, {}, llm)

    await env.close()


def run_real_simulation(platforms: list[str], sim_id: str, cfg: dict, work_dir: str) -> None:
    """运行真实 OASIS 模拟（可能多平台）。任何异常都会向上抛出以触发回退。"""
    async def _main():
        for platform in platforms:
            await _run_platform_async(platform, sim_id, cfg, work_dir)

    asyncio.run(_main())
