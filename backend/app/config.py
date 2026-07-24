"""SimulMirror 后端配置管理。

统一从环境变量（.env）加载 LLM / Zep 等配置，并集中定义全局常量。
对应 AI.md 第七章「配置与环境变量」。
"""

import os
import secrets

from dotenv import load_dotenv

# 加载 .env（优先当前工作目录，其次项目根目录）
load_dotenv()


class Config:
    """全局配置对象。"""

    # ---- Flask ----
    # 默认关闭 debug（生产安全）；本地开发可显式设置环境变量 DEBUG=true
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    # SECRET_KEY：未显式配置时生成随机密钥，避免使用可预测的默认值签名 session/cookie
    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)
    # 跨域白名单：逗号分隔的来源列表；默认 * 便于本地开发，生产应显式收紧为具体域名
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
    # 文件上传大小限制：50MB
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    # 允许上传的文件扩展名（与 file_parser 支持的格式一致）
    ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown"}
    # 服务监听地址与端口（后端 API 默认 5001）
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "5001"))

    # ---- 文本分块 ----
    DEFAULT_CHUNK_SIZE = 500
    DEFAULT_CHUNK_OVERLAP = 50

    # ---- 模拟 ----
    OASIS_DEFAULT_MAX_ROUNDS = 10
    # OASIS 各平台可用动作（与 scripts/action_logger 保持一致）
    OASIS_TWITTER_ACTIONS = [
        "CREATE_POST", "LIKE_POST", "REPOST", "FOLLOW", "DO_NOTHING", "QUOTE_POST",
    ]
    OASIS_REDDIT_ACTIONS = [
        "LIKE_POST", "DISLIKE_POST", "CREATE_POST", "CREATE_COMMENT", "LIKE_COMMENT",
        "DISLIKE_COMMENT", "SEARCH_POSTS", "SEARCH_USER", "TREND", "REFRESH",
        "DO_NOTHING", "FOLLOW", "MUTE",
    ]
    # 模拟运行期间图谱记忆增量写回的轮询间隔（秒）
    MEMORY_UPDATE_INTERVAL = float(os.getenv("MEMORY_UPDATE_INTERVAL", "12"))

    # ---- 图谱构建 / Zep 限流（原 graph_builder 内散落的魔法数字集中于此） ----
    # 分批写入 Zep 的批大小
    GRAPH_BATCH_SIZE = int(os.getenv("GRAPH_BATCH_SIZE", "3"))
    # 等待 episode 处理完成的最长秒数与轮询间隔
    EPISODE_WAIT_TIMEOUT = int(os.getenv("EPISODE_WAIT_TIMEOUT", "240"))
    EPISODE_POLL_INTERVAL = int(os.getenv("EPISODE_POLL_INTERVAL", "8"))
    # 相邻 Zep 请求的最小间隔（秒）；FREE 计划限流严，取较大值
    ZEP_MIN_INTERVAL = float(os.getenv("ZEP_MIN_INTERVAL", "3.0"))
    # 图谱读取短时缓存 TTL（秒）与最大缓存条目数（防内存无限增长）
    GRAPH_CACHE_TTL = float(os.getenv("GRAPH_CACHE_TTL", "15.0"))
    GRAPH_CACHE_MAX = int(os.getenv("GRAPH_CACHE_MAX", "64"))

    # ---- 报告 Agent ----
    # 单次报告的图谱检索工具调用上限（控制 Zep 请求量，避免 FREE 计划 429）
    REPORT_AGENT_MAX_TOOL_CALLS = 3
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = 1
    # 报告章节生成温度
    REPORT_AGENT_TEMPERATURE = float(
        os.getenv("REPORT_AGENT_TEMPERATURE", "0.5"))

    # ---- 目录 ----
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
    DATA_DIR = os.path.join(BASE_DIR, "data")

    # ---- LLM（主模型，OpenAI 兼容格式） ----
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL = os.getenv(
        "LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "qwen-plus")

    # ---- LLM（加速模型，可选） ----
    LLM_BOOST_API_KEY = os.getenv("LLM_BOOST_API_KEY")
    LLM_BOOST_BASE_URL = os.getenv("LLM_BOOST_BASE_URL")
    LLM_BOOST_MODEL_NAME = os.getenv("LLM_BOOST_MODEL_NAME")

    # ---- Zep Cloud 记忆图谱 ----
    ZEP_API_KEY = os.getenv("ZEP_API_KEY", "")

    @classmethod
    def ensure_dirs(cls):
        """确保上传与数据目录存在。"""
        os.makedirs(cls.UPLOAD_DIR, exist_ok=True)
        os.makedirs(cls.DATA_DIR, exist_ok=True)

    @staticmethod
    def _is_set(value) -> bool:
        """判断配置值是否有效（非空且非 .env.example 中的占位符）。"""
        if not value:
            return False
        v = str(value).strip().lower()
        if not v:
            return False
        # 过滤常见占位符，如 your_api_key_here / your_zep_api_key_here / your_base_url_here
        return not (v.startswith("your_") or v.endswith("_here"))

    @classmethod
    def has_llm(cls) -> bool:
        """是否已配置主 LLM。"""
        return cls._is_set(cls.LLM_API_KEY)

    @classmethod
    def has_boost_llm(cls) -> bool:
        """是否已配置加速 LLM（三项齐全才算启用）。"""
        return (
            cls._is_set(cls.LLM_BOOST_API_KEY)
            and cls._is_set(cls.LLM_BOOST_BASE_URL)
            and cls._is_set(cls.LLM_BOOST_MODEL_NAME)
        )

    @classmethod
    def has_zep(cls) -> bool:
        """是否已配置 Zep Cloud。"""
        return cls._is_set(cls.ZEP_API_KEY)

    @classmethod
    def validate(cls) -> list[str]:
        """启动时校验关键配置，返回警告列表。

        注意：本项目支持 LLM/Zep 缺失时的优雅降级，故这里仅返回「警告」而非致命错误，
        由启动入口决定是否打印提示，不强制退出。
        """
        warnings: list[str] = []
        if not cls.has_llm():
            warnings.append(
                "未配置 LLM_API_KEY：将以降级模式运行（模拟走内置动作循环，报告为兜底大纲）。"
            )
        if not cls.has_zep():
            warnings.append(
                "未配置 ZEP_API_KEY：知识图谱与记忆检索功能不可用，将自动降级。"
            )
        # CORS 通配符在生产（非 DEBUG）下有安全风险，提示收紧为具体域名白名单
        if not cls.DEBUG and str(cls.CORS_ORIGINS).strip() == "*":
            warnings.append(
                "CORS_ORIGINS 为通配符 '*'：生产环境建议通过环境变量收紧为具体前端域名。"
            )
        return warnings


# 全局单例
config = Config()
