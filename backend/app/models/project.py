"""项目模型与 JSON 文件持久化存储。

一个「项目」对应用户上传的一份种子文档 + 预测需求，贯穿图谱构建到报告生成。
"""

import json
import os
import threading
import time
import uuid
from typing import Optional

from pydantic import BaseModel, Field

from ..config import config


class Project(BaseModel):
    """项目模型。"""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    name: str = ""
    requirement: str = ""  # 预测需求描述
    file_name: Optional[str] = None  # 上传的种子文件名
    # 状态：created -> ontology_ready -> building -> graph_ready -> ...
    status: str = "created"
    graph_id: Optional[str] = None  # Zep 图谱 ID
    ontology: Optional[dict] = None  # 本体定义 { entity_types, edge_types }
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


class ProjectStore:
    """线程安全、JSON 文件持久化的项目存储。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._path = os.path.join(config.DATA_DIR, "projects.json")
        self._projects: dict[str, Project] = {}
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._projects = {k: Project(**v) for k, v in data.items()}
        except Exception:  # noqa: BLE001
            self._projects = {}

    def _save(self) -> None:
        config.ensure_dirs()
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(
                {k: v.model_dump() for k, v in self._projects.items()},
                f,
                ensure_ascii=False,
                indent=2,
            )

    def create(self, **kwargs) -> Project:
        project = Project(**kwargs)
        with self._lock:
            self._projects[project.id] = project
            self._save()
        return project

    def get(self, project_id: str) -> Optional[Project]:
        return self._projects.get(project_id)

    def list(self) -> list[Project]:
        return sorted(
            self._projects.values(), key=lambda p: p.created_at, reverse=True
        )

    def update(self, project_id: str, **kwargs) -> Optional[Project]:
        with self._lock:
            project = self._projects.get(project_id)
            if not project:
                return None
            for key, value in kwargs.items():
                setattr(project, key, value)
            project.updated_at = time.time()
            self._save()
            return project

    def delete(self, project_id: str) -> bool:
        with self._lock:
            if project_id in self._projects:
                del self._projects[project_id]
                self._save()
                return True
            return False


# 全局单例
project_store = ProjectStore()
