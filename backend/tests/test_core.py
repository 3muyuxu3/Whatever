"""SimulMirror 后端核心单元测试。"""

from app import create_app
from app.models import TaskStatus, project_store, task_store
from app.services.text_processor import chunk_text
from app.utils.locale import t

# 来自 scripts/ 的人设校验（由 conftest 将 scripts 加入 sys.path）
from test_profile_format import validate_profile


# ---------- 纯逻辑 ----------

def test_chunk_text_short():
    assert chunk_text("hello") == ["hello"]
    assert chunk_text("") == []


def test_chunk_text_overlap():
    text = "a" * 1200
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert len(chunks) >= 3
    assert all(len(c) <= 500 for c in chunks)


def test_task_store():
    tk = task_store.create("demo")
    assert tk.status == TaskStatus.PENDING
    task_store.update(tk.id, progress=50, status=TaskStatus.RUNNING)
    assert task_store.get(tk.id).progress == 50


def test_project_store_crud():
    p = project_store.create(name="t", requirement="r")
    assert project_store.get(p.id).name == "t"
    project_store.update(p.id, status="graph_ready")
    assert project_store.get(p.id).status == "graph_ready"
    assert project_store.delete(p.id) is True
    assert project_store.get(p.id) is None


def test_locale_default_zh():
    # 无请求上下文时回退到中文
    assert t("not_found") == "资源不存在。"


def test_validate_profile():
    good = {
        "name": "A", "bio": "b", "persona": "p",
        "mbti": "INTJ", "occupation": "o", "interests": [],
    }
    assert validate_profile(good) == []
    assert "bio" in validate_profile({"name": "A"})


# ---------- Flask 端点 ----------

def _client():
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_health():
    r = _client().get("/api/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_project_list():
    r = _client().get("/api/graph/project/list")
    assert r.status_code == 200
    assert "projects" in r.get_json()


def test_graph_data_degrades_without_zep():
    # 未配置 Zep 时应优雅降级为空图谱，而非 500
    r = _client().get("/api/graph/data/nonexistent")
    assert r.status_code == 200
    assert r.get_json()["nodes"] == []


def test_simulation_status_not_found():
    r = _client().post("/api/simulation/status", json={"simulation_id": "nope"})
    assert r.status_code == 404
