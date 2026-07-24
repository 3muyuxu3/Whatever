"""ReACT 报告生成 Agent 及报告存储。

采用 ReACT（推理-行动）模式：
1. 规划阶段：结合图谱规模与样本事实，用「上帝视角/未来预测报告」提示词规划 2-5 个章节；
2. 生成阶段：**逐章节独立多轮 ReACT**，每章自主多次调用检索工具获取针对性证据，
   基于「模拟世界即未来预演」的理念撰写，强制引用原文、禁用小标题；
3. 后处理：清理重复/多余标题层级，组装为完整 Markdown。

本项目 FREE 计划优化：
- 检索工具全部走本地内存检索（复用 graph_builder 的 15s 缓存），逐章多轮调用**零额外 Zep 请求**；
- 保留 SSE 流式对话、离线采访兜底、LLM 不可用时的多级优雅降级。
"""

import json
import os
import re
import threading
import time
import uuid

from ..config import config
from ..utils.atomic_json import atomic_write_json, read_json
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
        self._reports = read_json(self._path, default={}) or {}

    def _save(self):
        config.ensure_dirs()
        # 原子写入，避免写入中崩溃导致报告数据损坏
        atomic_write_json(self._path, self._reports)

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
DEFAULT_OUTLINE = ["预测场景与核心发现", "关键实体与关系演化",
                   "群体舆论演化", "风险与机会", "未来走向预测"]

# 合法工具名（供裸 JSON 兜底解析校验）
VALID_TOOL_NAMES = {"QuickSearch", "PanoramaSearch",
                    "InsightForge", "InterviewAgents"}


class ReportEventLogger:
    """报告生成过程的结构化 JSONL 日志（逐步可回放）。

    写入 data/reports/<report_id>/agent_log.jsonl，每行一个完整 JSON，包含
    ts / elapsed_seconds / action / stage / details，前端可轮询回放生成时间线。
    """

    def __init__(self, report_id: str):
        self.report_id = report_id
        self.path = os.path.join(
            config.DATA_DIR, "reports", report_id, "agent_log.jsonl")
        self._start = time.time()
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
        except Exception:  # noqa: BLE001
            pass

    def log(self, action: str, stage: str, **details) -> None:
        entry = {
            "ts": time.time(),
            "elapsed_seconds": round(time.time() - self._start, 2),
            "report_id": self.report_id,
            "action": action,
            "stage": stage,
            "details": details,
        }
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:  # noqa: BLE001
            logger.warning("写入报告日志失败（忽略）：%s", e)


def read_report_log(report_id: str) -> list[dict]:
    """读取某份报告的结构化日志（供 API 轮询回放）。"""
    path = os.path.join(config.DATA_DIR, "reports",
                        report_id, "agent_log.jsonl")
    if not os.path.exists(path):
        return []
    events: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception as e:  # noqa: BLE001
        logger.warning("读取报告日志失败：%s", e)
    return events


# ═══════════════════ 提示词模板（ 的「上帝视角/未来预测」体系）═══════════════════

PLAN_SYSTEM_PROMPT = """你是「未来预测报告」的撰写专家，拥有对模拟世界的「上帝视角」——可洞察模拟中每个 Agent 的行为、言论与互动。

【核心理念】我们构建了一个模拟世界并注入特定「预测需求」作为变量，模拟的演化结果就是对未来的预演。你观察的不是实验数据，而是「未来的预演」。

【任务】规划一份未来预测报告的章节结构，回答：在设定条件下未来发生了什么？各类人群如何反应？揭示了哪些趋势与风险？

【要求】最少 2 个、最多 5 个章节；不设子章节；聚焦核心预测发现。
仅输出 JSON：{"title":"报告标题","summary":"一句话核心发现","sections":[{"title":"章节标题"}]}"""

PLAN_USER_TEMPLATE = """【预测场景（注入变量）】{requirement}

【模拟世界规模】
- 实体数量：{node_count}
- 关系数量：{edge_count}
- 实体类型：{entity_types}

【模拟预测到的部分事实样本】
{sample_facts}

请以上帝视角审视这场未来预演，设计最合适的报告章节结构（2-5 个章节）。"""

SECTION_SYSTEM_TEMPLATE = """你是「未来预测报告」撰写专家，正在撰写其中一个章节。

报告标题：{report_title}
报告摘要：{report_summary}
预测场景（模拟需求）：{requirement}
当前章节：{section_title}

【核心理念】模拟世界是对未来的预演；模拟中 Agent 的行为与互动就是对未来人群行为的预测。请揭示「在设定条件下未来会怎样」，而非分析现实现状。

【最重要的规则】
1. 必须调用工具观察模拟世界：所有内容来自模拟中发生的事件与 Agent 言行，禁止使用你自己的知识编造；本章至少调用 {min_calls} 次工具（最多 {max_calls} 次）。
2. 必须引用 Agent 的原始言行作为预测证据，使用引用块：
   > "……原文……"
3. 语言一致性：引用的其他语言内容须翻译为中文后再写入，保持原意。
4. 忠实呈现：不添加模拟中不存在的信息；信息不足时如实说明。

【格式规范（极重要）】
- 一个章节 = 最小内容单位；❌ 禁止在章节内使用任何 Markdown 标题（#/##/###）。
- ✅ 用 **粗体** 代替小节标题；用列表、空行组织内容。
- ✅ 章节主标题由系统自动添加，你只写纯正文。
- 引用块须独立成段，前后各留一个空行。

【可用检索工具】（每章调用 {min_calls}-{max_calls} 次，建议混用不同工具）
{tools_description}

【工作流程】每次回复只能二选一：
选项A - 调用工具：输出思考后，用如下格式调用一个工具（系统会返回结果，你不能自行编造结果）：
<tool_call>{{"name":"工具名","parameters":{{"query":"检索式"}}}}</tool_call>
选项B - 输出最终内容：以 "Final Answer:" 开头输出纯正文章节内容（无任何标题）。
⚠️ 禁止在一次回复中同时包含工具调用与 Final Answer；每次最多调用一个工具。"""

SECTION_USER_TEMPLATE = """已完成的章节内容（请仔细阅读，避免重复）：
{previous_content}

【当前任务】撰写章节：{section_title}
1. 先思考本章需要哪些模拟信息；
2. 调用工具获取模拟数据（混用不同工具）；
3. 收集足够信息后以 "Final Answer:" 开头输出纯正文（禁止任何标题，用 **粗体** 代替小节标题，引用 Agent 原文）。"""

OBSERVATION_TEMPLATE = """Observation（工具 {tool_name} 返回）：

{result}

──────────
已调用工具 {count}/{max_calls} 次（已用：{used}）。{unused_hint}
- 信息充分：以 "Final Answer:" 开头输出章节内容（须引用上述原文）；
- 需要更多信息：再调用一个工具。"""

TOOL_DESCRIPTIONS = {
    "InsightForge": "深度洞察检索：聚合事实、核心实体与关系链，适合深入分析某话题（参数 query）",
    "PanoramaSearch": "广度全景检索：覆盖事实与实体，区分「当前有效」与「历史/已失效」事实，适合了解事件全貌与演变（参数 query）",
    "QuickSearch": "快速检索：验证某个具体信息点（参数 query）",
    "InterviewAgents": "采访模拟个体：获取不同角色的第一人称观点（参数 query，格式可为 'agent_id|问题' 或直接问题）",
}

# 深度互动对话提示词（：优先基于报告与图谱记忆作答，必要时调用检索工具）
CHAT_SYSTEM_TEMPLATE = """你是 SimulMirror 报告助手，基于已生成的预测报告与模拟世界记忆，回答用户追问。

【已生成的报告】
{report_content}

【规则】
1. 优先基于报告内容回答；报告不足以回答时，可调用检索工具获取更多模拟数据。
2. 回答简洁、有条理；必要时用 > 引用关键原文。

【可用工具】（仅在需要时使用，最多 1-2 次）
{tools_description}

【工具调用格式】（决定调用工具时，仅输出一个）：
<tool_call>{{"name":"工具名","parameters":{{"query":"检索式"}}}}</tool_call>
若无需检索，直接回答。"""


class ReportAgent:
    """ReACT 报告生成 Agent（逐章节多轮 ReACT，本地零 Zep 检索）。"""

    def __init__(self, graph_id: str | None = None, sim_id: str | None = None):
        self.graph_id = graph_id
        self.sim_id = sim_id
        self.client = get_llm_client() if config.has_llm() else None
        # 每章工具调用上下限（本地检索零 Zep，故可多轮；仍保留 config 上限旋钮）
        self.max_tool_calls = max(1, int(config.REPORT_AGENT_MAX_TOOL_CALLS))
        self.min_tool_calls = min(2, self.max_tool_calls)
        self.max_reflection = config.REPORT_AGENT_MAX_REFLECTION_ROUNDS
        # 章节生成温度（ 的 REPORT_AGENT_TEMPERATURE）
        self.section_temperature = float(
            getattr(config, "REPORT_AGENT_TEMPERATURE", 0.5))
        # 本次生成的大纲（规划后置位，供调用方读取）
        self.outline = None
        # ReACT 工具调用轨迹（供前端展示工具活动）
        self.tool_trace: list[dict] = []
        # 结构化事件日志（可选，由 generate 注入）
        self._event_logger = None

    # ---- 工具集（本地内存检索，零额外 Zep 请求） ----
    def _tools(self) -> dict:
        """可用检索工具注册表：name -> (callable(query)->list[dict], description)。"""
        tools: dict = {}
        if self.graph_id:
            from .zep_tools import insight_forge, panorama_search, quick_search

            tools["QuickSearch"] = (
                lambda q: quick_search(self.graph_id, q), TOOL_DESCRIPTIONS["QuickSearch"])
            tools["PanoramaSearch"] = (
                lambda q: panorama_search(self.graph_id, q), TOOL_DESCRIPTIONS["PanoramaSearch"])
            tools["InsightForge"] = (
                lambda q: insight_forge(self.graph_id, q), TOOL_DESCRIPTIONS["InsightForge"])
        if self.sim_id:
            tools["InterviewAgents"] = (
                self._interview_tool, TOOL_DESCRIPTIONS["InterviewAgents"])
        return tools

    def _get_tools_description(self, tools: dict) -> str:
        return "\n".join(f"- {name}: {desc}" for name, (_, desc) in tools.items())

    def _interview_tool(self, query: str) -> list[dict]:
        """InterviewAgents 工具：支持 'agent_id|question' 或直接 question。"""
        agent_id, _, question = (query or "").partition("|")
        if not question:
            question, agent_id = agent_id, ""
        answer = self.interview(agent_id.strip(), question.strip())
        return [{"type": "interview", "text": answer}] if answer else []

    def _tool_result_to_text(self, name: str, results) -> str:
        """将工具返回的结构化结果格式化为可读文本，供 LLM 作为 Observation。"""
        if not results:
            return "（未检索到相关内容）"
        lines: list[str] = []
        # InsightForge 返回 [{question, results:[...]}]
        if name == "InsightForge" and isinstance(results, list) and results and "results" in (results[0] or {}):
            for block in results:
                inner = block.get("results") or []
                for it in inner:
                    txt = (it or {}).get("text", "").strip()
                    if txt:
                        kind = (it or {}).get("type", "")
                        lines.append(
                            f'- [{kind}] "{txt}"' if kind == "fact" else f"- {txt}")
        else:
            for it in results:
                if not isinstance(it, dict):
                    lines.append(f"- {it}")
                    continue
                txt = (it.get("text") or it.get("answer") or "").strip()
                if not txt:
                    continue
                kind = it.get("type", "")
                if kind == "historical_fact":
                    lines.append(f'- [历史/已失效] "{txt}"')
                elif kind == "fact":
                    lines.append(f'- "{txt}"')
                elif kind == "interview":
                    lines.append(f"- 采访回答：{txt}")
                else:
                    lines.append(f"- {txt}")
        return "\n".join(lines[:30]) or "（未检索到相关内容）"

    def _execute_tool(self, name: str, query: str) -> str:
        """执行工具并返回文本化结果，同时记录 tool_trace。"""
        tools = self._tools()
        fn = tools.get(name)
        if not fn:
            return f"（工具 {name} 不可用）"
        try:
            results = fn[0](query)
        except Exception as e:  # noqa: BLE001
            logger.warning("工具 %s 调用失败：%s", name, e)
            results = []
        # 记录命中数（InsightForge 统计内层结果）
        hits = 0
        if name == "InsightForge" and results and isinstance(results, list):
            hits = sum(len((b or {}).get("results") or []) for b in results)
        else:
            hits = len(results or [])
        self.tool_trace.append({"tool": name, "query": query, "hits": hits})
        if self._event_logger:
            self._event_logger.log(
                "tool_call", "generating", tool=name, query=query, hits=hits)
        return self._tool_result_to_text(name, results)

    def _parse_tool_calls(self, response: str) -> list[dict]:
        """从 LLM 响应解析工具调用：优先 <tool_call> XML，其次裸 JSON。"""
        calls: list[dict] = []
        for m in re.finditer(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", response or "", re.DOTALL):
            try:
                calls.append(json.loads(m.group(1)))
            except json.JSONDecodeError:
                pass
        if calls:
            return [c for c in calls if self._valid_call(c)]
        stripped = (response or "").strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                c = json.loads(stripped)
                if self._valid_call(c):
                    return [c]
            except json.JSONDecodeError:
                pass
        return []

    def _valid_call(self, data: dict) -> bool:
        if not isinstance(data, dict):
            return False
        name = data.get("name") or data.get("tool")
        if name in VALID_TOOL_NAMES:
            data["name"] = name
            if "params" in data and "parameters" not in data:
                data["parameters"] = data.pop("params")
            return True
        return False

    # ---- 采访（环境存活时走 IPC 真实 Agent；否则基于人设离线作答） ----
    def interview(self, agent_id: str, question: str) -> str:
        if not self.sim_id:
            return ""
        from .simulation_manager import simulation_manager

        # 环境已进入等待命令模式（常驻）时，采访由真实 OASIS Agent 应答
        if simulation_manager.is_env_alive(self.sim_id):
            from .simulation_ipc import (
                read_interview_response,
                write_interview_request,
            )

            req_id = write_interview_request(self.sim_id, agent_id, question)
            # 真实 Agent 采访需调用 LLM，耗时较长，适当拉高等待上限
            resp = read_interview_response(self.sim_id, req_id, timeout=60)
            answer = (resp or {}).get("answer", "")
            if answer:
                return answer
        return self._offline_agent_answer(agent_id, question)

    def _offline_agent_answer(self, agent_id: str, question: str) -> str:
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

    # ---- 图谱上下文（复用一次缓存读取，供规划使用） ----
    def _graph_context(self) -> dict:
        """读取图谱规模统计与样本事实（复用 15s 缓存，零额外 Zep）。"""
        ctx = {"node_count": 0, "edge_count": 0,
               "entity_types": [], "sample_facts": []}
        if not self.graph_id:
            return ctx
        try:
            from .graph_builder import get_graph_data

            data = get_graph_data(self.graph_id)
            nodes = data.get("nodes", []) or []
            edges = data.get("edges", []) or []
            ctx["node_count"] = len(nodes)
            ctx["edge_count"] = len(edges)
            types = set()
            for n in nodes:
                for lb in (n.get("labels") or []):
                    if lb not in ("Entity", "Node"):
                        types.add(lb)
            ctx["entity_types"] = sorted(types)
            facts = [(e.get("fact") or "").strip()
                     for e in edges if (e.get("fact") or "").strip()]
            ctx["sample_facts"] = facts[:10]
        except Exception as e:  # noqa: BLE001
            logger.warning("读取图谱上下文失败：%s", e)
        return ctx

    # ---- 规划 ----
    def _plan(self, requirement: str, ctx: dict) -> dict:
        """规划报告大纲，返回 {title, summary, sections:[str]}。"""
        fallback = {"title": "未来预测报告",
                    "summary": "基于模拟预测的未来趋势与风险分析",
                    "sections": DEFAULT_OUTLINE}
        if not self.client:
            return fallback
        try:
            user = PLAN_USER_TEMPLATE.format(
                requirement=requirement,
                node_count=ctx.get("node_count", 0),
                edge_count=ctx.get("edge_count", 0),
                entity_types=", ".join(
                    ctx.get("entity_types", [])) or "（未知）",
                sample_facts="\n".join(
                    f"- {f}" for f in ctx.get("sample_facts", [])) or "（暂无样本）",
            )
            data = self.client.chat_json(
                [
                    {"role": "system", "content": PLAN_SYSTEM_PROMPT},
                    {"role": "user", "content": user},
                ],
                temperature=0.3,
            )
            sections = [
                (s.get("title") if isinstance(s, dict) else str(s))
                for s in (data.get("sections") or [])
            ]
            sections = [s for s in sections if s]
            if not sections:
                sections = DEFAULT_OUTLINE
            return {
                "title": data.get("title") or "未来预测报告",
                "summary": data.get("summary") or "",
                "sections": sections[:5],
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("大纲规划失败，使用默认大纲：%s", e)
            return fallback

    # ---- 逐章节多轮 ReACT ----
    def _generate_section_react(self, section: str, requirement: str,
                                report_title: str, report_summary: str,
                                previous: list[str]) -> str:
        """用 ReACT 模式生成单章节内容（本地工具多轮检索，零额外 Zep）。"""
        tools = self._tools()
        # 无工具（无 graph_id/sim_id）时退化为单次撰写
        if not tools or not self.client:
            return self._write_section_plain(section, requirement, previous)

        all_tool_names = set(tools.keys())
        system = SECTION_SYSTEM_TEMPLATE.format(
            report_title=report_title, report_summary=report_summary,
            requirement=requirement, section_title=section,
            min_calls=self.min_tool_calls, max_calls=self.max_tool_calls,
            tools_description=self._get_tools_description(tools),
        )
        prev_text = "\n\n---\n\n".join(
            (s[:3000] + "..." if len(s) > 3000 else s) for s in previous
        ) if previous else "（这是第一个章节）"
        user = SECTION_USER_TEMPLATE.format(
            previous_content=prev_text, section_title=section)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        tool_calls_count = 0
        used_tools: set[str] = set()
        conflict_retries = 0
        max_iterations = self.max_tool_calls + 2

        for _ in range(max_iterations):
            try:
                response = self.client.chat(
                    messages, temperature=self.section_temperature, max_tokens=4096)
            except Exception as e:  # noqa: BLE001
                logger.warning("章节生成 LLM 调用失败：%s", e)
                break
            if not response:
                break

            tool_calls = self._parse_tool_calls(response)
            has_tools = bool(tool_calls)
            has_final = "Final Answer:" in response

            # 冲突：同时出现工具调用与 Final Answer
            if has_tools and has_final:
                conflict_retries += 1
                if conflict_retries <= 2:
                    messages.append(
                        {"role": "assistant", "content": response})
                    messages.append({"role": "user", "content": (
                        "【格式错误】一次回复只能二选一：要么调用一个工具，要么以 'Final Answer:' 输出内容。请重新回复。")})
                    continue
                # 第三次：截断到首个工具调用，强制执行工具
                cut = response.find("</tool_call>")
                if cut != -1:
                    tool_calls = self._parse_tool_calls(
                        response[:cut + len("</tool_call>")])
                    has_tools = bool(tool_calls)
                has_final = False
                conflict_retries = 0

            # 情况1：Final Answer
            if has_final:
                if tool_calls_count < self.min_tool_calls:
                    messages.append(
                        {"role": "assistant", "content": response})
                    unused = all_tool_names - used_tools
                    hint = f"（还没用过：{', '.join(unused)}）" if unused else ""
                    messages.append({"role": "user", "content": (
                        f"你只调用了 {tool_calls_count} 次工具，至少需要 {self.min_tool_calls} 次。请再检索后再输出 Final Answer。{hint}")})
                    continue
                return response.split("Final Answer:")[-1].strip()

            # 情况2：工具调用
            if has_tools:
                if tool_calls_count >= self.max_tool_calls:
                    messages.append(
                        {"role": "assistant", "content": response})
                    messages.append({"role": "user", "content": (
                        f"工具调用已达上限（{self.max_tool_calls}），请立即以 'Final Answer:' 输出章节内容。")})
                    continue
                call = tool_calls[0]
                name = call.get("name")
                query = (call.get("parameters") or {}).get(
                    "query") or section
                result_text = self._execute_tool(name, query)
                tool_calls_count += 1
                used_tools.add(name)
                unused = all_tool_names - used_tools
                unused_hint = (f"建议试试未用过的工具：{', '.join(unused)}"
                               if unused and tool_calls_count < self.max_tool_calls else "")
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": OBSERVATION_TEMPLATE.format(
                    tool_name=name, result=result_text, count=tool_calls_count,
                    max_calls=self.max_tool_calls, used=", ".join(used_tools),
                    unused_hint=unused_hint,
                )})
                continue

            # 情况3：既无工具也无 Final Answer
            messages.append({"role": "assistant", "content": response})
            if tool_calls_count < self.min_tool_calls:
                messages.append({"role": "user", "content": (
                    f"请先调用工具获取模拟数据（至少 {self.min_tool_calls} 次）再输出内容。")})
                continue
            # 工具已足够，直接把这段作为正文
            return response.strip()

        # 达到迭代上限，强制收尾
        messages.append({"role": "user", "content": (
            "请立即基于已获取的信息，以 'Final Answer:' 开头输出章节内容（纯正文，无标题）。")})
        try:
            response = self.client.chat(
                messages, temperature=self.section_temperature, max_tokens=4096) or ""
        except Exception:  # noqa: BLE001
            response = ""
        if "Final Answer:" in response:
            return response.split("Final Answer:")[-1].strip()
        return response.strip() or self._write_section_plain(section, requirement, previous)

    def _write_section_plain(self, section: str, requirement: str,
                             previous: list[str]) -> str:
        """无工具/无 LLM 时的简单章节撰写（含反思）。"""
        if not self.client:
            return f"（本章节需配置 LLM 后自动生成）"
        try:
            content = self.client.chat(
                [
                    {"role": "system",
                        "content": "你是严谨的未来预测分析师，基于模拟预测撰写报告章节，避免臆测，禁止使用 Markdown 标题。"},
                    {"role": "user", "content": (
                        f"预测需求：{requirement}\n章节：{section}\n请撰写该章节纯正文内容。")},
                ]
            )
        except Exception:  # noqa: BLE001
            return f"（本章节生成失败）"
        for _ in range(self.max_reflection):
            try:
                content = self.client.chat(
                    [
                        {"role": "system",
                            "content": "审阅并改进以下章节，使其更准确、有据可依、结构清晰；仅输出改进后的正文，禁止标题。"},
                        {"role": "user", "content": content},
                    ]
                )
            except Exception:  # noqa: BLE001
                break
        return content

    # ---- 后处理：清理章节正文中的多余标题 ----
    @staticmethod
    def _post_process_section(content: str, section_title: str) -> str:
        """移除章节正文里误加的标题（含与章节同名的标题），级别标题转粗体。"""
        lines = []
        for line in (content or "").split("\n"):
            m = re.match(r"^(#{1,6})\s+(.+?)\s*$", line.strip())
            if m:
                title = m.group(2).strip()
                if title == section_title:
                    continue  # 丢弃与章节同名的重复标题
                lines.append(f"**{title}**")  # 其余标题降级为粗体
            else:
                lines.append(line)
        # 压缩连续空行（最多 1 个）
        out, empty = [], 0
        for ln in lines:
            if ln.strip() == "":
                empty += 1
                if empty <= 1:
                    out.append(ln)
            else:
                empty = 0
                out.append(ln)
        return "\n".join(out).strip()

    # ---- 兜底报告 ----
    def _fallback(self, requirement: str, actions: list[dict]) -> str:
        summary = _summarize_actions(actions)
        sections = "\n\n".join(
            f"## {s}\n\n（需配置 LLM 后自动生成）" for s in DEFAULT_OUTLINE)
        return (
            f"# SimulMirror 未来预测报告\n\n"
            f"> 预测需求：{requirement}\n\n"
            f"## 模拟动作摘要\n\n{summary}\n\n{sections}\n"
        )

    # ---- 主流程 ----
    def generate(self, requirement: str, actions: list[dict], on_progress=None,
                 on_plan=None, on_section=None, event_logger=None) -> str:
        """生成完整报告（逐章节多轮 ReACT）。

        :param on_plan:    大纲就绪回调 (outline_dict) -> None（供前端提前展示章节列表）
        :param on_section: 单章节完成回调 (index:int, title:str, content:str) -> None
                           （供前端分章节实时展示，无需等整篇完成）
        :param event_logger: 可选的结构化事件日志器（逐步写 JSONL，供回放）
        """
        self.tool_trace = []
        self._event_logger = event_logger
        if event_logger:
            event_logger.log("report_start", "pending", requirement=requirement,
                             graph_id=self.graph_id, action_count=len(actions))
        if not self.client:
            if on_progress:
                on_progress(100)
            return self._fallback(requirement, actions)

        ctx = self._graph_context()
        if on_progress:
            on_progress(8)
        outline = self._plan(requirement, ctx)
        sections = outline["sections"]
        n = max(1, len(sections))
        self.outline = outline
        if on_plan:
            try:
                on_plan(outline)
            except Exception:  # noqa: BLE001
                pass
        if event_logger:
            event_logger.log("planning_complete", "planning", outline=outline)
        if on_progress:
            on_progress(15)

        parts = [f"# {outline['title']}\n"]
        if outline.get("summary"):
            parts.append(f"> {outline['summary']}\n")
        parts.append(f"> 预测需求：{requirement}\n\n---")

        # 动作摘要作为所有章节的公共背景（避免章节凭空编造模拟规模）
        action_summary = _summarize_actions(actions)

        generated: list[str] = []
        for i, section in enumerate(sections):
            if on_progress:
                on_progress(int(15 + 80 * i / n))
            if event_logger:
                event_logger.log("section_start", "generating",
                                 index=i, section_title=section)
            body = self._generate_section_react(
                section, requirement, outline["title"],
                outline.get("summary", ""),
                generated +
                ([f"【模拟动作摘要】\n{action_summary}"] if i == 0 else []),
            )
            body = self._post_process_section(body, section)
            generated.append(f"## {section}\n\n{body}")
            parts.append(f"## {section}\n\n{body}")
            if event_logger:
                event_logger.log("section_complete", "generating", index=i,
                                 section_title=section, content_length=len(body))
            if on_section:
                try:
                    on_section(i, section, body)
                except Exception:  # noqa: BLE001
                    pass
            if on_progress:
                on_progress(int(15 + 80 * (i + 1) / n))

        if on_progress:
            on_progress(100)
        if event_logger:
            event_logger.log("report_complete", "completed", total_sections=n)
        return "\n\n".join(parts)

    # ---- 深度互动对话（：报告 Agent 可自主调用检索工具） ----
    def _chat_messages(self, report_content: str, message: str,
                       chat_history: list | None = None):
        """构建对话初始消息列表，返回 (messages, tools)。"""
        tools = self._tools()
        system = CHAT_SYSTEM_TEMPLATE.format(
            report_content=(report_content or "（暂无报告）")[:6000],
            tools_description=self._get_tools_description(
                tools) or "（无可用检索工具）",
        )
        messages = [{"role": "system", "content": system}]
        for h in (chat_history or [])[-8:]:
            if isinstance(h, dict) and h.get("role") and h.get("content"):
                messages.append(
                    {"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": message})
        return messages, tools

    def _chat_react(self, messages: list, tools: dict, max_calls: int = 2):
        """至多 max_calls 轮工具检索（ReACT）。

        返回 (messages, direct_answer)：direct_answer 非空时表示模型已直接作答。
        否则 messages 已追加工具 Observation，由调用方进行最终作答。
        """
        if not tools:
            return messages, None
        for _ in range(max_calls):
            try:
                resp = self.client.chat(messages)
            except Exception:  # noqa: BLE001
                return messages, None
            tool_calls = self._parse_tool_calls(resp)
            if not tool_calls:
                return messages, (resp or "").strip()
            call = tool_calls[0]
            name = call.get("name")
            query = (call.get("parameters") or {}).get("query") or ""
            result = self._execute_tool(name, query)
            messages.append({"role": "assistant", "content": resp})
            messages.append({"role": "user", "content": (
                f"检索结果（{name}）：\n{result}\n\n请基于以上资料简洁回答用户问题。")})
        return messages, None

    def chat(self, report_content: str, message: str,
             chat_history: list | None = None) -> str:
        """基于报告与图谱记忆的多轮对话（可自主调用检索工具）。"""
        if not self.client:
            return "（需配置 LLM 后可与报告 Agent 对话）"
        self.tool_trace = []
        messages, tools = self._chat_messages(
            report_content, message, chat_history)
        messages, direct = self._chat_react(messages, tools)
        if direct:
            return direct
        try:
            return self.client.chat(messages)
        except Exception as e:  # noqa: BLE001
            logger.warning("报告对话失败：%s", e)
            return "（生成失败，请稍后重试）"

    def chat_stream(self, report_content: str, message: str,
                    chat_history: list | None = None):
        """流式报告对话：先（必要时）检索工具，再流式输出最终答案。"""
        if not self.client:
            yield "（需配置 LLM 后可与报告 Agent 对话）"
            return
        self.tool_trace = []
        messages, tools = self._chat_messages(
            report_content, message, chat_history)
        # 先同步完成工具检索阶段（不流式），将 Observation 追加到上下文
        if tools:
            self._chat_react(messages, tools)
        # 追加明确作答指令，避免模型在流式阶段再次尝试调用工具
        messages.append({"role": "user", "content": "请给出最终回答（不要再调用工具）。"})
        try:
            for tok in self.client.chat_stream(messages):
                if tok:
                    yield tok
        except Exception as e:  # noqa: BLE001
            logger.warning("报告流式对话失败：%s", e)
            yield "（生成失败，请稍后重试）"


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
