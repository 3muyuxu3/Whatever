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
        return task

    def get(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def update(self, task_id: str, **kwargs) -> Optional[Task]:
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.touch(**kwargs)
            return task


# 全局单例
task_store = TaskStore()
