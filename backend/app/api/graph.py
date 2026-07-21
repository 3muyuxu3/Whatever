"""图谱相关 API 蓝图（/api/graph）。

覆盖：项目管理、本体生成、图谱构建（异步）、图谱数据读取。
所有耗时操作以后台线程执行，并通过任务/项目状态供前端轮询。
"""

import os
import threading

from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename

from ..config import config
from ..models import TaskStatus, project_store, task_store
from ..services import graph_builder
from ..services.ontology_generator import generate_ontology
from ..utils.file_parser import parse_file
from ..utils.locale import t
from ..utils.logger import get_logger

logger = get_logger("api.graph")

graph_bp = Blueprint("graph", __name__)

# 项目 -> 各阶段任务 ID 的映射（用于状态轮询）
_ontology_tasks: dict[str, str] = {}
_build_tasks: dict[str, str] = {}


# ---------------- 项目管理 ----------------

@graph_bp.get("/project/list")
def list_projects():
    """列出所有项目。"""
    projects = [p.model_dump() for p in project_store.list()]
    return jsonify({"projects": projects})


@graph_bp.get("/project/<project_id>")
def get_project(project_id: str):
    project = project_store.get(project_id)
    if not project:
        return jsonify({"error": t("not_found")}), 404
    return jsonify(project.model_dump())


@graph_bp.delete("/project/<project_id>")
def delete_project(project_id: str):
    ok = project_store.delete(project_id)
    return jsonify({"deleted": ok})


@graph_bp.post("/project/<project_id>/reset")
def reset_project(project_id: str):
    project = project_store.update(project_id, status="created", graph_id=None)
    if not project:
        return jsonify({"error": t("not_found")}), 404
    return jsonify(project.model_dump())


# ---------------- 本体生成 ----------------

@graph_bp.post("/ontology/generate")
def ontology_generate():
    """上传种子文件 + 预测需求，异步生成本体定义。"""
    requirement = request.form.get("requirement", "")
    file = request.files.get("file")
    if not file:
        return jsonify({"error": t("bad_request")}), 400

    # 创建项目并保存文件
    filename = secure_filename(file.filename or "seed.txt")
    project = project_store.create(
        name=filename, requirement=requirement, file_name=filename
    )
    project_dir = os.path.join(config.UPLOAD_DIR, project.id)
    os.makedirs(project_dir, exist_ok=True)
    file_path = os.path.join(project_dir, filename)
    file.save(file_path)

    # 后台任务：解析文件 -> 生成本体
    task = task_store.create("ontology")
    _ontology_tasks[project.id] = task.id

    def _run():
        task_store.update(task.id, status=TaskStatus.RUNNING, progress=10)
        try:
            text = parse_file(file_path)
            task_store.update(task.id, progress=40)
            ontology = generate_ontology(text, requirement)
            project_store.update(project.id, ontology=ontology, status="ontology_ready")
            task_store.update(
                task.id, status=TaskStatus.COMPLETED, progress=100, result=ontology
            )
        except Exception as e:  # noqa: BLE001
            logger.error("本体生成失败：%s", e)
            project_store.update(project.id, status="failed")
            task_store.update(task.id, status=TaskStatus.FAILED, error=str(e))

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"project_id": project.id, "task_id": task.id})


# ---------------- 图谱构建 ----------------

@graph_bp.post("/build")
def build():
    """异步构建 Zep 知识图谱。"""
    body = request.get_json(silent=True) or {}
    project_id = body.get("project_id")
    project = project_store.get(project_id)
    if not project:
        return jsonify({"error": t("not_found")}), 404

    task = task_store.create("build")
    _build_tasks[project_id] = task.id
    project_store.update(project_id, status="building")

    def _run():
        task_store.update(task.id, status=TaskStatus.RUNNING, progress=5)
        try:
            file_dir = os.path.join(config.UPLOAD_DIR, project_id)
            file_path = os.path.join(file_dir, project.file_name or "")
            text = parse_file(file_path) if os.path.exists(file_path) else ""

            def on_progress(p):
                task_store.update(task.id, progress=p)

            graph_id = graph_builder.build_graph(project, text, on_progress=on_progress)
            project_store.update(project_id, graph_id=graph_id, status="graph_ready")
            task_store.update(task.id, status=TaskStatus.COMPLETED, progress=100,
                              result={"graph_id": graph_id})
        except Exception as e:  # noqa: BLE001
            logger.error("图谱构建失败：%s", e)
            project_store.update(project_id, status="failed")
            task_store.update(task.id, status=TaskStatus.FAILED, error=str(e))

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"task_id": task.id})


@graph_bp.post("/build/status")
def build_status():
    """查询图谱构建（或本体生成）进度。"""
    body = request.get_json(silent=True) or {}
    project_id = body.get("project_id")
    task_id = body.get("task_id") or _build_tasks.get(project_id) or _ontology_tasks.get(project_id)
    task = task_store.get(task_id) if task_id else None
    project = project_store.get(project_id)
    return jsonify(
        {
            "status": (task.status.value if task else (project.status if project else "unknown")),
            "progress": task.progress if task else 0,
            "error": task.error if task else None,
            "graph_id": project.graph_id if project else None,
        }
    )


# ---------------- 图谱数据 ----------------

@graph_bp.get("/data/<graph_id>")
def graph_data(graph_id: str):
    """获取完整图谱数据（节点 + 边）。"""
    try:
        data = graph_builder.get_graph_data(graph_id)
        return jsonify(data)
    except Exception as e:  # noqa: BLE001
        logger.warning("读取图谱数据失败：%s", e)
        # 优雅降级：返回空图谱，避免前端崩溃
        return jsonify({"graph_id": graph_id, "nodes": [], "edges": [], "error": str(e)})
