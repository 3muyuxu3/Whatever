"""报告相关 API 蓝图（/api/report）。

覆盖：报告异步生成、状态查询、获取/删除/下载、按模拟查询、列表、以及与报告 Agent 对话。
"""

import io
import json
import threading

from flask import Blueprint, Response, jsonify, request, send_file, stream_with_context

from ..config import config
from ..models import TaskStatus, TaskRegistry, project_store, task_store
from ..services.report_agent import (
    ReportAgent,
    ReportEventLogger,
    generate_report,
    read_report_log,
    report_store,
)
from ..services.simulation_manager import simulation_manager
from ..utils.locale import t
from ..utils.logger import get_logger

logger = get_logger("api.report")

report_bp = Blueprint("report", __name__)

# 报告 -> 生成任务 ID（线程安全）
_report_tasks = TaskRegistry()


@report_bp.post("/generate")
def generate():
    """异步生成模拟分析报告。

    幂等：同一模拟已有「已完成」报告且未传 force_regenerate 时直接复用，
    避免重复的高成本报告生成与重复报告堆积。
    """
    body = request.get_json(silent=True) or {}
    sim_id = body.get("simulation_id")
    force = bool(body.get("force_regenerate", False))
    sim = simulation_manager.get(sim_id)
    # 允许在无模拟记录时也生成（用请求中的 requirement），以增强健壮性
    requirement = body.get("requirement") or (
        sim.get("requirement") if sim else "")
    graph_id = body.get("graph_id") or (sim.get("graph_id") if sim else None)

    # 幂等：已有已完成报告时直接复用，前端轮询即视为完成
    if not force and sim_id:
        existing = report_store.get_by_simulation(sim_id)
        if existing and existing.get("status") == "completed":
            task = task_store.create("report")
            task_store.update(
                task.id, status=TaskStatus.COMPLETED, progress=100)
            _report_tasks[existing["id"]] = task.id
            logger.info("模拟 %s 已有完成报告 %s，直接复用", sim_id, existing["id"])
            return jsonify({"report_id": existing["id"], "task_id": task.id,
                            "already_generated": True})

    report = report_store.create(simulation_id=sim_id)
    task = task_store.create("report")
    _report_tasks[report["id"]] = task.id

    def _run():
        task_store.update(task.id, status=TaskStatus.RUNNING, progress=5)
        # 结构化事件日志（逐步写 JSONL，供 /log 接口回放）
        event_logger = ReportEventLogger(report["id"])
        try:
            actions = simulation_manager.read_actions(sim_id) if sim_id else []

            def on_progress(p):
                task_store.update(task.id, progress=p)
                report_store.update(report["id"], progress=p)

            def on_plan(outline):
                # 大纲就绪：提前写入报告记录，供前端展示章节列表与总数
                report_store.update(
                    report["id"],
                    outline={
                        "title": outline.get("title", ""),
                        "summary": outline.get("summary", ""),
                        "section_titles": outline.get("sections", []),
                    },
                    total_sections=len(outline.get("sections", [])),
                )

            sections_acc: list[dict] = []

            def on_section(index, title, content):
                # 单章节完成：增量写入，前端可轮询 /sections 实时展示
                sections_acc.append(
                    {"index": index, "title": title, "content": content})
                report_store.update(
                    report["id"],
                    sections=list(sections_acc),
                    current_section=title,
                    completed_sections=[s["title"] for s in sections_acc],
                )

            agent = ReportAgent(graph_id=graph_id, sim_id=sim_id)
            content = agent.generate(
                requirement, actions, on_progress=on_progress,
                on_plan=on_plan, on_section=on_section, event_logger=event_logger)
            report_store.update(
                report["id"], content=content, status="completed",
                tool_trace=agent.tool_trace,
            )
            task_store.update(
                task.id, status=TaskStatus.COMPLETED, progress=100)
        except Exception as e:  # noqa: BLE001
            logger.error("报告生成失败：%s", e)
            event_logger.log("error", "failed", error=str(e))
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


@report_bp.get("/<report_id>/sections")
def report_sections(report_id: str):
    """获取已生成的章节列表（分章节实时展示，无需等整篇完成）。"""
    report = report_store.get(report_id)
    if not report:
        return jsonify({"error": t("not_found")}), 404
    sections = report.get("sections", []) or []
    return jsonify(
        {
            "report_id": report_id,
            "sections": sections,
            "total_sections": report.get("total_sections", len(sections)),
            "is_complete": report.get("status") == "completed",
        }
    )


@report_bp.get("/<report_id>/progress")
def report_progress(report_id: str):
    """获取报告生成进度（状态 + 百分比 + 当前/已完成章节）。"""
    report = report_store.get(report_id)
    if not report:
        return jsonify({"error": t("not_found")}), 404
    return jsonify(
        {
            "status": report.get("status", "generating"),
            "progress": report.get("progress", 0),
            "current_section": report.get("current_section"),
            "completed_sections": report.get("completed_sections", []),
            "outline": report.get("outline"),
        }
    )


@report_bp.get("/<report_id>/log")
def report_log(report_id: str):
    """获取报告生成的结构化事件日志（逐步时间线，可回放）。"""
    if not report_store.get(report_id):
        return jsonify({"error": t("not_found")}), 404
    return jsonify({"report_id": report_id, "events": read_report_log(report_id)})


@report_bp.get("/check/<sim_id>")
def check_report(sim_id: str):
    """检查模拟是否已有报告（供前端解锁 Interview 等交互）。"""
    report = report_store.get_by_simulation(sim_id)
    has = report is not None
    status = report.get("status") if report else None
    return jsonify(
        {
            "simulation_id": sim_id,
            "has_report": has,
            "report_status": status,
            "report_id": report.get("id") if report else None,
            "interview_unlocked": bool(has and status == "completed"),
        }
    )


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
    """与 Report Agent 对话（深度互动，可自主调用检索工具）。"""
    body = request.get_json(silent=True) or {}
    report_id = body.get("report_id")
    message = body.get("message", "")
    chat_history = body.get("chat_history") or []
    report = report_store.get(report_id)
    content = report.get("content", "") if report else ""

    sim = simulation_manager.get(report.get(
        "simulation_id")) if report else None
    graph_id = sim.get("graph_id") if sim else None
    sim_id = sim.get("id") if sim else None

    agent = ReportAgent(graph_id=graph_id, sim_id=sim_id)
    reply = agent.chat(content, message, chat_history=chat_history)
    return jsonify({"reply": reply, "response": reply,
                    "tool_calls": agent.tool_trace})


@report_bp.post("/chat/stream")
def chat_stream():
    """与 Report Agent 流式对话（SSE）：可自主调用检索工具后逐字输出回答。"""
    body = request.get_json(silent=True) or {}
    report_id = body.get("report_id")
    message = (body.get("message") or "").strip()
    chat_history = body.get("chat_history") or []
    report = report_store.get(report_id)
    content = report.get("content", "") if report else ""
    sim = simulation_manager.get(report.get(
        "simulation_id")) if report else None
    graph_id = sim.get("graph_id") if sim else None
    sim_id = sim.get("id") if sim else None
    has_llm = config.has_llm()

    def gen():
        if not has_llm:
            yield "data: " + json.dumps(
                {"delta": "（需配置 LLM 后可与报告 Agent 对话）"}, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"done": True}) + "\n\n"
            return
        got = False
        try:
            agent = ReportAgent(graph_id=graph_id, sim_id=sim_id)
            for tok in agent.chat_stream(content, message, chat_history=chat_history):
                if tok:
                    got = True
                    yield "data: " + json.dumps({"delta": tok}, ensure_ascii=False) + "\n\n"
        except Exception as e:  # noqa: BLE001
            logger.warning("报告流式对话失败：%s", e)
        if not got:
            yield "data: " + json.dumps({"delta": "（生成失败，请稍后重试）"}, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps({"done": True}) + "\n\n"

    return Response(
        stream_with_context(gen()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
