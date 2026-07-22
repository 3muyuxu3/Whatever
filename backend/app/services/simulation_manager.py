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
from ..utils.logger import get_logger
from . import simulation_runner

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
        self._load()

    # ---- 持久化 ----
    def _load(self):
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as f:
                    self._sims = json.load(f)
        except Exception:  # noqa: BLE001
            self._sims = {}

    def _save(self):
        config.ensure_dirs()
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._sims, f, ensure_ascii=False, indent=2)

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
    def start(self, sim_id: str, mode: str = "parallel", max_rounds: int | None = None) -> dict:
        """启动模拟子进程。"""
        sim = self.get(sim_id)
        if not sim:
            raise ValueError("模拟不存在")

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

        # 清空历史动作日志
        open(self.actions_path(sim_id), "w", encoding="utf-8").close()

        proc = simulation_runner.start_simulation_process(
            sim_id, mode, cfg_path, work_dir)
        self._procs[sim_id] = proc
        return self.update(sim_id, status="running", mode=mode,
                           max_rounds=max_rounds or config.OASIS_DEFAULT_MAX_ROUNDS)

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

    def append_action(self, sim_id: str, **action) -> None:
        """直接追加一条动作到日志（用于未运行时记录上帝视角注入等）。"""
        action.setdefault("ts", time.time())
        path = self.actions_path(sim_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(action, ensure_ascii=False) + "\n")

    def is_running(self, sim_id: str) -> bool:
        """该模拟的子进程是否仍在运行。"""
        proc = self._procs.get(sim_id)
        return bool(proc and proc.poll() is None)

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

    def status(self, sim_id: str) -> dict | None:
        """计算并返回模拟状态（结合进程存活情况与动作日志）。"""
        sim = self.get(sim_id)
        if not sim:
            return None

        proc = self._procs.get(sim_id)
        actions = self.read_actions(sim_id)
        rounds = {a.get("round")
                  for a in actions if a.get("round") is not None}
        current_round = (max(rounds) + 1) if rounds else 0

        status = sim.get("status", "created")
        if status == "running" and proc is not None and proc.poll() is not None:
            # 子进程已结束
            status = "completed" if proc.returncode == 0 else "failed"
            self.update(sim_id, status=status)

        return {
            "id": sim_id,
            "status": status,
            "round": current_round,
            "max_rounds": sim.get("max_rounds", config.OASIS_DEFAULT_MAX_ROUNDS),
            "action_count": len(actions),
            "graph_id": sim.get("graph_id"),
            "requirement": sim.get("requirement", ""),
        }

    def stop(self, sim_id: str) -> dict | None:
        """优雅停止模拟。"""
        proc = self._procs.get(sim_id)
        if proc:
            simulation_runner.terminate_process(proc)
            self._procs.pop(sim_id, None)
        return self.update(sim_id, status="stopped")

    def cleanup_all(self) -> None:
        """应用退出时终止所有运行中的子进程。"""
        for sim_id, proc in list(self._procs.items()):
            try:
                simulation_runner.terminate_process(proc)
            except Exception:  # noqa: BLE001
                pass
        self._procs.clear()
        # 注意：此方法可能在解释器退出阶段（atexit）被调用，届时 stdout 可能已关闭，
        # 因此此处不做日志输出，避免 logging 触发 I/O 错误噪声。


# 全局单例
simulation_manager = SimulationManager()
