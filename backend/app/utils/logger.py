"""结构化日志工具。

统一日志格式与级别，供后端各模块使用。
"""

import logging
import sys

_configured = False


def _configure() -> None:
    """初始化根日志记录器（幂等）。"""
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root = logging.getLogger("simulmirror")
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)
    root.propagate = False
    _configured = True


def get_logger(name: str = "app") -> logging.Logger:
    """获取命名子日志记录器。"""
    _configure()
    return logging.getLogger(f"simulmirror.{name}")
