"""模拟进程间通信（文件系统 IPC）。

运行中的模拟子进程与后端主进程之间，通过文件系统交换：
- Interview（采访）请求与响应，实现「在模拟运行过程中实时采访 Agent」；
- Injection（上帝视角变量注入），实现「在模拟运行过程中动态注入新事件 / 变量」，
  由运行中的模拟循环逐轮消费并影响后续社会演化。
"""

import json
import os
import time
import uuid

from ..config import config


def ipc_dir(sim_id: str) -> str:
    """返回某次模拟的 IPC 目录。"""
    d = os.path.join(config.DATA_DIR, "sims", sim_id, "ipc")
    os.makedirs(d, exist_ok=True)
    return d


def injections_dir(sim_id: str) -> str:
    """返回某次模拟的「上帝视角注入」目录。"""
    d = os.path.join(config.DATA_DIR, "sims", sim_id, "injections")
    os.makedirs(d, exist_ok=True)
    return d


# ---- 主进程侧（上帝视角注入变量） ----

def write_injection(sim_id: str, content: str, kind: str = "event",
                    platform: str | None = None) -> str:
    """写入一条「上帝视角」注入（新事件 / 变量），返回注入 ID。

    运行中的模拟循环会在下一轮读取并消费该注入，将其作为新的种子帖子 /
    环境变量注入到社会演化中。
    """
    inj_id = uuid.uuid4().hex
    path = os.path.join(injections_dir(sim_id), f"inj_{inj_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "id": inj_id,
                "content": content,
                "kind": kind,
                "platform": platform,
                "ts": time.time(),
            },
            f,
            ensure_ascii=False,
        )
    return inj_id


# ---- 主进程侧（发起采访） ----

def write_interview_request(sim_id: str, agent_id: str, question: str) -> str:
    """写入采访请求，返回请求 ID。"""
    req_id = uuid.uuid4().hex
    path = os.path.join(ipc_dir(sim_id), f"req_{req_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {"id": req_id, "agent_id": agent_id,
                "question": question, "ts": time.time()},
            f,
            ensure_ascii=False,
        )
    return req_id


def read_interview_response(sim_id: str, req_id: str, timeout: float = 30.0):
    """轮询等待采访响应，超时返回 None。"""
    path = os.path.join(ipc_dir(sim_id), f"resp_{req_id}.json")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        time.sleep(0.5)
    return None


# ---- 子进程侧（响应采访） ----

def poll_interview_requests(sim_id: str) -> list[dict]:
    """子进程侧：读取所有待处理的采访请求。"""
    d = ipc_dir(sim_id)
    requests = []
    for name in os.listdir(d):
        if name.startswith("req_") and name.endswith(".json"):
            with open(os.path.join(d, name), "r", encoding="utf-8") as f:
                requests.append(json.load(f))
    return requests


def write_interview_response(sim_id: str, req_id: str, answer: str) -> None:
    """子进程侧：写入采访响应，并清理对应请求文件。"""
    d = ipc_dir(sim_id)
    with open(os.path.join(d, f"resp_{req_id}.json"), "w", encoding="utf-8") as f:
        json.dump({"id": req_id, "answer": answer,
                  "ts": time.time()}, f, ensure_ascii=False)
    req_file = os.path.join(d, f"req_{req_id}.json")
    if os.path.exists(req_file):
        os.remove(req_file)
