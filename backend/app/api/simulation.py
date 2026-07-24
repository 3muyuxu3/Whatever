"""模拟相关 API 蓝图（/api/simulation）。

覆盖：实体读取、模拟创建、环境准备（异步）、启动/状态/动作、以及 Interview。
"""

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Blueprint, Response, jsonify, request, stream_with_context

from ..config import config
from ..models import TaskStatus, TaskRegistry, project_store, task_store
from ..services import zep_entity_reader
from ..services.graph_builder import ZepUnavailable
from ..services.oasis_profile_generator import (
    generate_profiles,
    to_reddit_json,
    to_twitter_csv,
)
from ..services.simulation_config_generator import generate_config
from ..services.simulation_ipc import (
    read_env_status,
    read_interview_response,
    write_injection,
    write_interview_request,
)
from ..services.simulation_manager import simulation_manager
from ..utils.llm_client import get_llm_client
from ..utils.locale import t
from ..utils.logger import get_logger

logger = get_logger("api.simulation")

simulation_bp = Blueprint("simulation", __name__)

# 模拟 -> 准备任务 ID（线程安全）
_prepare_tasks = TaskRegistry()


# ---------------- 实体 ----------------

@simulation_bp.get("/entities/<graph_id>")
def get_entities(graph_id: str):
    """获取图谱实体（已过滤）。"""
    try:
        entities = zep_entity_reader.read_entities(graph_id)
        return jsonify({"entities": entities})
    except ZepUnavailable as e:
        # 未配置/未安装 Zep 属预期降级，返回空列表并附提示（不告警）
        logger.info("Zep 不可用，返回空实体列表：%s", e)
        return jsonify({"entities": [], "zep_available": False, "message": str(e)})
    except Exception as e:  # noqa: BLE001
        logger.warning("读取实体失败：%s", e)
        return jsonify({"entities": [], "error": str(e)})


@simulation_bp.get("/entities/<graph_id>/<uuid>")
def get_entity(graph_id: str, uuid: str):
    """获取单个实体详情。"""
    try:
        detail = zep_entity_reader.get_entity_detail(graph_id, uuid)
    except ZepUnavailable as e:
        logger.info("Zep 不可用：%s", e)
        return jsonify({"zep_available": False, "message": str(e)})
    if not detail:
        return jsonify({"error": t("not_found")}), 404
    return jsonify(detail)


# ---------------- 模拟创建与准备 ----------------

@simulation_bp.post("/create")
def create_simulation():
    """创建新模拟。"""
    body = request.get_json(silent=True) or {}
    project_id = body.get("project_id")
    project = project_store.get(project_id)
    if not project:
        return jsonify({"error": t("not_found")}), 404
    sim = simulation_manager.create(
        project_id=project_id,
        graph_id=project.graph_id,
        requirement=project.requirement,
    )
    return jsonify({"simulation_id": sim["id"], "simulation": sim})


@simulation_bp.post("/prepare")
def prepare_simulation():
    """异步准备模拟环境：生成 Profile + 智能生成模拟配置。

    幂等：若已完成准备（人设 + 配置齐全）且未传 force_regenerate，则直接复用，
    避免重复的高成本 LLM 人设/配置生成。
    """
    body = request.get_json(silent=True) or {}
    sim_id = body.get("simulation_id")
    max_rounds = body.get("max_rounds")
    force = bool(body.get("force_regenerate", False))
    sim = simulation_manager.get(sim_id)
    if not sim:
        return jsonify({"error": t("not_found")}), 404

    # 幂等：已有人设 + 配置时直接返回一个已完成任务，前端轮询即视为完成，无需重跑
    if not force:
        existing = simulation_manager.read_profiles(sim_id)
        if existing and simulation_manager.get_config(sim_id):
            task = task_store.create("prepare")
            task_store.update(task.id, status=TaskStatus.COMPLETED, progress=100,
                              result={"profiles": len(existing)})
            _prepare_tasks[sim_id] = task.id
            logger.info("模拟 %s 已完成准备，直接复用（人设 %d）", sim_id, len(existing))
            return jsonify({"task_id": task.id, "already_prepared": True})

    task = task_store.create("prepare")
    _prepare_tasks[sim_id] = task.id

    def _run():
        task_store.update(task.id, status=TaskStatus.RUNNING, progress=10)
        try:
            graph_id = sim.get("graph_id")
            requirement = sim.get("requirement", "")
            # 1) 读取实体（Zep 异步抽取可能耗时数分钟，实体为空时耐心等待）
            entities = zep_entity_reader.read_entities(
                graph_id) if graph_id else []
            if graph_id and not entities:
                # 最多等待约 5 分钟（与建图阶段的等待共同覆盖 Zep 的抽取延迟）。
                # 每 15s 拉一次“最新”数据（绕过缓存），与缓存 TTL 对齐，
                # 避免高频拉取触发限流；期间推进进度条（10 -> 28）。
                max_tries = 20  # 20 * 15s ≈ 300s
                for i in range(max_tries):
                    time.sleep(15)
                    entities = zep_entity_reader.read_entities(
                        graph_id, use_cache=False)
                    if entities:
                        break
                    task_store.update(
                        task.id, progress=10 + int(18 * (i + 1) / max_tries))
                if not entities:
                    logger.warning("图谱 %s 实体仍为空（Zep 可能仍在处理），将以空实体继续", graph_id)
            task_store.update(task.id, progress=30)
            # 标记进入准备中并记录预期 Agent 总数（供 /profiles/realtime 展示进度）
            simulation_manager.update(
                sim_id, status="preparing", entities_count=len(entities))
            # 2) 生成 Profile（边生成边增量写入，支持环境搭建阶段实时流式展示）
            work_dir = simulation_manager.work_dir(sim_id)
            reddit_path = os.path.join(work_dir, "profiles_reddit.json")
            acc: list[dict] = []

            def _on_each(p):
                acc.append(p)
                try:
                    tmp = reddit_path + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(to_reddit_json(acc), f, ensure_ascii=False)
                    os.replace(tmp, reddit_path)
                except Exception:  # noqa: BLE001
                    pass
                task_store.update(task.id, progress=min(
                    65, 30 + int(35 * len(acc) / max(1, len(entities)))))

            profiles = generate_profiles(
                entities, graph_id=graph_id, on_each=_on_each)
            # 最终按原始顺序完整写入（覆盖增量文件）+ Twitter CSV
            with open(reddit_path, "w", encoding="utf-8") as f:
                json.dump(to_reddit_json(profiles), f,
                          ensure_ascii=False, indent=2)
            with open(os.path.join(work_dir, "profiles_twitter.csv"), "w", encoding="utf-8") as f:
                f.write(to_twitter_csv(profiles))
            task_store.update(task.id, progress=70)
            # 3) 智能生成模拟配置
            project = project_store.get(sim.get("project_id"))
            sim_config = generate_config(
                project, profiles, requirement, max_rounds=max_rounds)
            simulation_manager.save_config(sim_id, sim_config)
            task_store.update(task.id, status=TaskStatus.COMPLETED, progress=100,
                              result={"profiles": len(profiles)})
        except Exception as e:  # noqa: BLE001
            logger.error("环境准备失败：%s", e)
            task_store.update(task.id, status=TaskStatus.FAILED, error=str(e))

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"task_id": task.id})


@simulation_bp.post("/prepare/status")
def prepare_status():
    """查询准备进度。"""
    body = request.get_json(silent=True) or {}
    sim_id = body.get("simulation_id")
    task_id = body.get("task_id") or _prepare_tasks.get(sim_id)
    task = task_store.get(task_id) if task_id else None
    return jsonify(
        {
            "status": task.status.value if task else "unknown",
            "progress": task.progress if task else 0,
            "error": task.error if task else None,
        }
    )


@simulation_bp.get("/<sim_id>/profiles/realtime")
def profiles_realtime(sim_id: str):
    """实时获取生成中的 Agent 人设（环境搭建阶段流式展示)。"""
    sim = simulation_manager.get(sim_id)
    if not sim:
        return jsonify({"error": t("not_found")}), 404
    profiles = simulation_manager.read_profiles(sim_id)
    return jsonify({
        "simulation_id": sim_id,
        "count": len(profiles),
        "total_expected": sim.get("entities_count"),
        "is_generating": sim.get("status") == "preparing",
        "profiles": profiles,
    })


@simulation_bp.get("/<sim_id>/config/realtime")
def config_realtime(sim_id: str):
    """实时获取生成中的模拟配置。"""
    sim = simulation_manager.get(sim_id)
    if not sim:
        return jsonify({"error": t("not_found")}), 404
    cfg = simulation_manager.get_config(sim_id)
    return jsonify({
        "simulation_id": sim_id,
        "config": cfg or None,
        "config_generated": bool(cfg),
        "is_generating": sim.get("status") == "preparing",
    })


# ---------------- 运行控制 ----------------

@simulation_bp.post("/start")
def start_simulation():
    """启动模拟运行（默认双平台并行）。"""
    body = request.get_json(silent=True) or {}
    sim_id = body.get("simulation_id")
    mode = body.get("mode", "parallel")
    max_rounds = body.get("max_rounds")
    # 是否开启图谱记忆动态更新（将 Agent 活动实时写回 Zep 图谱），默认开启
    enable_graph_memory_update = body.get("enable_graph_memory_update", True)
    if not simulation_manager.get(sim_id):
        return jsonify({"error": t("not_found")}), 404
    try:
        sim = simulation_manager.start(
            sim_id, mode=mode, max_rounds=max_rounds,
            enable_graph_memory_update=enable_graph_memory_update)
        return jsonify({"simulation": sim})
    except Exception as e:  # noqa: BLE001
        logger.error("启动模拟失败：%s", e)
        return jsonify({"error": str(e)}), 500


@simulation_bp.post("/status")
def simulation_status():
    """获取模拟运行状态（默认轻量版；传 detail=true 可附带最近动作）。"""
    body = request.get_json(silent=True) or {}
    sim_id = body.get("simulation_id")
    # 高频轮询接口默认返回轻量版（不含 recent_actions），前端另走 /actions 获取动作
    status = simulation_manager.status(
        sim_id, detail=bool(body.get("detail", False)))
    if status is None:
        return jsonify({"error": t("not_found")}), 404
    return jsonify(status)


@simulation_bp.post("/actions")
def simulation_actions():
    """获取动作历史。"""
    body = request.get_json(silent=True) or {}
    sim_id = body.get("simulation_id")
    limit = int(body.get("limit", 500))
    actions = simulation_manager.read_actions(sim_id, limit=limit)
    return jsonify({"actions": actions})


@simulation_bp.post("/stop")
def stop_simulation():
    """优雅停止正在运行的模拟。"""
    body = request.get_json(silent=True) or {}
    sim_id = body.get("simulation_id")
    if not simulation_manager.get(sim_id):
        return jsonify({"error": t("not_found")}), 404
    sim = simulation_manager.stop(sim_id)
    return jsonify({"simulation": sim})


@simulation_bp.get("/detail/<sim_id>")
def simulation_detail(sim_id: str):
    """获取模拟详情：配置 + 人设 + 运行状态（供环境搭建/运行页展示）。"""
    sim = simulation_manager.get(sim_id)
    if not sim:
        return jsonify({"error": t("not_found")}), 404
    return jsonify(
        {
            "simulation": sim,
            "config": simulation_manager.get_config(sim_id),
            "profiles": simulation_manager.read_profiles(sim_id),
            "status": simulation_manager.status(sim_id),
        }
    )


@simulation_bp.post("/config")
def update_config():
    """编辑模拟配置（支持修改轮次与平台开关）。"""
    body = request.get_json(silent=True) or {}
    sim_id = body.get("simulation_id")
    if not simulation_manager.get(sim_id):
        return jsonify({"error": t("not_found")}), 404
    cfg = simulation_manager.get_config(sim_id)
    if not cfg:
        return jsonify({"error": t("not_found")}), 404
    # 整体替换（可选）
    if isinstance(body.get("config"), dict):
        cfg = body["config"]
    # 定点修改：轮次
    if body.get("max_rounds"):
        cfg.setdefault("time", {})["max_rounds"] = int(body["max_rounds"])
    # 定点修改：平台开关
    if isinstance(body.get("platforms"), dict):
        for k, v in body["platforms"].items():
            if isinstance(v, dict):
                cfg.setdefault("platforms", {}).setdefault(k, {}).update(v)
    simulation_manager.save_config(sim_id, cfg)
    return jsonify({"config": cfg})


# ---------------- 上帝视角：动态注入变量 ----------------

@simulation_bp.post("/inject")
def inject_variable():
    """上帝视角：向模拟世界动态注入新事件 / 变量（实时影响后续演化）。

    模拟运行中：写入注入文件，由子进程循环下一轮消费；
    未运行：直接记录为一条注入动作，确保被后续报告捕获。
    """
    body = request.get_json(silent=True) or {}
    sim_id = body.get("simulation_id")
    content = (body.get("content") or "").strip()
    kind = body.get("kind", "event")
    platform = body.get("platform")
    sim = simulation_manager.get(sim_id)
    if not sim:
        return jsonify({"error": t("not_found")}), 404
    if not content:
        return jsonify({"error": t("bad_request")}), 400

    inj_id = write_injection(sim_id, content, kind=kind, platform=platform)
    running = simulation_manager.is_running(sim_id)
    if not running:
        st = simulation_manager.status(sim_id) or {}
        simulation_manager.append_action(
            sim_id,
            round=st.get("round", 0),
            platform=platform or "twitter",
            agent_id="godview",
            agent_name="God View",
            action="INJECT",
            content=content,
        )
    logger.info("上帝视角注入（sim=%s, running=%s）：%s", sim_id, running, content[:60])
    return jsonify({"injection_id": inj_id, "running": running, "content": content})


# ---------------- Interview 采访 ----------------

def _sse(obj: dict) -> str:
    """将对象序列化为一条 SSE 消息。"""
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


def _interview_messages(sim: dict, agent_id: str, question: str):
    """构建采访的 LLM 消息（基于人设），返回 (name, messages)。"""
    sim_id = sim.get("id")
    profiles = simulation_manager.read_profiles(sim_id)
    profile = next(
        (p for p in profiles
         if p.get("entity_uuid") == agent_id or p.get("name") == agent_id),
        None,
    )
    name = (profile or {}).get("name") or agent_id or "Agent"
    persona_bits = []
    if profile:
        for key in ("bio", "persona", "occupation", "mbti"):
            if profile.get(key):
                persona_bits.append(f"{key}: {profile[key]}")
        if profile.get("interests"):
            persona_bits.append(
                "interests: " + ", ".join(profile["interests"]))
    persona = "\n".join(persona_bits) or "（无额外人设信息）"
    requirement = sim.get("requirement", "")
    messages = [
        {
            "role": "system",
            "content": (
                f"你在扮演社交模拟世界中的一个人物：{name}。\n人设：\n{persona}\n"
                f"该世界围绕以下议题演化：{requirement}\n"
                "请始终以第一人称、贴合人设地回答，真实而简洁（2-4 句）。"
            ),
        },
        {"role": "user", "content": question},
    ]
    return name, messages


def _answer_as_agent(sim: dict, agent_id: str, question: str) -> str:
    """当模拟子进程未运行时，基于人设用 LLM 直接作答（保证“与任意个体对话”始终可用）。"""
    name, messages = _interview_messages(sim, agent_id, question)
    if not config.has_llm():
        return f"作为 {name}，我认为「{question}」值得持续关注。"
    try:
        # 采访/人设作答高并发且非质量关键，优先走加速模型（未配置时自动回落主模型）
        client = get_llm_client(boost=True)
        return client.chat(messages)
    except Exception as e:  # noqa: BLE001
        logger.warning("Agent 作答失败：%s", e)
        return f"作为 {name}，我认为「{question}」值得持续关注。"


def _ask_agent(sim: dict, agent_id: str, question: str, timeout: float) -> str:
    """向单个 Agent 提问：环境存活时走 IPC（真实 Agent 采访）；否则（或超时无应答）回退到基于人设的 LLM 作答。"""
    sim_id = sim.get("id")
    answer = ""
    # 环境已进入等待命令模式（常驻）时，采访命令会由真实 OASIS Agent 应答
    if simulation_manager.is_env_alive(sim_id):
        req_id = write_interview_request(sim_id, agent_id, question)
        # 真实 Agent 采访需调用 LLM，耗时较长，适当拉高等待上限
        resp = read_interview_response(
            sim_id, req_id, timeout=max(timeout, 60))
        answer = (resp or {}).get("answer", "")
    if not answer:
        answer = _answer_as_agent(sim, agent_id, question)
    return answer


@simulation_bp.get("/agents/<sim_id>")
def list_agents(sim_id: str):
    """列出可对话/可调查的 Agent（基于已生成的人设）。"""
    if not simulation_manager.get(sim_id):
        return jsonify({"error": t("not_found")}), 404
    return jsonify({"agents": simulation_manager.list_agents(sim_id)})


@simulation_bp.post("/interview")
def interview():
    """采访单个 Agent（与世界中任意个体对话）。"""
    body = request.get_json(silent=True) or {}
    sim_id = body.get("simulation_id")
    agent_id = body.get("agent_id")
    question = body.get("question", "")
    sim = simulation_manager.get(sim_id)
    if not sim:
        return jsonify({"error": t("not_found")}), 404
    if not question.strip():
        return jsonify({"error": t("bad_request")}), 400
    answer = _ask_agent(sim, agent_id, question,
                        float(body.get("timeout", 15)))
    return jsonify({"answer": answer, "agent_id": agent_id})


@simulation_bp.post("/interview/stream")
def interview_stream():
    """流式采访单个 Agent（SSE）：环境存活时走真实 Agent 采访（IPC），否则基于人设 LLM 逐字输出。"""
    body = request.get_json(silent=True) or {}
    sim_id = body.get("simulation_id")
    agent_id = body.get("agent_id")
    question = (body.get("question") or "").strip()
    sim = simulation_manager.get(sim_id)
    if not sim:
        return jsonify({"error": t("not_found")}), 404
    if not question:
        return jsonify({"error": t("bad_request")}), 400
    # 在进入生成器（无请求上下文）前捕获所需数据
    name, messages = _interview_messages(sim, agent_id, question)
    has_llm = config.has_llm()
    env_alive = simulation_manager.is_env_alive(sim_id)

    def gen():
        # 环境存活：优先真实 Agent 采访（IPC），得到回答后分块输出（模拟流式）
        if env_alive:
            try:
                req_id = write_interview_request(sim_id, agent_id, question)
                resp = read_interview_response(sim_id, req_id, timeout=90)
                ans = (resp or {}).get("answer", "")
                if ans:
                    # IPC 已返回完整回答，需人为分帧 + 微小间隔才能呈现打字机效果
                    # （否则所有分块会在同一时刻涌出，前端一次性渲染，失去逐字流式观感）
                    for i in range(0, len(ans), 3):
                        yield _sse({"delta": ans[i:i + 3]})
                        time.sleep(0.03)
                    yield _sse({"done": True})
                    return
            except Exception as e:  # noqa: BLE001
                logger.warning("流式真实采访失败，降级人设作答：%s", e)
        # 降级：基于人设的 LLM 流式作答
        if not has_llm:
            yield _sse({"delta": f"作为 {name}，我认为「{question}」值得持续关注。"})
            yield _sse({"done": True})
            return
        got = False
        try:
            client = get_llm_client(boost=True)
            for tok in client.chat_stream(messages):
                got = True
                yield _sse({"delta": tok})
        except Exception as e:  # noqa: BLE001
            logger.warning("流式采访失败：%s", e)
        if not got:
            yield _sse({"delta": f"作为 {name}，我认为「{question}」值得持续关注。"})
        yield _sse({"done": True})

    return Response(
        stream_with_context(gen()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@simulation_bp.post("/env-status")
def env_status():
    """查询模拟环境是否存活（可接受实时采访）——。"""
    body = request.get_json(silent=True) or {}
    sim_id = body.get("simulation_id")
    if not simulation_manager.get(sim_id):
        return jsonify({"error": t("not_found")}), 404
    alive = simulation_manager.is_env_alive(sim_id)
    st = read_env_status(sim_id)
    return jsonify({
        "simulation_id": sim_id,
        "env_alive": alive,
        "twitter_available": bool(st.get("twitter_available")),
        "reddit_available": bool(st.get("reddit_available")),
        "message": "环境正在运行，可接受采访" if alive else "环境未运行",
    })


@simulation_bp.post("/close-env")
def close_env():
    """优雅关闭模拟环境（不同于 /stop 的强制终止）——。"""
    body = request.get_json(silent=True) or {}
    sim_id = body.get("simulation_id")
    timeout = body.get("timeout", 30)
    if not simulation_manager.get(sim_id):
        return jsonify({"error": t("not_found")}), 404
    sim = simulation_manager.close_env(sim_id, timeout=float(timeout))
    return jsonify({"simulation": sim, "message": "环境关闭命令已处理"})


@simulation_bp.post("/interview/batch")
def interview_batch():
    """批量采访 Agent（向世界发送问卷调查）。"""
    body = request.get_json(silent=True) or {}
    sim_id = body.get("simulation_id")
    agent_ids = body.get("agent_ids", [])
    question = body.get("question", "")
    sim = simulation_manager.get(sim_id)
    if not sim:
        return jsonify({"error": t("not_found")}), 404
    if not question.strip():
        return jsonify({"error": t("bad_request")}), 400

    # 未指定时默认向全体发送
    if not agent_ids:
        agent_ids = [a["id"] for a in simulation_manager.list_agents(sim_id)]

    # 并行采访（回退作答不依赖子进程，可安全并发）
    name_by_id = {a["id"]: a["name"]
                  for a in simulation_manager.list_agents(sim_id)}
    timeout = float(body.get("timeout", 15))
    results_by_id: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(agent_ids)))) as ex:
        future_map = {
            ex.submit(_ask_agent, sim, aid, question, timeout): aid
            for aid in agent_ids
        }
        # 按完成顺序收集，避免某个 Agent 作答较慢阻塞其余结果的收集
        for fut in as_completed(future_map):
            aid = future_map[fut]
            try:
                results_by_id[aid] = fut.result()
            except Exception:  # noqa: BLE001
                results_by_id[aid] = ""
    # 按请求顺序输出，保证前端展示稳定
    results = [
        {"agent_id": aid, "name": name_by_id.get(aid, aid),
         "answer": results_by_id.get(aid, "")}
        for aid in agent_ids
    ]
    return jsonify({"results": results, "count": len(results)})
