"""模拟生命周期管理。

负责创建/持久化模拟记录、管理工作目录与配置文件、启动/停止子进程、
读取运行状态与动作日志，并在应用退出时清理全部运行中的子进程。
"""

import json
import os
import threading
import time
import uuid

from ..config import config
from ..utils.atomic_json import atomic_write_json, read_json
from ..utils.logger import get_logger
from . import simulation_ipc, simulation_runner

logger = get_logger("sim_manager")

# 终止状态集合
TERMINAL = {"completed", "stopped", "failed"}


class SimulationManager:
    """模拟管理器（单例）。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._path = os.path.join(config.DATA_DIR, "simulations.json")
        self._sims: dict[str, dict] = {}
        self._procs: dict[str, object] = {}  # sim_id -> Popen
        self._proc_lock = threading.Lock()  # 保护 _procs 并发访问（与 _lock 分离，避免重入）
        # 增量状态统计缓存：sim_id -> {offset, action_count, current_round, per_platform, recent}
        # 高频 status() 轮询时按字节偏移增量累积，避免每次全量重读 actions.jsonl
        self._stats: dict[str, dict] = {}
        self._stats_lock = threading.Lock()
        self._load()

    # ---- 持久化 ----
    def _load(self):
        self._sims = read_json(self._path, default={}) or {}

    def _save(self):
        config.ensure_dirs()
        # 原子写入，避免写入中崩溃导致模拟记录损坏
        atomic_write_json(self._path, self._sims)

    # ---- 目录 ----
    def work_dir(self, sim_id: str) -> str:
        d = os.path.join(config.DATA_DIR, "sims", sim_id)
        os.makedirs(d, exist_ok=True)
        return d

    def actions_path(self, sim_id: str) -> str:
        return os.path.join(self.work_dir(sim_id), "actions.jsonl")

    def config_path(self, sim_id: str) -> str:
        return os.path.join(self.work_dir(sim_id), "config.json")

    # ---- CRUD ----
    def create(self, project_id: str, graph_id: str | None = None, **kwargs) -> dict:
        sim_id = uuid.uuid4().hex
        sim = {
            "id": sim_id,
            "project_id": project_id,
            "graph_id": graph_id,
            "status": "created",
            "round": 0,
            "created_at": time.time(),
            **kwargs,
        }
        with self._lock:
            self._sims[sim_id] = sim
            self._save()
        return sim

    def get(self, sim_id: str) -> dict | None:
        return self._sims.get(sim_id)

    def update(self, sim_id: str, **kwargs) -> dict | None:
        with self._lock:
            sim = self._sims.get(sim_id)
            if not sim:
                return None
            sim.update(kwargs)
            self._save()
            return sim

    def save_config(self, sim_id: str, sim_config: dict) -> str:
        """将模拟配置写入工作目录，返回配置文件路径。"""
        path = self.config_path(sim_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sim_config, f, ensure_ascii=False, indent=2)
        self.update(sim_id, status="prepared", config=sim_config)
        return path

    # ---- 运行控制 ----
    def start(self, sim_id: str, mode: str = "parallel", max_rounds: int | None = None,
              enable_graph_memory_update: bool = False) -> dict:
        """启动模拟子进程。

        :param enable_graph_memory_update: 是否在模拟运行期间将 Agent 活动动态写回
            Zep 图谱记忆（ 的 Dynamic temporal memory updates），
            让图谱「记住」这场模拟，供后续报告生成与深度互动复用。
        """
        sim = self.get(sim_id)
        if not sim:
            raise ValueError("模拟不存在")
        # 防止重复启动：已在运行时直接返回当前记录，避免产生无法回收的孤儿子进程
        if self.is_running(sim_id):
            logger.warning("模拟 %s 已在运行，忽略重复启动", sim_id)
            return sim

        work_dir = self.work_dir(sim_id)
        cfg_path = self.config_path(sim_id)
        if not os.path.exists(cfg_path):
            # 若未准备配置，则写入一个最小配置
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"time": {"max_rounds": max_rounds or config.OASIS_DEFAULT_MAX_ROUNDS}},
                    f,
                    ensure_ascii=False,
                )
        elif max_rounds:
            # 将启动时指定的轮数写回配置文件，确保子进程真正按此轮数运行（与状态展示一致）
            try:
                cfg = self.get_config(sim_id)
                cfg.setdefault("time", {})["max_rounds"] = int(max_rounds)
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
            except Exception:  # noqa: BLE001
                pass

        # 清空历史动作日志
        with open(self.actions_path(sim_id), "w", encoding="utf-8"):
            pass
        # 重置增量统计缓存（新一轮模拟从零开始计数）
        self._reset_stats(sim_id)

        proc = simulation_runner.start_simulation_process(
            sim_id, mode, cfg_path, work_dir)
        with self._proc_lock:
            self._procs[sim_id] = proc

        # 动态时序记忆更新：模拟运行期间将 Agent 活动增量写回 Zep 图谱，
        # 让图谱「记住」这场模拟（ 的 Dynamic temporal memory updates）。
        graph_id = sim.get("graph_id")
        memory_enabled = bool(
            enable_graph_memory_update and graph_id and config.has_zep())
        if memory_enabled:
            threading.Thread(
                target=self._memory_update_worker,
                args=(sim_id, graph_id, proc),
                daemon=True,
            ).start()
            logger.info("已启用图谱记忆动态更新：sim=%s graph=%s", sim_id, graph_id)

        return self.update(sim_id, status="running", mode=mode,
                           max_rounds=max_rounds or config.OASIS_DEFAULT_MAX_ROUNDS,
                           graph_memory_update=memory_enabled)

    def _memory_update_worker(self, sim_id: str, graph_id: str, proc) -> None:
        """后台线程：模拟运行期间将新动作增量批量写回 Zep 图谱记忆。

        每 12s 读取一次新动作并写回（update_graph_memory 内部分批 + 全局节流，
        不会打满 Zep FREE 计划配额）；进程结束后再补写剩余动作。
        """
        from .zep_graph_memory_updater import update_graph_memory

        path = self.actions_path(sim_id)
        offset = 0
        try:
            while proc.poll() is None:
                time.sleep(config.MEMORY_UPDATE_INTERVAL)
                new, offset = self._read_actions_since(path, offset)
                if new:
                    try:
                        update_graph_memory(graph_id, new)
                    except Exception as e:  # noqa: BLE001
                        logger.warning("图谱记忆增量写回失败（忽略）：%s", e)
            # 进程结束后补写剩余动作
            new, offset = self._read_actions_since(path, offset)
            if new:
                try:
                    update_graph_memory(graph_id, new)
                except Exception as e:  # noqa: BLE001
                    logger.warning("图谱记忆收尾写回失败（忽略）：%s", e)
            logger.info("图谱记忆动态更新完成：sim=%s", sim_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("图谱记忆更新线程异常：%s", e)

    def read_actions(self, sim_id: str, limit: int = 500) -> list[dict]:
        """读取动作日志（JSONL）。"""
        path = self.actions_path(sim_id)
        if not os.path.exists(path):
            return []
        actions = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    actions.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return actions[-limit:]

    def _read_actions_since(self, path: str, offset: int) -> tuple[list[dict], int]:
        """从上次字节偏移增量读取新动作，返回 (新动作列表, 新字节偏移)。

        仅处理以换行结尾的完整行，避免读到子进程正在写入的半行（跨进程并发安全）。
        相比每轮全量重读 JSONL，大幅降低大模拟下的 IO/CPU 开销。
        """
        if not os.path.exists(path):
            return [], offset
        with open(path, "rb") as f:
            f.seek(offset)
            data = f.read()
        if not data:
            return [], offset
        last_nl = data.rfind(b"\n")
        if last_nl == -1:
            return [], offset  # 尚无完整行
        complete = data[: last_nl + 1]
        new_offset = offset + len(complete)
        actions: list[dict] = []
        for raw in complete.split(b"\n"):
            raw = raw.strip()
            if not raw:
                continue
            try:
                actions.append(json.loads(raw.decode("utf-8")))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
        return actions, new_offset

    @staticmethod
    def _empty_stats() -> dict:
        """增量统计的初始结构。"""
        return {"offset": 0, "action_count": 0, "current_round": 0,
                "per_platform": {}, "recent": []}

    def _reset_stats(self, sim_id: str) -> None:
        """重置某模拟的增量统计（重新开始模拟时调用）。"""
        with self._stats_lock:
            self._stats.pop(sim_id, None)

    def _accumulate_stats(self, sim_id: str) -> dict:
        """增量累积某模拟的动作统计，返回快照（轮次 / 动作数 / 分平台 / 最近动作）。

        通过字节偏移只读取新追加的完整行并更新计数，相比每次全量重读 actions.jsonl，
        大幅降低大模拟下高频轮询的 IO/CPU 开销。检测到日志被截断（重新开始模拟会
        清空 actions.jsonl）时自动重置。
        """
        path = self.actions_path(sim_id)
        with self._stats_lock:
            st = self._stats.get(sim_id) or self._empty_stats()
            self._stats[sim_id] = st
            # 文件被截断（重新开始模拟）时字节偏移失效，重置统计
            try:
                size = os.path.getsize(path) if os.path.exists(path) else 0
            except OSError:
                size = 0
            if size < st["offset"]:
                st = self._empty_stats()
                self._stats[sim_id] = st
            new, st["offset"] = self._read_actions_since(path, st["offset"])
            for a in new:
                st["action_count"] += 1
                r = a.get("round")
                if isinstance(r, int) and r + 1 > st["current_round"]:
                    st["current_round"] = r + 1
                p = a.get("platform") or "unknown"
                slot = st["per_platform"].setdefault(
                    p, {"actions": 0, "round": 0})
                slot["actions"] += 1
                if isinstance(r, int) and r + 1 > slot["round"]:
                    slot["round"] = r + 1
                st["recent"].append(a)
            if len(st["recent"]) > 40:
                st["recent"] = st["recent"][-40:]
            # 返回快照（复制可变字段，避免调用方改到缓存）
            return {
                "action_count": st["action_count"],
                "current_round": st["current_round"],
                "per_platform": {p: dict(v) for p, v in st["per_platform"].items()},
                "recent": list(st["recent"]),
            }

    def append_action(self, sim_id: str, **action) -> None:
        """直接追加一条动作到日志（用于未运行时记录上帝视角注入等）。"""
        action.setdefault("ts", time.time())
        path = self.actions_path(sim_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(action, ensure_ascii=False) + "\n")

    def is_running(self, sim_id: str) -> bool:
        """该模拟的子进程是否仍在运行。"""
        with self._proc_lock:
            proc = self._procs.get(sim_id)
        return bool(proc and proc.poll() is None)

    def is_env_alive(self, sim_id: str) -> bool:
        """模拟环境是否存活（子进程运行中 且 已进入等待命令模式），可接受实时采访。

        ：模拟回合完成后环境常驻，此时 env_status.json 为 alive。
        """
        if not self.is_running(sim_id):
            return False
        status = simulation_ipc.read_env_status(sim_id)
        return status.get("status") == "alive"

    def close_env(self, sim_id: str, timeout: float = 30.0) -> dict:
        """优雅关闭模拟环境（向子进程发送 close 信号，等待其退出等待循环）。

        与 stop 不同：stop 直接终止进程；close_env 让子进程优雅关闭 OASIS 环境后退出。
        """
        if self.is_running(sim_id):
            try:
                simulation_ipc.write_close_env(sim_id)
            except Exception as e:  # noqa: BLE001
                logger.warning("写入关闭信号失败：%s", e)
            # 等待子进程优雅退出（轮询）；超时则强制终止
            deadline = time.time() + timeout
            with self._proc_lock:
                proc = self._procs.get(sim_id)
            while proc and proc.poll() is None and time.time() < deadline:
                time.sleep(0.5)
            if proc and proc.poll() is None:
                logger.info("关闭环境超时，强制终止：%s", sim_id)
                simulation_runner.terminate_process(proc)
            with self._proc_lock:
                self._procs.pop(sim_id, None)
        return self.update(sim_id, status="completed") or {"id": sim_id, "status": "completed"}

    def get_config(self, sim_id: str) -> dict:
        """读取模拟配置（config.json）。"""
        path = self.config_path(sim_id)
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            return {}

    def read_profiles(self, sim_id: str) -> list[dict]:
        """读取已生成的 Agent 人设（profiles_reddit.json）。"""
        path = os.path.join(self.work_dir(sim_id), "profiles_reddit.json")
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:  # noqa: BLE001
            return []

    def list_agents(self, sim_id: str) -> list[dict]:
        """返回可对话的 Agent 列表（优先取人设，回退到动作日志中出现过的 Agent）。"""
        profiles = self.read_profiles(sim_id)
        if profiles:
            agents = []
            for i, p in enumerate(profiles):
                agents.append(
                    {
                        "id": p.get("entity_uuid") or p.get("name") or str(i),
                        "name": p.get("name") or f"Agent {i}",
                        "bio": p.get("bio", ""),
                        "persona": p.get("persona", ""),
                        "occupation": p.get("occupation", ""),
                        "mbti": p.get("mbti", ""),
                        "interests": p.get("interests", []) or [],
                    }
                )
            return agents
        # 回退：从动作日志聚合出现过的 Agent
        seen: dict[str, dict] = {}
        for a in self.read_actions(sim_id, limit=2000):
            aid = a.get("agent_id")
            if aid and aid not in seen and aid != "seed":
                seen[aid] = {"id": aid, "name": a.get("agent_name") or aid}
        return list(seen.values())

    def status(self, sim_id: str, detail: bool = True) -> dict | None:
        """计算并返回模拟状态（结合进程存活情况与动作日志）。

        :param detail: 是否附带重字段 recent_actions（最近动作）。高频轮询可传 False
            以获取轻量版载荷（ 的 to_dict / to_detail_dict 双序列化）。
        """
        sim = self.get(sim_id)
        if not sim:
            return None

        with self._proc_lock:
            proc = self._procs.get(sim_id)
        # 增量累积统计（避免每次全量重读 actions.jsonl）
        snap = self._accumulate_stats(sim_id)
        current_round = snap["current_round"]

        status = sim.get("status", "created")
        if status == "running" and proc is not None and proc.poll() is not None:
            # 子进程已结束：仅在状态确实变化时才持久化，避免并发轮询重复写入
            new_status = "completed" if proc.returncode == 0 else "failed"
            if new_status != sim.get("status"):
                self.update(sim_id, status=new_status)
            status = new_status

        # 分平台统计：各自轮次、动作数、模拟时长与完成态（双平台并行时分别展示）
        minutes_per_round = int(sim.get("minutes_per_round", 30) or 30)
        # 单子进程驱动双平台，故各平台完成态以整体终止状态近似
        terminal = status in TERMINAL
        per_platform: dict[str, dict] = {}
        for p, slot in snap["per_platform"].items():
            per_platform[p] = {
                "actions": slot["actions"],
                "round": slot["round"],
                "completed": terminal,
                "simulated_minutes": slot["round"] * minutes_per_round,
            }

        result = {
            "id": sim_id,
            "status": status,
            "round": current_round,
            "max_rounds": sim.get("max_rounds", config.OASIS_DEFAULT_MAX_ROUNDS),
            "action_count": snap["action_count"],
            "per_platform": per_platform,
            "graph_id": sim.get("graph_id"),
            "requirement": sim.get("requirement", ""),
            "env_alive": self.is_env_alive(sim_id),
        }
        # 双序列化：仅详情态附带最近动作（重字段），轻量态省略以降低高频轮询负载
        if detail:
            result["recent_actions"] = snap["recent"][-20:][::-1]  # 最近 20 条，最新在前
        return result

    def stop(self, sim_id: str) -> dict | None:
        """优雅停止模拟。"""
        with self._proc_lock:
            proc = self._procs.get(sim_id)
        if proc:
            simulation_runner.terminate_process(proc)
            with self._proc_lock:
                self._procs.pop(sim_id, None)
        return self.update(sim_id, status="stopped")

    def cleanup_all(self) -> None:
        """应用退出时终止所有运行中的子进程。"""
        with self._proc_lock:
            procs = list(self._procs.items())
            self._procs.clear()
        for sim_id, proc in procs:
            try:
                simulation_runner.terminate_process(proc)
            except Exception:  # noqa: BLE001
                pass
        # 子进程已终止（文件句柄已释放），清扫其生成的 OASIS 运行期日志（跑完即删的兜底）
        self._sweep_run_logs()
        # 注意：此方法可能在解释器退出阶段（atexit）被调用，届时 stdout 可能已关闭，
        # 因此此处不做日志输出，避免 logging 触发 I/O 错误噪声。

    # OASIS 库运行期日志前缀（子进程于 backend/log 下按时间生成，跑完清理）
    _RUN_LOG_PREFIXES = (
        "oasis-", "oasis.env-", "social.agent-", "social.twitter-",
        "social.reddit-", "table-",
    )

    def _sweep_run_logs(self) -> None:
        """删除 OASIS 子进程生成的运行期日志（backend/log 下的 oasis-*/social.*/table-*）。

        作为子进程自清理的兜底：子进程被强制杀死未及清理时，由主进程统一清扫。
        不触碰后端自身的 simulmirror.log。
        """
        log_dir = os.path.join(config.BASE_DIR, "log")
        try:
            for name in os.listdir(log_dir):
                if name.startswith(self._RUN_LOG_PREFIXES):
                    try:
                        os.remove(os.path.join(log_dir, name))
                    except OSError:
                        pass
        except OSError:
            pass


# 全局单例
simulation_manager = SimulationManager()
