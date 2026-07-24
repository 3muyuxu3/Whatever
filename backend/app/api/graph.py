"""图谱相关 API 蓝图（/api/graph）。

覆盖：项目管理、本体生成、图谱构建（异步）、图谱数据读取。
所有耗时操作以后台线程执行，并通过任务/项目状态供前端轮询。
"""

import os
import threading

from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename

from ..config import config
from ..models import TaskStatus, TaskRegistry, project_store, task_store
from ..services import graph_builder
from ..services.ontology_generator import generate_ontology
from ..utils.file_parser import parse_file
from ..utils.locale import t
from ..utils.logger import get_logger

logger = get_logger("api.graph")

graph_bp = Blueprint("graph", __name__)

# 项目 -> 各阶段任务 ID 的映射（用于状态轮询，线程安全）
_ontology_tasks = TaskRegistry()
_build_tasks = TaskRegistry()
# 项目 -> 构建中的 graph_id（图谱创建后即写入，供前端在构建期间实时可视化；
# 与 project.graph_id 区分：后者仅在构建完成时才置位，用于解锁下一步）
_build_graph_ids = TaskRegistry()


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
    """上传种子文件（支持多文件） + 预测需求，异步生成本体定义。"""
    requirement = request.form.get("requirement", "")
    # 兼容单文件字段名 file 与多文件字段名 files
    files = request.files.getlist("file") + request.files.getlist("files")
    files = [f for f in files if f and f.filename]
    if not files:
        return jsonify({"error": t("bad_request")}), 400

    # 校验扩展名：仅接受受支持的种子文件类型，拒绝其他文件避免任意文件落盘
    def _allowed(fn: str) -> bool:
        return os.path.splitext(fn or "")[1].lower() in config.ALLOWED_EXTENSIONS

    files = [f for f in files if _allowed(f.filename)]
    if not files:
        return jsonify({"error": t("unsupported_file_type")}), 400

    # 创建项目并保存全部文件
    first_name = secure_filename(files[0].filename or "seed.txt")
    project = project_store.create(
        name=(request.form.get("project_name") or first_name),
        requirement=requirement,
        file_name=first_name,
    )
    project_dir = os.path.join(config.UPLOAD_DIR, project.id)
    os.makedirs(project_dir, exist_ok=True)
    saved = []  # [(filename, path)]
    for f in files:
        fn = secure_filename(f.filename or "seed.txt")
        fp = os.path.join(project_dir, fn)
        f.save(fp)
        saved.append((fn, fp))
    project_store.update(project.id, file_names=[n for n, _ in saved])

    # 后台任务：解析全部文件 -> 生成本体
    task = task_store.create("ontology")
    _ontology_tasks[project.id] = task.id

    def _run():
        task_store.update(task.id, status=TaskStatus.RUNNING, progress=10)
        try:
            parts = []
            for fn, fp in saved:
                try:
                    parts.append(f"=== {fn} ===\n{parse_file(fp)}")
                except Exception as e:  # noqa: BLE001
                    logger.warning("解析文件失败 %s：%s", fn, e)
            text = "\n\n".join(parts)
            if not text.strip():
                # 所有文件解析失败 / 为空：不再空跑 LLM 生成无意义本体，直接报错
                raise ValueError("未能从上传文件中解析出任何文本内容")
            task_store.update(task.id, progress=40)
            ontology = generate_ontology(text, requirement)
            project_store.update(
                project.id,
                ontology=ontology,
                analysis_summary=ontology.get("analysis_summary", ""),
                status="ontology_ready",
            )
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
            names = project.file_names or (
                [project.file_name] if project.file_name else [])
            parts = []
            for fn in names:
                fp = os.path.join(file_dir, fn)
                if os.path.exists(fp):
                    try:
                        parts.append(parse_file(fp))
                    except Exception as e:  # noqa: BLE001
                        logger.warning("解析文件失败 %s：%s", fn, e)
            text = "\n\n".join(parts)

            def on_progress(p):
                task_store.update(task.id, progress=p)

            def on_graph_created(gid):
                _build_graph_ids[project_id] = gid

            graph_id = graph_builder.build_graph(
                project, text, on_progress=on_progress,
                on_graph_created=on_graph_created)
            project_store.update(
                project_id, graph_id=graph_id, status="graph_ready")
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
    task_id = body.get("task_id") or _build_tasks.get(
        project_id) or _ontology_tasks.get(project_id)
    task = task_store.get(task_id) if task_id else None
    project = project_store.get(project_id)
    # 构建中优先返回临时 graph_id，让前端在建图过程中即可拉取并实时展示图谱
    live_graph_id = (project.graph_id if project and project.graph_id
                     else _build_graph_ids.get(project_id))
    if task:
        status = task.status.value
        progress = task.progress
        error = task.error
    else:
        # 任务对象丢失（如服务重启）时，用项目状态推导前端可识别的终态，
        # 避免前端因拿不到 completed/failed 而无限轮询。
        _terminal = {"graph_ready": "completed", "failed": "failed"}
        status = _terminal.get(
            project.status, project.status) if project else "unknown"
        progress = 100 if status == "completed" else 0
        error = None
    return jsonify(
        {
            "status": status,
            "progress": progress,
            "error": error,
            "graph_id": live_graph_id,
        }
    )


# ---------------- 图谱数据 ----------------

@graph_bp.get("/data/<graph_id>")
def graph_data(graph_id: str):
    """获取完整图谱数据（节点 + 边）。"""
    try:
        data = graph_builder.get_graph_data(graph_id)
        return jsonify(data)
    except graph_builder.ZepUnavailable as e:
        # 未配置/未安装 Zep 属预期降级，返回空图谱（不告警）
        logger.info("Zep 不可用，返回空图谱：%s", e)
        return jsonify(
            {"graph_id": graph_id, "nodes": [], "edges": [],
                "zep_available": False, "message": str(e)}
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("读取图谱数据失败：%s", e)
        # 优雅降级：返回空图谱，避免前端崩溃
        return jsonify({"graph_id": graph_id, "nodes": [], "edges": [], "error": str(e)})
