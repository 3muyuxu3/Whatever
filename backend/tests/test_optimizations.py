""" 对齐优化项的单元测试。

覆盖：原子 JSON 读写、线程安全 TaskRegistry、任务清理、加速模型回落、
LLM 输出清洗、采访前缀、时序事实分流、增量动作读取、状态双序列化、
报告 JSONL 事件日志、以及准备/报告的幂等端点。
"""

import json
import os
import shutil
import threading
import time

from app import create_app
from app.config import config
from app.models import TaskRegistry, TaskStatus, task_store
from app.services import zep_tools
from app.services.report_agent import ReportEventLogger, read_report_log, report_store
from app.services.simulation_manager import simulation_manager
from app.utils.atomic_json import atomic_write_json, read_json
from app.utils.llm_client import _strip_code_fence, _strip_think, get_llm_client


def _client():
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


# ---------- 原子 JSON ----------

def test_atomic_json_roundtrip(tmp_path):
    p = str(tmp_path / "d.json")
    atomic_write_json(p, {"a": 1, "中文": [1, 2]})
    assert read_json(p) == {"a": 1, "中文": [1, 2]}


def test_read_json_missing_returns_default(tmp_path):
    assert read_json(str(tmp_path / "nope.json"), default={}) == {}


def test_read_json_corrupt_backs_up(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert read_json(str(p), default={"x": 1}) == {"x": 1}
    # 损坏文件被备份，原文件已移走
    assert (tmp_path / "c.json.corrupt").exists()
    assert not p.exists()


# ---------- TaskRegistry ----------

def test_task_registry_basic():
    r = TaskRegistry()
    r["k"] = "v"
    assert r.get("k") == "v"
    assert "k" in r
    assert r.pop("k") == "v"
    assert r.get("k") is None
    assert "k" not in r


def test_task_registry_concurrent():
    r = TaskRegistry()

    def worker(base):
        for i in range(100):
            r[f"{base}-{i}"] = i

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 8*100 个键全部写入，无丢失
    assert sum(1 for b in range(8)
               for i in range(100) if f"{b}-{i}" in r) == 800


# ---------- TaskStore 旧任务清理 ----------

def test_task_store_cleanup_old():
    tk = task_store.create("cleanup_probe")
    task_store.update(tk.id, status=TaskStatus.COMPLETED)
    # 将更新时间置于 25 小时前（超过 24h 阈值）
    task_store.get(tk.id).updated_at = time.time() - 25 * 3600
    # create 内部会触发 _cleanup_locked
    task_store.create("cleanup_trigger")
    assert task_store.get(tk.id) is None


# ---------- 加速模型回落 ----------

def test_boost_fallback_without_config():
    c = get_llm_client(boost=True)
    if not config.has_boost_llm():
        # 未配置 LLM_BOOST_* 时，boost 请求回落主模型
        assert c.boost is False
        assert c.model == config.LLM_MODEL_NAME


# ---------- LLM 输出清洗 ----------

def test_strip_think():
    assert _strip_think("<think>reason</think>answer") == "answer"
    assert _strip_think("plain") == "plain"


def test_strip_code_fence():
    assert _strip_code_fence('```json\n{"a":1}\n```') == '{"a":1}'
    assert _strip_code_fence('{"a":1}') == '{"a":1}'


# ---------- 采访前缀 ----------

def test_interview_prefix_applied_and_idempotent():
    from oasis_runner import _with_interview_prefix

    once = _with_interview_prefix("你怎么看？")
    assert once.startswith("结合你的人设")
    assert _with_interview_prefix(once) == once  # 幂等
    assert _with_interview_prefix("") == ""


# ---------- 时序事实分流 ----------

def test_is_historical():
    assert zep_tools._is_historical({"expired_at": "2024-01-01"}) is True
    assert zep_tools._is_historical({"invalid_at": "2024-01-01"}) is True
    assert zep_tools._is_historical({}) is False


def test_panorama_splits_active_historical(monkeypatch):
    edges = [
        {"fact": "当前有效事实", "name": "R1", "source": "a", "target": "b"},
        {"fact": "过期事实", "name": "R2", "source": "a",
         "target": "b", "expired_at": "2024-01-01"},
    ]
    monkeypatch.setattr(zep_tools, "_load_graph", lambda gid: ([], edges))
    res = zep_tools.panorama_search("g", "事实")
    kinds = {it["type"] for it in res}
    assert "fact" in kinds and "historical_fact" in kinds
    hist = [it for it in res if it["type"] == "historical_fact"]
    assert hist and hist[0]["text"] == "过期事实"


# ---------- 增量动作读取 ----------

def test_read_actions_since_incremental(tmp_path):
    p = str(tmp_path / "actions.jsonl")
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps({"round": 0}) + "\n")
        f.write(json.dumps({"round": 1}) + "\n")
    acts, off = simulation_manager._read_actions_since(p, 0)
    assert len(acts) == 2 and off > 0
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps({"round": 2}) + "\n")
    acts2, off2 = simulation_manager._read_actions_since(p, off)
    assert len(acts2) == 1 and acts2[0]["round"] == 2 and off2 > off


def test_read_actions_since_ignores_partial_line(tmp_path):
    p = str(tmp_path / "actions.jsonl")
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps({"round": 0}) + "\n")
        f.write('{"round": 1')  # 半行（无换行），应被忽略
    acts, _off = simulation_manager._read_actions_since(p, 0)
    assert len(acts) == 1


# ---------- 报告 JSONL 事件日志 ----------

def test_report_event_logger(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    lg = ReportEventLogger("r1")
    lg.log("report_start", "pending", x=1)
    lg.log("report_complete", "completed", total_sections=2)
    ev = read_report_log("r1")
    assert len(ev) == 2
    assert ev[0]["action"] == "report_start"
    assert ev[-1]["details"]["total_sections"] == 2


# ---------- 状态双序列化 + 分平台轮次 ----------

def test_status_detail_and_per_platform():
    sim = simulation_manager.create(project_id="p_probe")
    sid = sim["id"]
    try:
        simulation_manager.append_action(
            sid, round=0, platform="twitter", action="CREATE_POST")
        simulation_manager.append_action(
            sid, round=1, platform="reddit", action="CREATE_POST")
        light = simulation_manager.status(sid, detail=False)
        assert "recent_actions" not in light
        full = simulation_manager.status(sid, detail=True)
        assert "recent_actions" in full
        assert full["per_platform"]["twitter"]["round"] == 1
        assert full["per_platform"]["reddit"]["round"] == 2
    finally:
        shutil.rmtree(simulation_manager.work_dir(sid), ignore_errors=True)
        simulation_manager._sims.pop(sid, None)
        simulation_manager._save()


# ---------- 幂等端点 ----------

def test_report_generate_idempotent():
    sid = "sim_idem_probe"
    rep = report_store.create(simulation_id=sid)
    report_store.update(rep["id"], status="completed", content="x")
    try:
        r = _client().post("/api/report/generate", json={"simulation_id": sid})
        data = r.get_json()
        assert data.get("already_generated") is True
        assert data.get("report_id") == rep["id"]
    finally:
        report_store.delete(rep["id"])


def test_prepare_idempotent():
    sim = simulation_manager.create(project_id="p_idem")
    sid = sim["id"]
    wd = simulation_manager.work_dir(sid)
    try:
        with open(os.path.join(wd, "profiles_reddit.json"), "w", encoding="utf-8") as f:
            json.dump([{"name": "A"}], f)
        with open(simulation_manager.config_path(sid), "w", encoding="utf-8") as f:
            json.dump({"time": {"max_rounds": 5}}, f)
        r = _client().post("/api/simulation/prepare",
                           json={"simulation_id": sid})
        assert r.get_json().get("already_prepared") is True
    finally:
        shutil.rmtree(wd, ignore_errors=True)
        simulation_manager._sims.pop(sid, None)
        simulation_manager._save()
