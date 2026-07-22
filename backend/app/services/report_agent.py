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
        # ReACT 工具调用轨迹（供前端展示工具活动）
        self.tool_trace: list[dict] = []

    # ---- 工具集 ----
    def _tools(self) -> dict:
        """可用检索工具注册表：name -> (callable(query)->list[dict], description)。

        仅在具备相应上下文（graph_id / sim_id）时才注册对应工具。
        """
        tools: dict = {}
        if self.graph_id:
            from .zep_tools import insight_forge, panorama_search, quick_search

            tools["QuickSearch"] = (
                lambda q: quick_search(self.graph_id, q), "快速事实检索")
            tools["PanoramaSearch"] = (
                lambda q: panorama_search(self.graph_id, q), "广度全景检索")
            tools["InsightForge"] = (lambda q: insight_forge(
                self.graph_id, q), "深度归因（子问题分解）")
        if self.sim_id:
            tools["InterviewAgents"] = (self._interview_tool, "采访模拟世界中的个体")
        return tools

    def _interview_tool(self, query: str) -> list[dict]:
        """InterviewAgents 工具：支持 'agent_id|question' 或直接 question。"""
        agent_id, _, question = (query or "").partition("|")
        if not question:
            question, agent_id = agent_id, ""
        answer = self.interview(agent_id.strip(), question.strip())
        return [{"type": "interview", "text": answer}] if answer else []

    def _gather_evidence(self, query: str) -> list[dict]:
        """ReACT 检索：由 LLM 选择工具并给出检索式，逐一执行并聚合证据。

        无 LLM / 无图谱时降级：尽力做一次 InsightForge。
        """
        tools = self._tools()
        if not tools:
            return []
        # 无 LLM：无法规划工具，直接回退到 InsightForge / QuickSearch
        if not self.client:
            for name in ("InsightForge", "QuickSearch"):
                if name in tools:
                    try:
                        res = tools[name][0](query)
                        self.tool_trace.append(
                            {"tool": name, "query": query, "hits": len(res or [])})
                        return [{"tool": name, "query": query, "results": res}]
                    except Exception as e:  # noqa: BLE001
                        logger.warning("检索失败：%s", e)
            return []
        # 有 LLM：让模型选择 1-3 个工具
        try:
            plan = self.client.chat_json(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是检索规划器。可用工具："
                            + "；".join(f"{k}（{v[1]}）" for k,
                                       v in tools.items())
                            + '。请为给定查询选择 1-3 个工具并给出各自检索式，'
                            '输出 JSON：{"calls":[{"tool":"QuickSearch","query":"..."}]}'
                        ),
                    },
                    {"role": "user", "content": query},
                ]
            )
            calls = plan.get("calls") or []
        except Exception:  # noqa: BLE001
            calls = [{"tool": "InsightForge", "query": query}]

        evidence = []
        for c in calls[: self.max_tool_calls]:
            name = c.get("tool")
            q = c.get("query") or query
            fn = tools.get(name)
            if not fn:
                continue
            try:
                res = fn[0](q)
                self.tool_trace.append(
                    {"tool": name, "query": q, "hits": len(res or [])})
                evidence.append({"tool": name, "query": q, "results": res})
            except Exception as e:  # noqa: BLE001
                logger.warning("工具 %s 调用失败：%s", name, e)
        return evidence

    def interview(self, agent_id: str, question: str) -> str:
        """InterviewAgents 工具：采访 Agent。

        仅当模拟子进程仍在运行时走文件 IPC；模拟已结束（报告生成的常态）
        时直接基于人设用 LLM 作答，避免空等 IPC 超时（每次白白阻塞 20s）。
        """
        if not self.sim_id:
            return ""
        from .simulation_manager import simulation_manager

        if simulation_manager.is_running(self.sim_id):
            from .simulation_ipc import (
                read_interview_response,
                write_interview_request,
            )

            req_id = write_interview_request(self.sim_id, agent_id, question)
            resp = read_interview_response(self.sim_id, req_id, timeout=8)
            answer = (resp or {}).get("answer", "")
            if answer:
                return answer
        return self._offline_agent_answer(agent_id, question)

    def _offline_agent_answer(self, agent_id: str, question: str) -> str:
        """模拟未运行时，基于人设用 LLM 直接作答。"""
        if not self.client:
            return ""
        from .simulation_manager import simulation_manager

        profiles = simulation_manager.read_profiles(self.sim_id)
        profile = next(
            (p for p in profiles
             if p.get("entity_uuid") == agent_id or p.get("name") == agent_id),
            None,
        )
        name = (profile or {}).get("name") or agent_id or "Agent"
        bits = []
        if profile:
            for key in ("bio", "persona", "occupation", "mbti"):
                if profile.get(key):
                    bits.append(f"{key}: {profile[key]}")
            if profile.get("interests"):
                bits.append("interests: " + ", ".join(profile["interests"]))
        persona = "\n".join(bits) or "（无额外人设信息）"
        try:
            return self.client.chat(
                [
                    {"role": "system", "content": (
                        f"你在扮演社交模拟世界中的人物：{name}。\n人设：\n{persona}\n"
                        "请以第一人称、贴合人设地简洁作答（2-4 句）。")},
                    {"role": "user", "content": question},
                ]
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("离线采访作答失败：%s", e)
            return ""

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
        # 行动：ReACT 多工具检索（由 LLM 选择 QuickSearch/PanoramaSearch/InsightForge/InterviewAgents）
        evidence = self._gather_evidence(f"{requirement} - {section}")
        evidence_text = json.dumps(evidence, ensure_ascii=False)[:2500]
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
                        {"role": "system",
                            "content": "审阅并改进以下章节，使其更准确、有据可依、结构清晰。仅输出改进后的正文。"},
                        {"role": "user", "content": content},
                    ]
                )
            except Exception:  # noqa: BLE001
                break
        return content

    def _fallback(self, requirement: str, actions: list[dict]) -> str:
        """LLM 不可用时的兜底报告。"""
        summary = _summarize_actions(actions)
        sections = "\n\n".join(
            f"## {s}\n\n（需配置 LLM 后自动生成）" for s in DEFAULT_OUTLINE)
        return (
            f"# SimulMirror 预测分析报告\n\n"
            f"> 预测需求：{requirement}\n\n"
            f"## 模拟动作摘要\n\n{summary}\n\n{sections}\n"
        )

    def generate(self, requirement: str, actions: list[dict], on_progress=None) -> str:
        """生成完整报告。"""
        self.tool_trace = []
        if not self.client:
            if on_progress:
                on_progress(100)
            return self._fallback(requirement, actions)

        outline = self._plan(requirement)
        parts = [f"# SimulMirror 预测分析报告\n\n> 预测需求：{requirement}\n"]
        n = max(1, len(outline))
        if on_progress:
            on_progress(10)  # 大纲就绪
        for i, section in enumerate(outline):
            # 进入第 i 节：先推进一步进度，避免单节耗时较长时前端看起来“卡住”
            if on_progress:
                on_progress(int(10 + 88 * i / n))
            body = self._write_section(section, requirement, actions)
            parts.append(f"## {section}\n\n{body}")
            if on_progress:
                on_progress(int(10 + 88 * (i + 1) / n))
        if on_progress:
            on_progress(100)
        return "\n\n".join(parts)

    def chat(self, report_content: str, message: str) -> str:
        """基于报告上下文继续对话（深度互动）。"""
        if not self.client:
            return "（需配置 LLM 后可与报告 Agent 对话）"
        return self.client.chat(
            [
                {"role": "system", "content": "你是 SimulMirror 报告助手，基于以下报告回答用户的追问。"},
                {"role": "user",
                    "content": f"【报告】\n{report_content[:6000]}\n\n【问题】\n{message}"},
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
    lines = [f"- {k}: {v} 次" for k,
             v in sorted(counts.items(), key=lambda x: -x[1])]
    return f"共 {len(actions)} 条动作：\n" + "\n".join(lines)


def generate_report(graph_id, sim_id, requirement, actions, on_progress=None) -> str:
    """便捷入口：创建 Agent 并生成报告。"""
    agent = ReportAgent(graph_id=graph_id, sim_id=sim_id)
    return agent.generate(requirement, actions, on_progress)
