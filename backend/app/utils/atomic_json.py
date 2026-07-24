"""原子化 JSON 读写工具。

统一封装「写临时文件 → os.replace 原子替换」的持久化模式，避免写入过程中
进程崩溃/断电导致 JSON 文件被截断为空或不完整（对齐数据安全要求）。

所有服务端的 JSON 持久化（projects / reports / simulations 等）均应经由此模块，
以保证同一路径的写入是原子的。
"""

import json
import os
import tempfile
from typing import Any

from .logger import get_logger

logger = get_logger("atomic_json")


def read_json(path: str, default: Any = None) -> Any:
    """安全读取 JSON 文件。

    文件不存在时返回 default；解析失败时记录 error 级别日志并将损坏文件
    备份为 ``<path>.corrupt``（保留现场以便排查），随后返回 default。

    :param path:    JSON 文件路径
    :param default: 读取失败时的兜底返回值
    """
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        logger.error("读取 JSON 失败（%s）：%s", path, e)
        # 保留损坏文件现场，避免静默丢失数据
        try:
            backup = path + ".corrupt"
            if os.path.exists(path):
                os.replace(path, backup)
                logger.error("已将损坏文件备份至：%s", backup)
        except Exception:  # noqa: BLE001
            pass
        return default


def atomic_write_json(path: str, data: Any, *, indent: int = 2) -> None:
    """原子化写入 JSON：先写入同目录临时文件，再 os.replace 覆盖目标。

    os.replace 在同一文件系统上是原子操作，可保证读者要么看到旧内容、
    要么看到完整的新内容，绝不会读到写了一半的中间状态。

    :param path:   目标文件路径
    :param data:   可被 json 序列化的对象
    :param indent: 缩进（默认 2）
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    # 在目标同目录创建临时文件，确保 os.replace 跨设备时仍是原子替换
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        # 失败时清理临时文件，避免残留
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:  # noqa: BLE001
            pass
        raise
