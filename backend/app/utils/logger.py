"""结构化日志工具。

统一日志格式与级别，供后端各模块使用。
- 控制台：简洁格式（始终启用）；
- 文件：默认关闭；仅当环境变量 SIMULMIRROR_FILE_LOG=1 时才写入 backend/log/simulmirror.log
  （带轮转 10MB × 5 备份，含模块/行号），避免默认在项目目录堆积日志文件。
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

_configured = False

# 日志目录：backend/log（与 OASIS 子进程日志同目录）
_LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))),
    "log",
)


def _file_log_enabled() -> bool:
    """是否将日志写入文件（默认关闭，仅输出到控制台）。

    需要落盘排障时，设置环境变量 SIMULMIRROR_FILE_LOG=1（或 true/yes/on）开启。
    """
    return os.getenv("SIMULMIRROR_FILE_LOG", "").strip().lower() in (
        "1", "true", "yes", "on")


def _configure() -> None:
    """初始化根日志记录器（幂等）。"""
    global _configured
    if _configured:
        return
    root = logging.getLogger("simulmirror")
    root.setLevel(logging.INFO)
    root.handlers.clear()

    # 控制台处理器（简洁格式）
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(
        logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root.addHandler(console)

    # 文件处理器（带轮转）：默认关闭，仅当 SIMULMIRROR_FILE_LOG 开启时写入，避免日志文件堆积
    if _file_log_enabled():
        try:
            os.makedirs(_LOG_DIR, exist_ok=True)
            file_handler = RotatingFileHandler(
                os.path.join(_LOG_DIR, "simulmirror.log"),
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setFormatter(
                logging.Formatter(
                    "[%(asctime)s] %(levelname)s [%(name)s:%(lineno)d] %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            root.addHandler(file_handler)
        except Exception:  # noqa: BLE001
            # 文件不可写（如只读环境）时仅保留控制台日志，不阻断启动
            pass

    root.propagate = False
    _configured = True


def get_logger(name: str = "app") -> logging.Logger:
    """获取命名子日志记录器。"""
    _configure()
    return logging.getLogger(f"simulmirror.{name}")
