"""报告相关 API 蓝图（/api/report）。

覆盖：报告异步生成、状态查询、获取/删除/下载、按模拟查询、列表、以及与报告 Agent 对话。
"""

import io
import threading

from flask import Blueprint, jsonify, request, send_file

from ..models import TaskStatus, project_store, task_store
from ..services.report_agent import ReportAgent, generate_report, report_store
from ..services.simulation_manager import simulation_manager
from ..utils.locale import t
from ..utils.logger import get_logger

logger = get_logger("api.report")

report_bp = Blueprint("report", __name__)

# 报告 -> 生成任务 ID
_report_tasks: dict[str, str] = {}


@report_bp.post("/generate")
def generate():
    """异步生成模拟分析报告。"""
    body = request.get_json(silent=True) or {}
    sim_id = body.get("simulation_id")
    sim = simulation_manager.get(sim_id)
    # 允许在无模拟记录时也生成（用请求中的 requirement），以增强健壮性
    requirement = body.get("requirement") or (sim.get("requirement") if sim else "")
    graph_id = body.get("graph_id") or (sim.get("graph_id") if sim else None)

    report = report_store.create(simulation_id=sim_id)
    task = task_store.create("report")
    _report_tasks[report["id"]] = task.id

    def _run():
        task_store.update(task.id, status=TaskStatus.RUNNING, progress=5)
        try:
            actions = simulation_manager.read_actions(sim_id) if sim_id else []

            def on_progress(p):
                task_store.update(task.id, progress=p)
                report_store.update(report["id"], progress=p)

            content = generate_report(
                graph_id, sim_id, requirement, actions, on_progress=on_progress
            )
            report_store.update(report["id"], content=content, status="completed")
            task_store.update(task.id, status=TaskStatus.COMPLETED, progress=100)
        except Exception as e:  # noqa: BLE001
            logger.error("报告生成失败：%s", e)
            report_store.update(report["id"], status="failed")
            task_store.update(task.id, status=TaskStatus.FAILED, error=str(e))

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"report_id": report["id"], "task_id": task.id})


@report_bp.post("/generate/status")
def generate_status():
    """查询报告生成进度。"""
    body = request.get_json(silent=True) or {}
    report_id = body.get("report_id")
    task_id = body.get("task_id") or _report_tasks.get(report_id)
    task = task_store.get(task_id) if task_id else None
    return jsonify(
        {
            "status": task.status.value if task else "unknown",
            "progress": task.progress if task else 0,
            "error": task.error if task else None,
        }
    )


@report_bp.get("/list")
def list_reports():
    """列出所有报告。"""
    return jsonify({"reports": report_store.list()})


@report_bp.get("/by-simulation/<sim_id>")
def by_simulation(sim_id: str):
    """按模拟 ID 获取报告。"""
    report = report_store.get_by_simulation(sim_id)
    if not report:
        return jsonify({"error": t("not_found")}), 404
    return jsonify(report)


@report_bp.get("/<report_id>")
def get_report(report_id: str):
    report = report_store.get(report_id)
    if not report:
        return jsonify({"error": t("not_found")}), 404
    return jsonify(report)


@report_bp.delete("/<report_id>")
def delete_report(report_id: str):
    ok = report_store.delete(report_id)
    return jsonify({"deleted": ok})


@report_bp.get("/<report_id>/download")
def download_report(report_id: str):
    """下载 Markdown 报告。"""
    report = report_store.get(report_id)
    if not report:
        return jsonify({"error": t("not_found")}), 404
    content = (report.get("content") or "").encode("utf-8")
    return send_file(
        io.BytesIO(content),
        mimetype="text/markdown",
        as_attachment=True,
        download_name=f"report-{report_id}.md",
    )


@report_bp.post("/chat")
def chat():
    """与 Report Agent 对话（深度互动）。"""
    body = request.get_json(silent=True) or {}
    report_id = body.get("report_id")
    message = body.get("message", "")
    report = report_store.get(report_id)
    content = report.get("content", "") if report else ""

    sim = simulation_manager.get(report.get("simulation_id")) if report else None
    graph_id = sim.get("graph_id") if sim else None
    sim_id = sim.get("id") if sim else None

    agent = ReportAgent(graph_id=graph_id, sim_id=sim_id)
    reply = agent.chat(content, message)
    return jsonify({"reply": reply})
