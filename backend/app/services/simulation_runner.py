"""模拟运行器（子进程封装）。

通过 subprocess.Popen 启动独立 Python 进程运行 OASIS 模拟，
支持 Twitter 单平台、Reddit 单平台与双平台并行三种模式，并支持优雅终止。
"""

import os
import signal
import subprocess
import sys

from ..config import config
from ..utils.logger import get_logger

logger = get_logger("sim_runner")

# 运行模式 -> 脚本文件
SCRIPTS = {
    "twitter": "run_twitter_simulation.py",
    "reddit": "run_reddit_simulation.py",
    "parallel": "run_parallel_simulation.py",
}


def start_simulation_process(sim_id: str, mode: str, config_path: str, work_dir: str):
    """启动模拟子进程，返回 Popen 对象。"""
    script = SCRIPTS.get(mode, SCRIPTS["parallel"])
    script_path = os.path.join(config.BASE_DIR, "scripts", script)
    cmd = [
        sys.executable,
        script_path,
        "--sim-id", sim_id,
        "--config", config_path,
        "--work-dir", work_dir,
    ]
    logger.info("启动模拟子进程：%s", " ".join(cmd))

    # Windows 下创建新进程组，便于后续优雅终止
    creationflags = 0
    if os.name == "nt":
        # type: ignore[attr-defined]
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

    # 强制子进程以 UTF-8 打开文件：OASIS 的 generate_reddit_agent_graph 等以
    # open(path, "r") 读取人设文件（未指定编码），在中文 Windows（默认 GBK）下
    # 会因中文内容抛 UnicodeDecodeError，导致真实 OASIS 崩溃回退。开启 UTF-8 模式即可修复。
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}

    # OASIS 的 Twitter 推荐系统会从 HuggingFace 下载 twhin-bert 等模型；
    # 国内直连 huggingface.co 常超时（反复 10s 重试）导致模拟卡死。
    # 默认改用镜像 hf-mirror.com（可被用户环境变量覆盖），并缩短下载超时。
    env.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    env.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "15")

    return subprocess.Popen(cmd, cwd=config.BASE_DIR,
                            creationflags=creationflags, env=env)


def terminate_process(proc) -> None:
    """优雅终止子进程；超时则强制结束。"""
    if not proc or proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            proc.terminate()
        proc.wait(timeout=10)
    except Exception:  # noqa: BLE001
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass
