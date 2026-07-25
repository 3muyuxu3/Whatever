# SimulMirror Backend

SimulMirror 的后端服务，基于 **Flask 3** 的 REST API，负责从种子文档到预测报告的完整五阶段流水线：本体生成 → Zep 知识图谱构建 → OASIS 模拟环境准备 → 群体模拟运行 → ReACT 报告生成与深度互动。

项目整体介绍、前端说明与完整 API 表格见根目录 [README.md](../README.md)。

---

## 目录

- [快速开始](#快速开始)
- [目录结构](#目录结构)
- [核心模块说明](#核心模块说明)
- [环境变量](#环境变量)
- [异步任务模型](#异步任务模型)
- [模拟子进程架构](#模拟子进程架构)
- [数据持久化](#数据持久化)
- [优雅降级](#优雅降级)
- [日志](#日志)
- [测试](#测试)

---

## 快速开始

### 前置条件

- Python **3.11 - 3.12**（`pyproject.toml` 限定 `>=3.11,<3.13`）
- [uv](https://docs.astral.sh/uv/) ≥ 0.4

### 安装与启动

```bash
# 安装依赖（在 backend/ 目录下）
uv sync

# 启动服务（默认 http://0.0.0.0:5001）
uv run python run.py

# 或使用已有虚拟环境（Windows）
.venv\Scripts\python run.py
```

启动时会执行配置校验：缺失 `LLM_API_KEY` / `ZEP_API_KEY` 仅打印警告而不阻断启动（见[优雅降级](#优雅降级)）。健康检查端点：`GET /api/health`。

> `run.py` 以 `threaded=True` 运行，保证流式接口进行中仍能处理其他并发请求；Windows 下会自动将 stdout/stderr 重设为 UTF-8，避免中文日志乱码。

---

## 目录结构

```
backend/
├── run.py                      # 启动入口（配置校验 + Flask 启动）
├── pyproject.toml              # uv 项目配置（AGPL-3.0）
├── uv.lock                     # 依赖锁定
├── app/
│   ├── __init__.py             # create_app 工厂：注册蓝图、CORS、退出清理
│   ├── config.py               # 全局配置（.env 加载、降级判定、启动校验）
│   ├── api/                    # Flask 蓝图（REST 端点层）
│   │   ├── graph.py            #   /api/graph      项目、本体、图谱构建
│   │   ├── simulation.py       #   /api/simulation 实体、模拟、采访
│   │   └── report.py           #   /api/report     报告生成与对话
│   ├── services/               # 业务服务层（核心逻辑）
│   ├── models/                 # Pydantic 模型 + 内存任务存储
│   │   ├── project.py          #   项目模型与持久化
│   │   └── task.py             #   异步任务状态跟踪（线程安全）
│   └── utils/                  # 通用工具（LLM 客户端、重试、日志等）
├── scripts/                    # 模拟执行脚本（独立子进程运行）
│   ├── run_simulation.py       #   统一模拟入口（Twitter/Reddit/双平台）
│   ├── oasis_runner.py         #   真实 OASIS 引擎运行器
│   ├── action_logger.py        #   JSONL 动作日志 + 降级模拟循环
│   └── test_profile_format.py  #   Profile 格式验证（调试用）
├── tests/                      # pytest 单元测试
├── uploads/                    # 用户上传的种子文档（按项目 ID 分目录）
└── data/                       # 运行时数据（JSON 元数据 + 模拟工作目录）
```

---

## 核心模块说明

### services/ 业务服务层

| 模块 | 职责 |
| --- | --- |
| `ontology_generator` | 分析文档内容与预测需求，LLM 生成本体定义（正好 10 个实体类型 + 关系类型） |
| `text_processor` | 文本分块（默认 chunk 500 / overlap 50） |
| `graph_builder` | 基于本体在 Zep Cloud 创建 Standalone Graph，分块分批写入并读取完整图谱；带限流控制与 15s 读取缓存 |
| `zep_entity_reader` | 从 Zep 图谱读取并过滤实体节点，附带关联边/关联节点信息 |
| `oasis_profile_generator` | 为每个实体生成 Agent 人设（Reddit JSON / Twitter CSV 双格式），复用已有实体上下文减少 Zep 请求 |
| `simulation_config_generator` | 分步 LLM 智能生成模拟配置（时间配置、平台参数、初始事件等） |
| `simulation_manager` | 模拟生命周期管理：创建/持久化记录、工作目录、启动/停止子进程、读取状态与动作日志、退出时清理 |
| `simulation_ipc` | 文件系统 IPC：模拟运行中实时采访 Agent 的请求/响应交换 |
| `simulation_runner` | 模拟运行编排 |
| `zep_graph_memory_updater` | 模拟结束后将 Agent 社交动态增量写回 Zep 图谱（可选阶段） |
| `zep_tools` | ReportAgent 检索工具集：优先 Zep 语义搜索（混合语义 + BM25 + 重排），不可用时降级本地关键词检索 |
| `report_agent` | ReACT 报告 Agent：规划章节 → 自主调用检索工具（InsightForge / PanoramaSearch / QuickSearch / InterviewAgents）→ 生成 Markdown 报告；含报告存储与对话 |

### utils/ 工具层

| 模块 | 职责 |
| --- | --- |
| `llm_client` | OpenAI 兼容格式 LLM 客户端，统一封装主模型与加速模型（boost），内置指数退避重试 |
| `retry` | 指数退避重试装饰器（同步 + 异步），用于所有外部 API 调用 |
| `file_parser` | PDF（PyMuPDF）/ TXT / MD 解析，兼容多种非 UTF-8 编码 |
| `atomic_json` | 原子化 JSON 读写（临时文件 + `os.replace`），防止写入中断导致数据损坏 |
| `zep_paging` | Zep 节点/边分页查询的通用聚合 |
| `locale` | 后端国际化：根据 `Accept-Language` 或后台线程 locale 返回本地化文案 |
| `logger` | 结构化日志，统一格式与级别 |

---

## 环境变量

配置从 `.env` 加载（优先当前工作目录，其次项目根目录），完整定义见 [app/config.py](app/config.py)。

### 基础配置

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LLM_API_KEY` | 空 | LLM API 密钥（OpenAI 兼容格式），**核心功能必填** |
| `LLM_BASE_URL` | 通义千问兼容端点 | LLM 服务地址 |
| `LLM_MODEL_NAME` | `qwen-plus` | 主模型名 |
| `LLM_BOOST_API_KEY` / `LLM_BOOST_BASE_URL` / `LLM_BOOST_MODEL_NAME` | 空 | 加速模型，**三项齐全才启用**，用于轻量任务提速 |
| `ZEP_API_KEY` | 空 | Zep Cloud 记忆图谱密钥，缺失时图谱功能自动降级 |
| `HOST` / `PORT` | `0.0.0.0` / `5001` | 服务监听地址与端口 |
| `DEBUG` | `false` | Flask debug 模式 |
| `SECRET_KEY` | 随机生成 | Flask session 签名密钥 |
| `CORS_ORIGINS` | `*` | 跨域白名单（逗号分隔），生产环境建议收紧为具体域名 |
| `SIMULMIRROR_FILE_LOG` | 关闭 | 设为 `1/true/yes/on` 时将日志落盘到 `backend/log/simulmirror.log` |

### 高级调优（一般无需修改）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MEMORY_UPDATE_INTERVAL` | `12` | 模拟运行期间图谱记忆增量写回的轮询间隔（秒） |
| `GRAPH_BATCH_SIZE` | `3` | 分批写入 Zep 的批大小 |
| `EPISODE_WAIT_TIMEOUT` / `EPISODE_POLL_INTERVAL` | `240` / `8` | 等待 Zep episode 处理完成的超时与轮询间隔（秒） |
| `ZEP_MIN_INTERVAL` | `3.0` | 相邻 Zep 请求的最小间隔（秒），FREE 计划限流保护 |
| `GRAPH_CACHE_TTL` / `GRAPH_CACHE_MAX` | `15.0` / `64` | 图谱读取短时缓存 TTL（秒）与最大条目数 |
| `REPORT_AGENT_TEMPERATURE` | `0.5` | 报告章节生成温度 |

其他约束：上传文件大小上限 50MB；允许的扩展名为 `.pdf` / `.txt` / `.md` / `.markdown`。

---

## 异步任务模型

本体生成、图谱构建、环境准备、报告生成均为**异步任务**：`POST` 发起后立即返回 `task_id`，前端通过对应的 `/status` 端点轮询进度。任务状态由 [app/models/task.py](app/models/task.py) 中的线程安全内存存储管理（pending → running → completed / failed），并携带进度百分比与阶段描述。

准备与报告生成均具备**幂等性**：重复触发不会重复消耗 LLM/Zep 配额，已完成的产物直接复用。

---

## 模拟子进程架构

模拟运行在**独立子进程**中执行（`scripts/run_simulation.py`），与 Flask 主进程解耦：

- **平台模式**：由 `--platform` 指定 Twitter 单平台、Reddit 单平台或双平台并行。
- **真实引擎**：`oasis_runner.py` 基于 CAMEL-AI 的 OASIS 引擎，读取环境准备阶段生成的 `profiles_twitter.csv` / `profiles_reddit.json` 构建 Agent 图谱并运行社交模拟。
- **动作日志**：`action_logger.py` 线程安全地将每一步动作写入 `actions.jsonl`（JSONL 追加写），主进程增量读取供前端实时展示；未配置 LLM 时它同时提供自包含的降级模拟循环。
- **进程间通信**：通过文件系统 IPC（`simulation_ipc`）交换采访请求/响应，实现「模拟运行中实时采访 Agent」。
- **生命周期**：`simulation_manager` 负责启动/停止子进程，应用退出时自动清理全部运行中的子进程，并在模拟结束后清理 OASIS 遗留日志。

---

## 数据持久化

全部采用「JSON 元数据 + 文件系统工作目录」的轻量方案，写入均经过 `atomic_json` 原子替换：

```
data/
├── projects.json               # 项目元数据（图谱阶段）
├── simulations.json            # 模拟元数据
├── reports.json                # 报告元数据
├── sims/<simulation_id>/       # 每个模拟的工作目录
│   ├── profiles_*.csv/json     #   Agent 人设
│   ├── sim_config.json         #   模拟配置
│   └── actions.jsonl           #   动作日志（JSONL）
└── reports/<report_id>/        # 报告产物（Markdown 等）
uploads/<project_id>/           # 用户上传的种子文档原件
```

---

## 优雅降级

后端在依赖缺失时保证端到端流程可运行，不会崩溃或阻断：

| 缺失项 | 降级行为 |
| --- | --- |
| `LLM_API_KEY` | 模拟走内置动作循环（`action_logger`），报告输出兜底大纲 |
| `ZEP_API_KEY` | 图谱构建/记忆检索跳过，报告检索降级为本地关键词检索 |
| `zep-cloud` / `camel-oasis` 包缺失 | 相关模块惰性导入失败时静默降级，仅记录一次提示 |
| Zep 429 限流 | 指数退避重试 + 最小请求间隔 + 读取缓存，多级缓解 |

---

## 日志

- 默认仅输出到控制台（结构化格式，统一由 `utils/logger` 管理）。
- 设置 `SIMULMIRROR_FILE_LOG=1` 后追加落盘到 `backend/log/simulmirror.log`，用于排障。
- CAMEL 的 `max_tokens` 相关噪声告警已被过滤。

---

## 测试

```bash
# 安装测试依赖并运行（pytest + pytest-asyncio，asyncio_mode=auto）
uv run --extra test pytest

# 运行单个测试文件
uv run --extra test pytest tests/test_core.py -v
```

测试目录为 `tests/`，包含核心流程单测（`test_core.py`）与优化点回归测试（`test_optimizations.py`）。

---

## 许可证

本项目基于 **AGPL-3.0** 许可证开源。
