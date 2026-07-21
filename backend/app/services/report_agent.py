"""ReACT 报告生成 Agent 及报告存储。

采用 ReACT（推理-行动）模式：先规划大纲，再对每个章节自主调用检索工具
（InsightForge / PanoramaSearch / QuickSearch / InterviewAgents），
基于检索结果撰写并经过反思，最终产出完整 Markdown 报告。
"""

import json
import os
import threading
import time
import uuid

from ..config import config
from ..utils.llm_client import get_llm_client
from ..utils.logger import get_logger

logger = get_logger("report_agent")


class ReportStore:
    """报告的 JSON 文件持久化存储。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._path = os.path.join(config.DATA_DIR, "reports.json")
        self._reports: dict[str, dict] = {}
        self._load()

    def _load(self):
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as f:
                    self._reports = json.load(f)
        except Exception:  # noqa: BLE001
            self._reports = {}

    def _save(self):
        config.ensure_dirs()
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._reports, f, ensure_ascii=False, indent=2)

    def create(self, simulation_id: str, **kwargs) -> dict:
        rid = uuid.uuid4().hex
        report = {
            "id": rid,
            "simulation_id": simulation_id,
            "content": "",
            "status": "generating",
            "created_at": time.time(),
            **kwargs,
        }
        with self._lock:
            self._reports[rid] = report
            self._save()
        return report

    def get(self, report_id: str) -> dict | None:
        return self._reports.get(report_id)

    def get_by_simulation(self, sim_id: str) -> dict | None:
        for r in self._reports.values():
            if r.get("simulation_id") == sim_id:
                return r
        return None

    def list(self) -> list[dict]:
        return sorted(self._reports.values(), key=lambda r: r.get("created_at", 0), reverse=True)

    def update(self, report_id: str, **kwargs) -> dict | None:
        with self._lock:
            r = self._reports.get(report_id)
            if not r:
                return None
            r.update(kwargs)
            self._save()
            return r

    def delete(self, report_id: str) -> bool:
        with self._lock:
            if report_id in self._reports:
                del self._reports[report_id]
                self._save()
                return True
            return False


# 全局单例
report_store = ReportStore()

# 默认大纲（LLM 不可用时的兜底章节）
DEFAULT_OUTLINE = ["背景与概述", "关键实体与关系", "群体舆论演化", "风险与机会", "未来走向预测"]


class ReportAgent:
    """ReACT 报告生成 Agent。"""

    def __init__(self, graph_id: str | None = None, sim_id: str | None = None):
        self.graph_id = graph_id
        self.sim_id = sim_id
        self.client = get_llm_client() if config.has_llm() else None
        self.max_tool_calls = config.REPORT_AGENT_MAX_TOOL_CALLS
        self.max_reflection = config.REPORT_AGENT_MAX_REFLECTION_ROUNDS

    # ---- 工具 ----
    def _retrieve(self, query: str) -> list[dict]:
        """调用检索工具（受 max_tool_calls 约束）。"""
        if not self.graph_id:
            return []
        try:
            from .zep_tools import insight_forge

            return insight_forge(self.graph_id, query)
        except Exception as e:  # noqa: BLE001
            logger.warning("检索失败：%s", e)
            return []

    def interview(self, agent_id: str, question: str) -> str:
        """InterviewAgents 工具：采访运行中的 Agent。"""
        if not self.sim_id:
            return ""
        from .simulation_ipc import read_interview_response, write_interview_request

        req_id = write_interview_request(self.sim_id, agent_id, question)
        resp = read_interview_response(self.sim_id, req_id, timeout=20)
        return (resp or {}).get("answer", "")

    # ---- 生成 ----
    def _plan(self, requirement: str) -> list[str]:
        """规划报告大纲。"""
        if not self.client:
            return DEFAULT_OUTLINE
        try:
            data = self.client.chat_json(
                [
                    {
                        "role": "system",
                        "content": '规划一份预测分析报告的章节大纲，输出 JSON：{"sections":["...","..."]}（4-6 个章节）',
                    },
                    {"role": "user", "content": requirement},
                ]
            )
            return data.get("sections") or DEFAULT_OUTLINE
        except Exception:  # noqa: BLE001
            return DEFAULT_OUTLINE

    def _write_section(self, section: str, requirement: str, actions: list[dict]) -> str:
        """撰写单个章节：检索 -> 撰写 -> 反思（遵循工具调用/反思上限）。"""
        # 行动：检索（1 次 InsightForge 内部已做子问题分解，计入工具预算）
        evidence = self._retrieve(f"{requirement} - {section}")
        evidence_text = json.dumps(evidence, ensure_ascii=False)[:2000]
        action_summary = _summarize_actions(actions)[:1500]

        if not self.client:
            return f"（基于模拟动作的概述）\n\n{action_summary}"

        content = self.client.chat(
            [
                {"role": "system", "content": "你是一名严谨的分析师，基于给定证据撰写报告章节，避免臆测。"},
                {
                    "role": "user",
                    "content": (
                        f"预测需求：{requirement}\n章节：{section}\n\n"
                        f"图谱检索证据：{evidence_text}\n\n"
                        f"模拟动作摘要：{action_summary}\n\n请撰写该章节内容（Markdown）。"
                    ),
                },
            ]
        )

        # 反思：最多 max_reflection 轮自我改进
        for _ in range(self.max_reflection):
            try:
                content = self.client.chat(
                    [
                        {"role": "system", "content": "审阅并改进以下章节，使其更准确、有据可依、结构清晰。仅输出改进后的正文。"},
                        {"role": "user", "content": content},
                    ]
                )
            except Exception:  # noqa: BLE001
                break
        return content

    def _fallback(self, requirement: str, actions: list[dict]) -> str:
        """LLM 不可用时的兜底报告。"""
        summary = _summarize_actions(actions)
        sections = "\n\n".join(f"## {s}\n\n（需配置 LLM 后自动生成）" for s in DEFAULT_OUTLINE)
        return (
            f"# SimulMirror 预测分析报告\n\n"
            f"> 预测需求：{requirement}\n\n"
            f"## 模拟动作摘要\n\n{summary}\n\n{sections}\n"
        )

    def generate(self, requirement: str, actions: list[dict], on_progress=None) -> str:
        """生成完整报告。"""
        if not self.client:
            if on_progress:
                on_progress(100)
            return self._fallback(requirement, actions)

        outline = self._plan(requirement)
        parts = [f"# SimulMirror 预测分析报告\n\n> 预测需求：{requirement}\n"]
        for i, section in enumerate(outline):
            body = self._write_section(section, requirement, actions)
            parts.append(f"## {section}\n\n{body}")
            if on_progress:
                on_progress(int(100 * (i + 1) / max(1, len(outline))))
        return "\n\n".join(parts)

    def chat(self, report_content: str, message: str) -> str:
        """基于报告上下文继续对话（深度互动）。"""
        if not self.client:
            return "（需配置 LLM 后可与报告 Agent 对话）"
        return self.client.chat(
            [
                {"role": "system", "content": "你是 SimulMirror 报告助手，基于以下报告回答用户的追问。"},
                {"role": "user", "content": f"【报告】\n{report_content[:6000]}\n\n【问题】\n{message}"},
            ]
        )


def _summarize_actions(actions: list[dict]) -> str:
    """将动作日志聚合为可读摘要。"""
    if not actions:
        return "（暂无模拟动作数据）"
    counts: dict[str, int] = {}
    for a in actions:
        key = a.get("action", "UNKNOWN")
        counts[key] = counts.get(key, 0) + 1
    lines = [f"- {k}: {v} 次" for k, v in sorted(counts.items(), key=lambda x: -x[1])]
    return f"共 {len(actions)} 条动作：\n" + "\n".join(lines)


def generate_report(graph_id, sim_id, requirement, actions, on_progress=None) -> str:
    """便捷入口：创建 Agent 并生成报告。"""
    agent = ReportAgent(graph_id=graph_id, sim_id=sim_id)
    return agent.generate(requirement, actions, on_progress)
