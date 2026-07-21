"""模拟相关 API 蓝图（/api/simulation）。

覆盖：实体读取、模拟创建、环境准备（异步）、启动/状态/动作、以及 Interview。
"""

import json
import os
import threading

from flask import Blueprint, jsonify, request

from ..config import config
from ..models import TaskStatus, project_store, task_store
from ..services import zep_entity_reader
from ..services.graph_builder import ZepUnavailable
from ..services.oasis_profile_generator import (
    generate_profiles,
    to_reddit_json,
    to_twitter_csv,
)
from ..services.simulation_config_generator import generate_config
from ..services.simulation_ipc import read_interview_response, write_interview_request
from ..services.simulation_manager import simulation_manager
from ..utils.locale import t
from ..utils.logger import get_logger

logger = get_logger("api.simulation")

simulation_bp = Blueprint("simulation", __name__)

# 模拟 -> 准备任务 ID
_prepare_tasks: dict[str, str] = {}


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
    """异步准备模拟环境：生成 Profile + 智能生成模拟配置。"""
    body = request.get_json(silent=True) or {}
    sim_id = body.get("simulation_id")
    sim = simulation_manager.get(sim_id)
    if not sim:
        return jsonify({"error": t("not_found")}), 404

    task = task_store.create("prepare")
    _prepare_tasks[sim_id] = task.id

    def _run():
        task_store.update(task.id, status=TaskStatus.RUNNING, progress=10)
        try:
            graph_id = sim.get("graph_id")
            requirement = sim.get("requirement", "")
            # 1) 读取实体
            entities = zep_entity_reader.read_entities(
                graph_id) if graph_id else []
            task_store.update(task.id, progress=30)
            # 2) 生成 Profile（Reddit JSON + Twitter CSV）
            profiles = generate_profiles(entities, graph_id=graph_id)
            work_dir = simulation_manager.work_dir(sim_id)
            with open(os.path.join(work_dir, "profiles_reddit.json"), "w", encoding="utf-8") as f:
                json.dump(to_reddit_json(profiles), f,
                          ensure_ascii=False, indent=2)
            with open(os.path.join(work_dir, "profiles_twitter.csv"), "w", encoding="utf-8") as f:
                f.write(to_twitter_csv(profiles))
            task_store.update(task.id, progress=70)
            # 3) 智能生成模拟配置
            project = project_store.get(sim.get("project_id"))
            sim_config = generate_config(project, profiles, requirement)
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


# ---------------- 运行控制 ----------------

@simulation_bp.post("/start")
def start_simulation():
    """启动模拟运行（默认双平台并行）。"""
    body = request.get_json(silent=True) or {}
    sim_id = body.get("simulation_id")
    mode = body.get("mode", "parallel")
    max_rounds = body.get("max_rounds")
    if not simulation_manager.get(sim_id):
        return jsonify({"error": t("not_found")}), 404
    try:
        sim = simulation_manager.start(
            sim_id, mode=mode, max_rounds=max_rounds)
        return jsonify({"simulation": sim})
    except Exception as e:  # noqa: BLE001
        logger.error("启动模拟失败：%s", e)
        return jsonify({"error": str(e)}), 500


@simulation_bp.post("/status")
def simulation_status():
    """获取模拟运行状态。"""
    body = request.get_json(silent=True) or {}
    sim_id = body.get("simulation_id")
    status = simulation_manager.status(sim_id)
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


# ---------------- Interview ----------------

@simulation_bp.post("/interview")
def interview():
    """采访单个 Agent。"""
    body = request.get_json(silent=True) or {}
    sim_id = body.get("simulation_id")
    agent_id = body.get("agent_id")
    question = body.get("question", "")
    if not sim_id:
        return jsonify({"error": t("bad_request")}), 400
    req_id = write_interview_request(sim_id, agent_id, question)
    resp = read_interview_response(
        sim_id, req_id, timeout=float(body.get("timeout", 20)))
    return jsonify({"answer": (resp or {}).get("answer", ""), "request_id": req_id})


@simulation_bp.post("/interview/batch")
def interview_batch():
    """批量采访 Agent（问卷调查）。"""
    body = request.get_json(silent=True) or {}
    sim_id = body.get("simulation_id")
    agent_ids = body.get("agent_ids", [])
    question = body.get("question", "")
    if not sim_id:
        return jsonify({"error": t("bad_request")}), 400

    results = []
    for agent_id in agent_ids:
        req_id = write_interview_request(sim_id, agent_id, question)
        resp = read_interview_response(
            sim_id, req_id, timeout=float(body.get("timeout", 20)))
        results.append(
            {"agent_id": agent_id, "answer": (resp or {}).get("answer", "")})
    return jsonify({"results": results})
