"""SimulMirror 后端配置管理。

统一从环境变量（.env）加载 LLM / Zep 等配置，并集中定义全局常量。
对应 AI.md 第七章「配置与环境变量」。
"""

import os

from dotenv import load_dotenv

# 加载 .env（优先当前工作目录，其次项目根目录）
load_dotenv()


class Config:
    """全局配置对象。"""

    # ---- Flask ----
    DEBUG = os.getenv("DEBUG", "true").lower() == "true"
    SECRET_KEY = os.getenv("SECRET_KEY", "simulmirror-secret")
    # 文件上传大小限制：50MB
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    # 服务监听地址与端口（后端 API 默认 5001）
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "5001"))

    # ---- 文本分块 ----
    DEFAULT_CHUNK_SIZE = 500
    DEFAULT_CHUNK_OVERLAP = 50

    # ---- 模拟 ----
    OASIS_DEFAULT_MAX_ROUNDS = 10

    # ---- 报告 Agent ----
    REPORT_AGENT_MAX_TOOL_CALLS = 5
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = 2

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

    @classmethod
    def has_llm(cls) -> bool:
        """是否已配置主 LLM。"""
        return bool(cls.LLM_API_KEY)

    @classmethod
    def has_boost_llm(cls) -> bool:
        """是否已配置加速 LLM（三项齐全才算启用）。"""
        return bool(
            cls.LLM_BOOST_API_KEY
            and cls.LLM_BOOST_BASE_URL
            and cls.LLM_BOOST_MODEL_NAME
        )

    @classmethod
    def has_zep(cls) -> bool:
        """是否已配置 Zep Cloud。"""
        return bool(cls.ZEP_API_KEY)


# 全局单例
config = Config()
