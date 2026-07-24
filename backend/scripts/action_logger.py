"""动作日志记录（JSONL 格式）与自包含的模拟循环。

- ActionLogger：线程安全地将每一步动作写入 actions.jsonl。
- 动作类型：分别对应 Twitter 与 Reddit 平台。
- run_mock_simulation：当真实 OASIS 依赖/密钥不可用时的降级模拟循环，
  仍会产出真实的 actions.jsonl 与 Interview 应答，保证端到端流程可运行。

注意：本文件被独立子进程直接运行/导入，因此不依赖 app 包。
"""

import json
import os
import random
import threading
import time

# Twitter 平台动作类型
TWITTER_ACTIONS = [
    "CREATE_POST", "LIKE_POST", "REPOST", "FOLLOW", "DO_NOTHING", "QUOTE_POST",
]

# Reddit 平台动作类型
REDDIT_ACTIONS = [
    "LIKE_POST", "DISLIKE_POST", "CREATE_POST", "CREATE_COMMENT", "LIKE_COMMENT",
    "DISLIKE_COMMENT", "SEARCH_POSTS", "SEARCH_USER", "TREND", "REFRESH",
    "DO_NOTHING", "FOLLOW", "MUTE",
]

ACTIONS_BY_PLATFORM = {"twitter": TWITTER_ACTIONS, "reddit": REDDIT_ACTIONS}


class ActionLogger:
    """将模拟动作追加写入 JSONL 文件（线程安全）。"""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def log(self, **action) -> None:
        action.setdefault("ts", time.time())
        line = json.dumps(action, ensure_ascii=False)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")


def _maybe_llm():
    """尽力创建一个 LLM 调用函数；不可用时返回 None。"""
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url=os.getenv(
                "LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
            ),
        )
        model = os.getenv("LLM_MODEL_NAME", "qwen-plus")

        def _call(prompt: str) -> str:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=80,
            )
            return (resp.choices[0].message.content or "").strip()

        return _call
    except Exception:  # noqa: BLE001
        return None


def _load_profiles(work_dir: str) -> list:
    """读取已生成的 Agent 人设（profiles_reddit.json），供深度采访时贴合人设作答。"""
    path = os.path.join(work_dir, "profiles_reddit.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


def _find_profile(profiles: list, agent_id) -> dict | None:
    """根据 agent_id（entity_uuid / name / 索引）定位对应人设。"""
    if not profiles:
        return None
    aid = str(agent_id) if agent_id is not None else ""
    # 数字索引形式
    if aid.isdigit():
        i = int(aid)
        if 0 <= i < len(profiles):
            return profiles[i]
    for p in profiles:
        if p.get("entity_uuid") == aid or p.get("name") == aid or p.get("username") == aid:
            return p
    return None


def _persona_answer(profiles: list, agent_id, question: str, llm) -> str:
    """贴合人设生成采访回答（降级模拟 / 真实模拟环境不可用时的共用实现）。"""
    profile = _find_profile(profiles, agent_id)
    name = (profile or {}).get("name") or str(agent_id) or "Agent"
    bits = []
    if profile:
        for key in ("bio", "persona", "occupation", "mbti"):
            if profile.get(key):
                bits.append(f"{key}: {profile[key]}")
        if profile.get("interests"):
            bits.append("interests: " + ", ".join(profile["interests"]))
    persona = "\n".join(bits) or "（无额外人设信息）"
    if not llm:
        return f"作为 {name}，我认为「{question}」值得持续关注。"
    prompt = (
        f"你在扮演社交模拟世界中的人物：{name}。\n人设：\n{persona}\n"
        f"请以第一人称、贴合人设地简洁作答（2-4 句）。\n问题：{question}"
    )
    try:
        ans = llm(prompt)
        return ans or f"作为 {name}，我认为「{question}」值得持续关注。"
    except Exception:  # noqa: BLE001
        return f"作为 {name}，我认为「{question}」值得持续关注。"


def _handle_interviews(work_dir: str, llm, profiles: list | None = None) -> int:
    """处理 IPC 目录中的采访请求（贴合人设生成应答并回写），返回处理数。"""
    ipc = os.path.join(work_dir, "ipc")
    if not os.path.isdir(ipc):
        return 0
    profiles = profiles if profiles is not None else _load_profiles(work_dir)
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
            # 请求文件缺少 id（可能写入不完整），跳过并清理
            try:
                os.remove(req_path)
            except OSError:
                pass
            continue
        answer = _persona_answer(
            profiles, req.get("agent_id"), req.get("question", ""), llm)
        with open(os.path.join(ipc, f"resp_{req_id}.json"), "w", encoding="utf-8") as f:
            json.dump({"id": req_id, "answer": answer,
                      "ts": time.time()}, f, ensure_ascii=False)
        try:
            os.remove(req_path)
        except OSError:
            pass
        handled += 1
    return handled


# ---- 环境存活状态 / 关闭信号（ 的环境常驻） ----

def _write_env_status(work_dir: str, status: str, platforms: list) -> None:
    """写入模拟环境状态（alive/stopped），供主进程判断环境是否可接受采访。"""
    try:
        with open(os.path.join(work_dir, "env_status.json"), "w", encoding="utf-8") as f:
            json.dump({
                "status": status,
                "twitter_available": "twitter" in platforms,
                "reddit_available": "reddit" in platforms,
                "ts": time.time(),
            }, f, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass


def _check_close(work_dir: str) -> bool:
    """检查是否收到关闭环境信号（并消费信号文件）。"""
    p = os.path.join(work_dir, "ipc", "close.json")
    if os.path.exists(p):
        try:
            os.remove(p)
        except OSError:
            pass
        return True
    return False


# 等待命令模式的最大空闲时长（秒）：无采访命令超过此时长自动关闭环境，避免孤儿进程
WAIT_IDLE_TIMEOUT = 900


def run_wait_loop(work_dir: str, platforms: list, llm, profiles: list | None = None) -> None:
    """模拟回合完成后进入等待命令模式（环境常驻，）。

    持续处理 IPC 采访请求（贴合人设作答），直到：收到 close 信号 或 长时间空闲。
    """
    profiles = profiles if profiles is not None else _load_profiles(work_dir)
    _write_env_status(work_dir, "alive", platforms)
    print("[env] 进入等待命令模式，环境保持运行（支持采访 / close_env）")
    idle_deadline = time.time() + WAIT_IDLE_TIMEOUT
    try:
        while True:
            if _check_close(work_dir):
                print("[env] 收到关闭命令，退出等待循环")
                break
            handled = _handle_interviews(work_dir, llm, profiles)
            if handled:
                idle_deadline = time.time() + WAIT_IDLE_TIMEOUT
            elif time.time() > idle_deadline:
                print("[env] 空闲超时，自动关闭环境")
                break
            else:
                time.sleep(0.5)
    finally:
        _write_env_status(work_dir, "stopped", platforms)


def _poll_injections(work_dir: str) -> list:
    """读取并消费「上帝视角」注入目录中的新事件 / 变量。

    与主进程侧 simulation_ipc.write_injection 对应；读取后删除文件，确保每条注入
    只被应用一次。
    """
    d = os.path.join(work_dir, "injections")
    if not os.path.isdir(d):
        return []
    items = []
    for name in sorted(os.listdir(d)):
        if not (name.startswith("inj_") and name.endswith(".json")):
            continue
        p = os.path.join(d, name)
        try:
            with open(p, "r", encoding="utf-8") as f:
                items.append(json.load(f))
        except Exception:  # noqa: BLE001
            continue
        try:
            os.remove(p)  # 消费后删除，避免重复注入
        except Exception:  # noqa: BLE001
            pass
    return items


def run_mock_simulation(platforms: list[str], sim_id: str, cfg: dict, work_dir: str) -> None:
    """降级模拟循环：按活跃度曲线为各平台 Agent 生成动作并记录。

    支持「上帝视角」动态注入：每轮开始时消费注入目录中的新事件 / 变量，
    将其作为新的种子话题注入后续社会演化。
    """
    logger = ActionLogger(os.path.join(work_dir, "actions.jsonl"))
    llm = _maybe_llm()
    profiles = _load_profiles(work_dir)

    time_cfg = cfg.get("time", {})
    max_rounds = int(time_cfg.get("max_rounds", 10))
    curve = time_cfg.get("activity_curve") or [0.6] * 24

    agents_cfg = cfg.get("agents", {})
    # 组织每个平台的 Agent 列表（无配置时给出默认 Agent）
    agents = {}
    for p in platforms:
        ids = agents_cfg.get(p) or [f"{p}_agent_{i}" for i in range(5)]
        agents[p] = [{"id": str(a), "name": str(a)} for a in ids]

    # 话题池：由初始种子事件填充，可被「上帝视角」注入动态扩展
    topics = [e.get("content", "")
              for e in (cfg.get("events") or []) if e.get("content")]
    if not topics:
        topics = ["公共议题"]

    # 初始种子帖子
    for event in cfg.get("events", []) or []:
        logger.log(round=0, platform=platforms[0], agent_id="seed",
                   agent_name="seed", action="CREATE_POST", content=event.get("content", ""))

    for rnd in range(max_rounds):
        # 上帝视角：消费本轮新注入的事件 / 变量
        for inj in _poll_injections(work_dir):
            c = (inj.get("content") or "").strip()
            if not c:
                continue
            topics.append(c)
            plat = inj.get("platform") or platforms[0]
            logger.log(round=rnd, platform=plat, agent_id="godview",
                       agent_name="God View", action="INJECT", content=c)

        hour = (19 + rnd) % 24  # 从晚高峰开始推进
        activity = curve[hour % len(curve)]
        for platform in platforms:
            action_set = ACTIONS_BY_PLATFORM.get(platform, TWITTER_ACTIONS)
            for agent in agents[platform]:
                if random.random() > activity:
                    continue
                action = random.choice(action_set)
                content = ""
                if action in ("CREATE_POST", "CREATE_COMMENT", "QUOTE_POST"):
                    if llm:
                        try:
                            content = llm(
                                f"用一句话，以 {agent['name']} 的口吻，就以下话题发表社交媒体观点："
                                f"{topics[-1]}"
                            )
                        except Exception:  # noqa: BLE001
                            content = "对此我有一些想法。"
                    else:
                        content = "对此我有一些想法。"
                logger.log(round=rnd, platform=platform, agent_id=agent["id"],
                           agent_name=agent["name"], action=action, content=content)
        # 每轮处理一次采访请求（贴合人设作答）
        _handle_interviews(work_dir, llm, profiles)
        time.sleep(0.2)

    # 模拟回合完成后进入等待命令模式（环境常驻，支持实时采访，）
    run_wait_loop(work_dir, platforms, llm, profiles)
