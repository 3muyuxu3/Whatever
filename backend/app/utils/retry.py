"""指数退避重试机制。

用于所有外部 API 调用（LLM、Zep 等）的容错，提供同步与异步两个装饰器。
"""

import asyncio
import functools
import time

from .logger import get_logger

logger = get_logger("retry")


def retry(max_attempts: int = 3, base_delay: float = 1.0, max_delay: float = 8.0,
          exceptions=(Exception,)):
    """同步指数退避重试装饰器。

    :param max_attempts: 最大尝试次数
    :param base_delay:   初始延迟（秒）
    :param max_delay:    延迟上限（秒）
    :param exceptions:   需要重试的异常类型
    """

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            attempt = 0
            while True:
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:  # noqa: BLE001
                    attempt += 1
                    if attempt >= max_attempts:
                        logger.error("重试 %d 次后仍失败：%s", attempt, e)
                        raise
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    logger.warning("第 %d 次调用失败，%.1fs 后重试：%s", attempt, delay, e)
                    time.sleep(delay)

        return wrapper

    return decorator


def async_retry(max_attempts: int = 3, base_delay: float = 1.0, max_delay: float = 8.0,
                exceptions=(Exception,)):
    """异步指数退避重试装饰器（用于 async 函数）。"""

    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            attempt = 0
            while True:
                try:
                    return await fn(*args, **kwargs)
                except exceptions as e:  # noqa: BLE001
                    attempt += 1
                    if attempt >= max_attempts:
                        logger.error("异步重试 %d 次后仍失败：%s", attempt, e)
                        raise
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    logger.warning("异步第 %d 次失败，%.1fs 后重试：%s", attempt, delay, e)
                    await asyncio.sleep(delay)

        return wrapper

    return decorator
