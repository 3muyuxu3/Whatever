# SimulMirror

> **模拟镜像，推演未来** · *Simulate Reality, Mirror the Future*

SimulMirror 是一个新一代 AI 群体智能预测引擎。它从现实世界提取「种子信息」（突发新闻、政策草案、金融信号、小说故事等），自动构建高保真的平行数字世界；在其中，成千上万个具备独立人格、长期记忆与行为逻辑的智能体自由交互与社会演化。用户可透过「上帝视角」动态注入变量，精准推演未来走向，并获得一份详尽的预测报告与一个可深度交互的数字世界。

**命名寓意**：**SimulMirror** 由 Simul（Simulation + Simulacrum）与 Mirror（镜像）组合而成，寓意在数字空间中构建现实的拟像镜像，让未来的每一种可能性都在推演中清晰可见。

---

## 目录

- [核心能力](#核心能力)
- [端到端工作流程](#端到端工作流程)
- [技术栈](#技术栈)
- [工程结构](#工程结构)
- [快速开始](#快速开始)
- [环境变量](#环境变量)
- [API 文档](#api-文档)
- [前端路由](#前端路由)
- [国际化](#国际化)
- [优雅降级](#优雅降级)
- [测试](#测试)
- [Docker 部署](#docker-部署)
- [许可证](#许可证)

---

## 核心能力

SimulMirror 采用五阶段流水线，从一颗现实种子生长为可交互的数字世界：

1. **知识图谱构建**：上传 PDF / TXT / MD 种子文档（突发新闻、政策草案、金融信号等），LLM 分析文档内容与预测需求自动生成本体（正好 10 个实体类型 + 关系类型），随后文本分块、分批写入 **Zep Cloud** 构建高保真时序知识图谱，前端以 D3 力导向图实时可视化。
2. **环境搭建**：从图谱中读取并过滤实体，为每个实体生成具备人格、长期记忆与行为逻辑的 Agent 人设（Reddit JSON / Twitter CSV 两种格式），并由 LLM **全自动**分步生成模拟配置（模拟周期、时间粒度、活跃度曲线、初始事件等），全程无需人工干预。
3. **群体模拟**：通过独立子进程运行 **OASIS**（基于 CAMEL-AI）群体模拟，支持 **Twitter / Reddit 双平台并行**；每一步 Agent 动作（发帖、点赞、转发、评论、关注等）实时写入 JSONL 动作日志，前端增量拉取展示；运行期间还会将社交动态增量写回 Zep 图谱丰富时序记忆。
4. **报告生成**：ReACT（推理-行动）报告 Agent 先规划 2-5 个章节，再自主调用四类检索工具（**InsightForge** 深度洞察 / **PanoramaSearch** 全景检索 / **QuickSearch** 快速检索 / **InterviewAgents** 现场采访），交叉验证后生成详尽的 Markdown 预测报告，支持下载。
5. **深度互动**：报告生成后进入「上帝视角」互动阶段——与报告 Agent 连续多轮对话追问细节、采访模拟世界中的任意 Agent、对多个 Agent 批量发起问卷调查。

---

## 端到端工作流程

```
种子文档上传 ──► 本体生成(LLM) ──► Zep 图谱构建 ──► 实体读取与过滤
                                                        │
        ┌───────────────────────────────────────────────┘
        ▼
Agent 人设生成 ──► 模拟配置生成(LLM) ──► OASIS 子进程模拟(双平台)
                                              │
        ┌─────────────────────────────────────┘
        ▼
JSONL 动作日志 ──► ReACT 报告 Agent(4 类检索工具) ──► Markdown 报告
                                                        │
                                                        ▼
                                     深度互动（对话 / 采访 / 问卷）
```

- 图谱构建、环境准备、报告生成均为**异步任务**：发起后返回 `task_id`，前端轮询 `/status` 端点获取进度与阶段描述。
- 准备与报告生成具备**幂等性**：重复触发不会重复消耗 LLM / Zep 配额，已完成的产物直接复用。
- 模拟运行中可通过文件系统 IPC **实时采访** Agent，无需等待模拟结束。

---

## 技术栈

| 层 | 关键技术 |
| --- | --- |
| 前端 | React 18 · React Router 6 · react-i18next · D3 v7 · Axios · Vite 7 · Tailwind CSS 3 |
| 后端 | Python 3.11-3.12 · Flask 3 · flask-cors · OpenAI SDK · Zep Cloud · camel-oasis · camel-ai · PyMuPDF · Pydantic |
| 包管理 | 前端/根：**pnpm** · 后端：**uv** |
| 部署 | Docker · docker-compose |

---

## 工程结构

```
.
├── package.json            # 根 monorepo 编排脚本（pnpm）
├── .env.example            # 环境变量示例
├── Dockerfile              # 前后端一体化镜像
├── docker-compose.yml      # 一键部署
├── frontend/               # React 18 + Vite 前端
│   ├── public/
│   │   ├── home.mp4         # 首页 Hero 背景视频
│   │   └── locales/         # 7 种语言资源
│   └── src/
│       ├── api/            # Axios 实例 + 三大 API 模块
│       ├── components/     # GraphPanel(D3)、Step1-5、FadeIn、AnimatedHeading 等
│       ├── hooks/          # usePolling / useGraphData / useSimulationStatus
│       ├── i18n/           # react-i18next 配置
│       ├── router/         # createBrowserRouter 路由
│       ├── store/          # 上传状态 Context
│       └── views/          # Home / MainView / ...View 页面
└── backend/                # Flask REST API（详见 backend/README.md）
    ├── run.py              # 启动入口
    ├── pyproject.toml      # uv 项目配置（AGPL-3.0）
    ├── uv.lock             # 依赖锁定
    ├── app/
    │   ├── api/            # graph / simulation / report 蓝图
    │   ├── services/       # 本体、图谱、Profile、模拟、报告 Agent 等
    │   ├── models/         # Project / Task Pydantic 模型
    │   └── utils/          # LLM 客户端、文件解析、重试、日志、i18n
    ├── scripts/            # 模拟执行脚本（独立子进程）
    ├── tests/              # pytest 单元测试
    ├── uploads/            # 用户上传的种子文档（按项目分目录）
    └── data/               # 运行时数据（JSON 元数据 + 模拟工作目录）
```

> 后端模块职责、异步任务模型、子进程架构与数据持久化的详细说明见 [backend/README.md](backend/README.md)。

---

## 快速开始

### 前置条件

- Node.js ≥ 18、**pnpm** ≥ 10
- Python 3.11 - 3.12、**uv** ≥ 0.4

### 一键安装

```bash
# 安装根目录 + 前端依赖（pnpm）
pnpm run setup
# 安装后端依赖（uv）
pnpm run setup:backend
# 或一次性安装全部
pnpm run setup:all
```

### 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，至少填入 LLM_API_KEY；如需完整功能再填 ZEP_API_KEY
```

### 启动开发环境

```bash
# 同时启动前后端（前端 3001 / 后端 5001）
pnpm run dev

# 或分别启动
pnpm run frontend   # 前端 http://localhost:3001
pnpm run backend    # 后端 http://localhost:5001
```

> 说明：未配置 `ZEP_API_KEY` 或未安装完整 AI 依赖时，应用仍可正常启动与浏览；模拟阶段会以内置的降级模拟循环产出真实的动作日志，保证端到端流程可运行（详见[优雅降级](#优雅降级)）。

---

## 环境变量

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `LLM_API_KEY` | 是 | LLM API 密钥（OpenAI 兼容格式） |
| `LLM_BASE_URL` | 否 | LLM 服务地址，默认通义千问兼容端点 |
| `LLM_MODEL_NAME` | 否 | 模型名，默认 `qwen-plus` |
| `LLM_BOOST_API_KEY` / `LLM_BOOST_BASE_URL` / `LLM_BOOST_MODEL_NAME` | 否 | 加速模型，用于轻量任务提速（**三项齐全才启用**） |
| `ZEP_API_KEY` | 否 | Zep Cloud 记忆图谱密钥，缺失时图谱功能自动降级 |
| `HOST` / `PORT` | 否 | 后端监听地址与端口，默认 `0.0.0.0:5001` |
| `DEBUG` | 否 | Flask debug 模式，默认 `false` |
| `CORS_ORIGINS` | 否 | 跨域白名单（逗号分隔），默认 `*`，生产环境建议收紧 |
| `SIMULMIRROR_FILE_LOG` | 否 | 设为 `1` 时后端日志落盘到 `backend/log/simulmirror.log` |

> 更多高级调优参数（Zep 限流间隔、图谱缓存、报告温度等）见 [backend/README.md](backend/README.md#环境变量)。

---

## API 文档

### Graph 蓝图（`/api/graph`）

| 端点 | 方法 | 功能 |
| --- | --- | --- |
| `/project/list` | GET | 列出所有项目 |
| `/project/<id>` | GET/DELETE | 获取/删除项目 |
| `/project/<id>/reset` | POST | 重置项目状态 |
| `/ontology/generate` | POST | 上传文件，LLM 生成本体定义 |
| `/build` | POST | 异步构建 Zep 知识图谱 |
| `/build/status` | POST | 查询图谱构建进度 |
| `/data/<graph_id>` | GET | 获取完整图谱数据 |

### Simulation 蓝图（`/api/simulation`）

| 端点 | 方法 | 功能 |
| --- | --- | --- |
| `/entities/<graph_id>` | GET | 获取图谱实体（已过滤） |
| `/entities/<graph_id>/<uuid>` | GET | 获取单个实体详情 |
| `/create` | POST | 创建新模拟 |
| `/prepare` | POST | 异步准备模拟环境 |
| `/prepare/status` | POST | 查询准备进度 |
| `/start` | POST | 启动模拟运行 |
| `/status` | POST | 获取模拟运行状态 |
| `/actions` | POST | 获取动作历史 |
| `/interview` | POST | 采访单个 Agent |
| `/interview/batch` | POST | 批量采访 Agent |

### Report 蓝图（`/api/report`）

| 端点 | 方法 | 功能 |
| --- | --- | --- |
| `/generate` | POST | 异步生成模拟分析报告 |
| `/generate/status` | POST | 查询报告生成进度 |
| `/<report_id>` | GET/DELETE | 获取/删除报告 |
| `/by-simulation/<sim_id>` | GET | 按模拟 ID 获取报告 |
| `/list` | GET | 列出所有报告 |
| `/<id>/download` | GET | 下载 Markdown 报告 |
| `/chat` | POST | 与 Report Agent 对话 |

> 另有健康检查：`GET /api/health`。

---

## 前端路由

| 路径 | 页面 | 阶段 |
| --- | --- | --- |
| `/` | Home | 首页（Hero、上传、历史项目） |
| `/process/:projectId` | MainView | Step 1-2（图谱构建 + 环境搭建） |
| `/simulation/:simulationId` | SimulationView | Step 2（环境搭建详情） |
| `/simulation/:simulationId/start` | SimulationRunView | Step 3（模拟运行，支持 `?maxRounds`） |
| `/report/:reportId` | ReportView | Step 4（报告生成） |
| `/interaction/:reportId` | InteractionView | Step 5（深度互动） |

---

## 国际化

支持 7 种语言：中文、English、Español、Français、Português、Русский、Deutsch。
语言资源位于 `frontend/public/locales/<lng>/translation.json`，通过 **react-i18next + i18next-http-backend** 动态加载；语言切换持久化到 `localStorage`，并自动注入 `Accept-Language` 请求头。

---

## 优雅降级

后端在依赖缺失时保证端到端流程可运行，不会崩溃或阻断：

| 缺失项 | 降级行为 |
| --- | --- |
| `LLM_API_KEY` | 模拟走内置动作循环，报告输出兜底大纲 |
| `ZEP_API_KEY` | 图谱构建/记忆检索跳过，报告检索降级为本地关键词检索 |
| `zep-cloud` / `camel-oasis` 包缺失 | 相关模块惰性导入失败时静默降级，仅记录一次提示 |
| Zep 429 限流 | 指数退避重试 + 最小请求间隔 + 读取缓存，多级缓解 |

---

## 测试

```bash
cd backend
uv run --extra test pytest                    # 运行后端全部单元测试
uv run --extra test pytest tests/test_core.py -v   # 运行单个测试文件
```

测试基于 **pytest + pytest-asyncio**（`asyncio_mode=auto`），覆盖核心流程与优化点回归。

---

## Docker 部署

```bash
cp .env.example .env
docker compose up --build
# 前端 http://localhost:3001 · 后端 http://localhost:5001
```

镜像为前后端一体化构建，默认读取根目录 `.env`，并挂载 `./backend/uploads` 卷用于文件持久化。如需国内加速，可在 `Dockerfile` 中将 base 镜像替换为 `ghcr.nju.edu.cn` 等加速地址。

---

## 许可证

本项目基于 **AGPL-3.0** 许可证开源。
