"""国际化工具：根据请求头 Accept-Language 返回本地化文案。"""

# 支持的语言（与前端保持一致）
SUPPORTED = ["zh", "en", "es", "fr", "pt", "ru", "de"]

# 后端消息文案表（提供中英文，其余回退到中文）
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
}


def get_locale() -> str:
    """从当前请求解析语言代码；无请求上下文时回退到 zh。"""
    try:
        from flask import request

        header = request.headers.get("Accept-Language") or "zh"
        code = header.split(",")[0].strip().lower().split("-")[0]
        return code if code in SUPPORTED else "zh"
    except Exception:  # noqa: BLE001
        return "zh"


def t(key: str, locale: str | None = None) -> str:
    """获取本地化文案。"""
    locale = locale or get_locale()
    entry = MESSAGES.get(key, {})
    return entry.get(locale) or entry.get("zh") or key
