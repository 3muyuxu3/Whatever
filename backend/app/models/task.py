"""异步任务模型与内存存储。

用于本体生成、图谱构建、环境准备、报告生成等异步任务的状态跟踪。
"""

import threading
import time
import uuid
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """任务状态枚举。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Task(BaseModel):
    """异步任务模型。"""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    type: str = ""
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0  # 0-100
    message: str = ""
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    def touch(self, **kwargs) -> None:
        """更新字段并刷新更新时间。"""
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.updated_at = time.time()


class TaskStore:
    """线程安全的内存任务存储。"""

    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._lock = threading.Lock()

    def create(self, task_type: str) -> Task:
        task = Task(type=task_type, status=TaskStatus.PENDING)
        with self._lock:
            self._tasks[task.id] = task
            # 机会性清理旧任务，避免内存无限增长（ cleanup_old_tasks）
            self._cleanup_locked()
        return task

    def get(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def update(self, task_id: str, **kwargs) -> Optional[Task]:
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.touch(**kwargs)
            return task

    def _cleanup_locked(self, max_age_seconds: float = 86400) -> None:
        """清理超过 max_age 的已完成/失败任务（须在持锁状态下调用）。"""
        cutoff = time.time() - max_age_seconds
        stale = [
            tid for tid, task in self._tasks.items()
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
            and task.updated_at < cutoff
        ]
        for tid in stale:
            del self._tasks[tid]


class TaskRegistry:
    """线程安全的「业务键 -> 任务ID/值」映射。

    用于各蓝图记录 业务ID -> 异步任务ID 的映射，替代无锁的模块级 dict，
    消除 threaded=True 下后台线程写入与前端轮询读取的并发竞态。
    支持 dict 风格的赋值与读取，作为原模块级 dict 的无缝替换。
    """

    def __init__(self):
        self._data: dict = {}
        self._lock = threading.Lock()

    def __setitem__(self, key, value):
        with self._lock:
            self._data[key] = value

    def get(self, key, default=None):
        with self._lock:
            return self._data.get(key, default)

    def pop(self, key, default=None):
        with self._lock:
            return self._data.pop(key, default)

    def __contains__(self, key):
        with self._lock:
            return key in self._data


# 全局单例
task_store = TaskStore()
