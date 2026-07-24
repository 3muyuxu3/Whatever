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
import logging
import os
import sqlite3
import time

from action_logger import (
    ActionLogger,
    WAIT_IDLE_TIMEOUT,
    _check_close,
    _handle_interviews,
    _load_profiles,
    _maybe_llm,
    _persona_answer,
    _poll_injections,
    _write_env_status,
)


class MaxTokensWarningFilter(logging.Filter):
    """过滤 camel-ai 关于 max_tokens 的告警（-main）。

    我们故意不在 model_config_dict 中设置 max_tokens（见 _build_model），让模型
    自行决定输出长度，同时避免 CAMEL 把 max_tokens 误用作 token_limit（上下文窗口
    上限）导致 Agent 人设 system message 超限而抛 "System message alone exceeds
    token limit"。CAMEL 会因缺失 max_tokens 打印一条 "Invalid or missing
    `max_tokens`..." 告警，这里将其过滤掉。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not ("max_tokens" in msg and "Invalid or missing" in msg)


# 在模块加载时立即注册过滤器：camel 通过 logging.warning 向根 logger 输出该告警，
# 且本模块在真实模拟启动（run_real_simulation）前即被导入，可确保在任何 camel
# 代码执行前生效。
logging.getLogger().addFilter(MaxTokensWarningFilter())


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
    # 不设置 max_tokens：CAMEL 会把 model_config_dict 中的 max_tokens 同时当作
    # token_limit（上下文窗口上限）。若设成 512，Agent 人设 system message
    # （约 650~700 token）会超限并抛 "System message alone exceeds token limit"，
    # 导致真实 Agent 采访失败而降级。-main：不设置 max_tokens，
    # 让模型自行决定输出长度；由 MaxTokensWarningFilter 过滤随之产生的告警。
    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type=model_name,
        url=base_url,
        api_key=api_key,
        model_config_dict={"temperature": 0.8},
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
    """从 user 表构建 user_id -> 展示名 的映射（尽力而为，跳过空/None）。"""
    cols = _table_columns(conn, "user")
    if not cols:
        return {}
    id_col = "user_id" if "user_id" in cols else (
        "agent_id" if "agent_id" in cols else cols[0])
    # 优先真实姓名，其次用户名；逐行取第一个非空值，避免某列为 NULL 时记成 "None"
    name_cols = [c for c in ("name", "real_name", "user_name", "username")
                 if c in cols]
    if not name_cols:
        return {}
    names = {}
    try:
        sel = ", ".join([id_col] + name_cols)
        for row in conn.execute(f"SELECT {sel} FROM user"):
            uid = row[0]
            uname = next(
                (v for v in row[1:] if v not in (None, "", "None", "null")), None)
            if uname is not None:
                names[uid] = uname
    except sqlite3.Error:
        pass
    return names


def _resolve_agent_name(names: dict, profiles: list | None, user_id) -> str:
    """解析 Agent 展示名：优先 DB 名，其次人设名（按索引），最后回退 Agent {id}。

    修复「活跃 Agent 排行显示 None」：OASIS user 表姓名列可能为 NULL，
    直接 str() 会得到 "None"。
    """
    raw = names.get(user_id)
    if raw not in (None, "", "None", "null"):
        return str(raw)
    if profiles:
        idx = user_id if isinstance(user_id, int) else (
            int(user_id) if str(user_id).isdigit() else None)
        if idx is not None and 0 <= idx < len(profiles):
            p = profiles[idx]
            nm = p.get("name") or p.get("username")
            if nm:
                return str(nm)
    return f"Agent {user_id}"


def _bridge_new_actions(db_path: str, logger: ActionLogger, platform: str,
                        rnd: int, last_rowid: int, profiles: list | None = None) -> int:
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
                agent_name=_resolve_agent_name(names, profiles, user_id),
                action=str(action or "").upper(),
                content=content,
            )
    finally:
        conn.close()
    return last_rowid


async def _run_platform_async(platform: str, sim_id: str, cfg: dict, work_dir: str) -> dict:
    """在单一平台上运行真实 OASIS 模拟，返回含 env / agent_graph / db_path 的状态字典。"""
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

    if platform == "twitter":
        # OASIS 对 Twitter 默认使用 twhin-bert recsys（从 HuggingFace 下载 twhin-bert-base），
        # RecsysType.TWITTER 则依赖 paraphrase-MiniLM-L6-v2；两者在国内均因无法访问
        # huggingface.co 而反复超时卡死。改用 RANDOM recsys（不加载任何模型，
        # 且仍保持 platform_type=TWITTER），彻底规避 HuggingFace 依赖。
        from oasis.social_platform.channel import Channel
        from oasis.social_platform.platform import Platform

        twitter_platform = Platform(
            db_path=db_path,
            channel=Channel(),
            recsys_type="random",
            refresh_rec_post_count=2,
            max_rec_post_len=2,
            following_post_count=3,
        )
        env = oasis.make(agent_graph=agent_graph,
                         platform=twitter_platform, database_path=db_path)
    else:
        env = oasis.make(agent_graph=agent_graph,
                         platform=ptype, database_path=db_path)
    await env.reset()

    logger = ActionLogger(os.path.join(work_dir, "actions.jsonl"))
    llm = _maybe_llm()
    last_rowid = 0
    # 人设列表用于回退解析 Agent 展示名（OASIS user 表姓名列可能为空）
    profiles = _load_profiles(work_dir)

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
            db_path, logger, platform, rnd, last_rowid, profiles)

        # 运行中实时采访（轮次期间暂用贴合人设快速应答；回合完成后的等待循环采用真实 Agent 采访）
        _handle_interviews(work_dir, llm)

    # 注意：不在此处关闭环境，交由 run_real_simulation 的等待循环结束后统一关闭，
    # 以便环境常驻接受真实 Agent 采访。
    return {
        "platform": platform,
        "env": env,
        "agent_graph": agent_graph,
        "db_path": db_path,
    }


def _resolve_agent_index(profiles: list, agent_id) -> int:
    """将 SimulMirror 的 agent_id（entity_uuid / name / 索引字符串）解析为 OASIS Agent 索引。"""
    aid = str(agent_id) if agent_id is not None else ""
    if aid.isdigit():
        return int(aid)
    for i, p in enumerate(profiles or []):
        if p.get("entity_uuid") == aid or p.get("name") == aid or p.get("username") == aid:
            return i
    return 0


def _read_interview_result(db_path: str, agent_id: int) -> str:
    """从 OASIS 数据库 trace 表读取最新一条采访回答。"""
    if not os.path.exists(db_path):
        return ""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "SELECT info FROM trace WHERE lower(action)='interview' AND user_id=? "
            "ORDER BY created_at DESC LIMIT 1",
            (agent_id,),
        )
        row = cur.fetchone()
        if not row or row[0] is None:
            return ""
        info = row[0]
        try:
            d = json.loads(info) if isinstance(info, str) else info
            if isinstance(d, dict):
                return str(d.get("response") or d.get("content") or d.get("text") or "")
            return str(info)
        except (ValueError, TypeError):
            return str(info)
    except sqlite3.Error:
        return ""
    finally:
        conn.close()


# 采访提问前缀：引导真实 OASIS Agent 直接用文本作答，不去调用工具（发帖/搜索等），
INTERVIEW_PROMPT_PREFIX = "结合你的人设、所有的过往记忆与行动，不调用任何工具，直接用文本回复我："


def _with_interview_prefix(prompt: str) -> str:
    """为采访提问加上「不调工具、直接作答」前缀，避免真实 Agent 在采访中触发发帖/搜索等动作。"""
    p = (prompt or "").strip()
    if not p or p.startswith(INTERVIEW_PROMPT_PREFIX):
        return p
    return f"{INTERVIEW_PROMPT_PREFIX}{p}"


async def _interview_one(state: dict, agent_index: int, prompt: str) -> str:
    """在单个平台对真实 Agent 发起采访（ManualAction(INTERVIEW)）并从 DB 读回答。"""
    from oasis import ActionType, ManualAction

    interview_action = getattr(ActionType, "INTERVIEW", None)
    if interview_action is None:
        raise RuntimeError("当前 OASIS 版本不支持 INTERVIEW 动作")
    agent = state["agent_graph"].get_agent(agent_index)
    await state["env"].step({
        agent: ManualAction(action_type=interview_action,
                            action_args={"prompt": _with_interview_prefix(prompt)})
    })
    return _read_interview_result(state["db_path"], agent_index)


async def _answer_interview(states: dict, profiles: list, agent_id, question: str, llm) -> str:
    """优先真实 Agent 采访（首个可用平台）；失败时降级为贴合人设的 LLM 作答。"""
    idx = _resolve_agent_index(profiles, agent_id)
    for platform, st in states.items():
        try:
            ans = await _interview_one(st, idx, question)
            if ans and ans.strip():
                return ans.strip()
        except Exception as e:  # noqa: BLE001
            print(f"[interview] 真实采访失败({platform})，尝试下一平台/降级：{e}")
    return _persona_answer(profiles, agent_id, question, llm)


async def _real_wait_loop(states: dict, work_dir: str) -> None:
    """真实环境常驻等待循环：处理 IPC 采访请求（真实 Agent），直到 close 或空闲超时。"""
    profiles = _load_profiles(work_dir)
    platforms = list(states.keys())
    llm = _maybe_llm()
    ipc = os.path.join(work_dir, "ipc")
    os.makedirs(ipc, exist_ok=True)
    _write_env_status(work_dir, "alive", platforms)
    print("[env] 真实环境进入等待命令模式（支持实时真实 Agent 采访 / close_env）")
    idle_deadline = time.time() + WAIT_IDLE_TIMEOUT
    try:
        while True:
            if _check_close(work_dir):
                print("[env] 收到关闭命令，退出等待循环")
                break
            handled = 0
            for name in list(os.listdir(ipc)):
                if not (name.startswith("req_") and name.endswith(".json")):
                    continue
                req_path = os.path.join(ipc, name)
                try:
                    with open(req_path, "r", encoding="utf-8") as f:
                        req = json.load(f)
                except Exception:  # noqa: BLE001
                    continue
                req_id = req.get("id")
                if not req_id:
                    try:
                        os.remove(req_path)
                    except OSError:
                        pass
                    continue
                answer = await _answer_interview(
                    states, profiles, req.get("agent_id"), req.get("question", ""), llm)
                with open(os.path.join(ipc, f"resp_{req_id}.json"), "w", encoding="utf-8") as f:
                    json.dump({"id": req_id, "answer": answer,
                              "ts": time.time()}, f, ensure_ascii=False)
                try:
                    os.remove(req_path)
                except OSError:
                    pass
                handled += 1
            if handled:
                idle_deadline = time.time() + WAIT_IDLE_TIMEOUT
            elif time.time() > idle_deadline:
                print("[env] 空闲超时，自动关闭环境")
                break
            else:
                await asyncio.sleep(0.5)
    finally:
        _write_env_status(work_dir, "stopped", platforms)


def run_real_simulation(platforms: list[str], sim_id: str, cfg: dict, work_dir: str) -> None:
    """运行真实 OASIS 模拟（可能多平台），回合完成后环境常驻接受采访。任何异常向上抛出以触发回退。"""
    async def _main():
        # 多平台真正并行运行（Twitter / Reddit 各自独立的 DB 与协程），。
        results = await asyncio.gather(
            *(_run_platform_async(p, sim_id, cfg, work_dir) for p in platforms)
        )
        states = {r["platform"]: r for r in results if r}
        # 回合完成后进入等待命令模式（环境常驻，支持真实 Agent 采访）
        try:
            await _real_wait_loop(states, work_dir)
        finally:
            # 统一关闭所有平台环境
            for st in states.values():
                try:
                    await st["env"].close()
                except Exception:  # noqa: BLE001
                    pass

    asyncio.run(_main())
