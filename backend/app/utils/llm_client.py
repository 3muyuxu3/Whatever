"""LLM 客户端封装（OpenAI 兼容格式）。

统一封装主模型与加速模型的调用，内置指数退避重试。
任意兼容 OpenAI SDK 的 LLM API（如通义千问、DeepSeek 等）均可使用。
"""

import json
import re

from ..config import config
from .logger import get_logger
from .retry import retry

logger = get_logger("llm")


def _strip_think(text: str) -> str:
    """移除思考型模型（如 MiniMax / DeepSeek-R1）输出中的 <think>...</think> 段。"""
    return re.sub(r"<think>[\s\S]*?</think>", "", text or "").strip()


def _strip_code_fence(text: str) -> str:
    """移除 LLM 返回内容外层的 ```json ... ``` markdown 代码块围栏。"""
    s = (text or "").strip()
    s = re.sub(r"^```(?:json)?\s*\n?", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\n?```\s*$", "", s)
    return s.strip()


class LLMClient:
    """LLM 调用封装。

    :param boost: 是否使用加速模型（需配置 LLM_BOOST_* 且三项齐全）
    """

    def __init__(self, boost: bool = False):
        # 仅当加速模型完整配置时才启用
        self.boost = boost and config.has_boost_llm()
        # 缓存 OpenAI 客户端实例，复用 HTTP 连接池，避免高频调用时重复建连接
        self._cached_client = None

    @property
    def model(self) -> str:
        return config.LLM_BOOST_MODEL_NAME if self.boost else config.LLM_MODEL_NAME

    def _client(self):
        """惰性创建并缓存 OpenAI 客户端（避免模块级导入 & 重复建连接池）。"""
        if self._cached_client is not None:
            return self._cached_client
        from openai import OpenAI

        if self.boost:
            self._cached_client = OpenAI(
                api_key=config.LLM_BOOST_API_KEY,
                base_url=config.LLM_BOOST_BASE_URL,
            )
        else:
            self._cached_client = OpenAI(
                api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL)
        return self._cached_client

    @retry(max_attempts=3)
    def chat(self, messages, **kwargs) -> str:
        """发起对话补全，返回文本内容（自动清理 <think> 思考段）。"""
        if not config.has_llm():
            raise RuntimeError("LLM 未配置（缺少 LLM_API_KEY）")
        client = self._client()
        resp = client.chat.completions.create(
            model=self.model, messages=messages, **kwargs
        )
        return _strip_think(resp.choices[0].message.content or "")

    def chat_json(self, messages, **kwargs) -> dict:
        """发起对话补全并解析 JSON 输出。"""
        # 请求模型以 JSON 对象格式返回
        kwargs.setdefault("response_format", {"type": "json_object"})
        # 先去除可能的 markdown 代码块围栏，再解析
        content = _strip_code_fence(self.chat(messages, **kwargs))
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            # 容错：尝试截取第一个 { 到最后一个 }
            start, end = content.find("{"), content.rfind("}")
            if start != -1 and end != -1:
                return json.loads(content[start: end + 1])
            raise

    def chat_stream(self, messages, **kwargs):
        """流式对话补全：逐块 yield 文本增量（供 SSE 等实时输出）。

        不带重试（流式中途失败难以幂等重试）；调用方自行处理异常。
        """
        if not config.has_llm():
            raise RuntimeError("LLM 未配置（缺少 LLM_API_KEY）")
        client = self._client()
        resp = client.chat.completions.create(
            model=self.model, messages=messages, stream=True, **kwargs
        )
        for chunk in resp:
            try:
                delta = chunk.choices[0].delta.content
            except (AttributeError, IndexError, TypeError):
                delta = None
            if delta:
                yield delta


def get_llm_client(boost: bool = False) -> LLMClient:
    """获取 LLM 客户端实例。"""
    return LLMClient(boost=boost)
