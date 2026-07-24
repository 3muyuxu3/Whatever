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
                    logger.warning("第 %d 次调用失败，%.1fs 后重试：%s",
                                   attempt, delay, e)
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
                    logger.warning("异步第 %d 次失败，%.1fs 后重试：%s",
                                   attempt, delay, e)
                    await asyncio.sleep(delay)

        return wrapper

    return decorator


class RetryableAPIClient:
    """可重试的 API 调用封装。

    适用于需要对「单次调用」或「批量调用中的每一项」独立重试的场景，
    并可选择在单项失败后继续处理其余项、收集失败清单。
    """

    def __init__(self, max_attempts: int = 3, base_delay: float = 1.0,
                 max_delay: float = 8.0):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay

    def call_with_retry(self, fn, *args, exceptions=(Exception,), **kwargs):
        """执行单次调用并在失败时指数退避重试。"""
        attempt = 0
        while True:
            try:
                return fn(*args, **kwargs)
            except exceptions as e:  # noqa: BLE001
                attempt += 1
                if attempt >= self.max_attempts:
                    logger.error("API 调用重试 %d 次后仍失败：%s", attempt, e)
                    raise
                delay = min(self.base_delay *
                            (2 ** (attempt - 1)), self.max_delay)
                logger.warning("API 调用第 %d 次失败，%.1fs 后重试：%s",
                               attempt, delay, e)
                time.sleep(delay)

    def call_batch_with_retry(self, items, process_fn, exceptions=(Exception,),
                              continue_on_failure: bool = True):
        """批量调用并对每项独立重试，返回 (成功结果列表, 失败项列表)。"""
        results = []
        failures = []
        for idx, item in enumerate(items):
            try:
                results.append(self.call_with_retry(
                    process_fn, item, exceptions=exceptions))
            except Exception as e:  # noqa: BLE001
                logger.error("批量第 %d 项处理失败：%s", idx + 1, e)
                failures.append({"index": idx, "item": item, "error": str(e)})
                if not continue_on_failure:
                    raise
        return results, failures
