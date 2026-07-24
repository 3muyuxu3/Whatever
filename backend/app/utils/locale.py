"""后端国际化工具。

- 根据请求头 ``Accept-Language`` 或后台线程显式设置的 locale 返回本地化文案；
- 提供 ``get_language_instruction()`` 用于引导 LLM 以用户所选语言输出。

后台线程（报告生成、图谱构建、环境准备等）脱离了 Flask 请求上下文，
需在启动线程前捕获请求 locale，并在线程内调用 ``set_locale()`` 传递，
否则 ``t()`` 与 ``get_language_instruction()`` 会回退到默认语言。
"""

import threading

# 支持的语言（与前端 public/locales 保持一致）
SUPPORTED = ["zh", "en", "es", "fr", "pt", "ru", "de"]

# 后台线程的 locale 存储（无请求上下文时使用）
_thread_local = threading.local()

# 引导 LLM 输出语言的指令（ 的 languages.json.llmInstruction）
LANGUAGE_INSTRUCTIONS = {
    "zh": "请使用中文回答。",
    "en": "Please respond in English.",
    "es": "Por favor, responde en español.",
    "fr": "Veuillez répondre en français.",
    "pt": "Por favor, responda em português.",
    "ru": "Пожалуйста, отвечайте на русском языке.",
    "de": "Bitte antworten Sie auf Deutsch.",
}

# 后端消息文案表（提供中英文，其余语言回退到英文再回退中文）
MESSAGES = {
    "llm_not_configured": {
        "zh": "未配置 LLM API Key，请在 .env 中设置 LLM_API_KEY。",
        "en": "LLM API key is not configured. Please set LLM_API_KEY in .env.",
    },
    "zep_not_configured": {
        "zh": "未配置 Zep API Key，请在 .env 中设置 ZEP_API_KEY。",
        "en": "Zep API key is not configured. Please set ZEP_API_KEY in .env.",
    },
    "feature_unavailable": {
        "zh": "该功能依赖未安装（zep-cloud / camel-oasis / camel-ai），请先安装完整依赖。",
        "en": "This feature requires optional dependencies (zep-cloud / camel-oasis / camel-ai).",
    },
    "not_found": {
        "zh": "资源不存在。",
        "en": "Resource not found.",
    },
    "bad_request": {
        "zh": "请求参数有误。",
        "en": "Invalid request parameters.",
    },
    "file_too_large": {
        "zh": "文件过大，超出上传大小限制。",
        "en": "File too large, exceeds the upload size limit.",
    },
    "internal_error": {
        "zh": "服务器内部错误。",
        "en": "Internal server error.",
    },
    "unsupported_file_type": {
        "zh": "不支持的文件类型，仅支持 PDF / TXT / Markdown。",
        "en": "Unsupported file type. Only PDF / TXT / Markdown are allowed.",
    },
}


def set_locale(locale: str) -> None:
    """为当前线程设置 locale。后台线程启动时应在最开始调用以继承请求语言。"""
    _thread_local.locale = locale if locale in SUPPORTED else "zh"


def get_locale() -> str:
    """解析当前语言：优先请求头，其次线程本地，最后回退到 zh。"""
    try:
        from flask import has_request_context, request

        if has_request_context():
            header = request.headers.get("Accept-Language") or ""
            code = header.split(",")[0].strip().lower().split("-")[0]
            if code in SUPPORTED:
                return code
    except Exception:  # noqa: BLE001
        pass
    return getattr(_thread_local, "locale", "zh")


def t(key: str, locale: str | None = None) -> str:
    """获取本地化文案。回退顺序：指定语言 → 英文 → 中文 → key 原文。"""
    locale = locale or get_locale()
    entry = MESSAGES.get(key, {})
    return entry.get(locale) or entry.get("en") or entry.get("zh") or key


def get_language_instruction(locale: str | None = None) -> str:
    """获取引导 LLM 输出语言的指令，供拼接到 system prompt。"""
    locale = locale or get_locale()
    return LANGUAGE_INSTRUCTIONS.get(locale) or LANGUAGE_INSTRUCTIONS["zh"]
