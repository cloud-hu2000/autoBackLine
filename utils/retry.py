"""
重试机制模块
"""

import time
import functools
from typing import Callable, Any, Optional
from tenacity import (
    retry,
    stop_after_attempt,
    wait_fixed,
    retry_if_exception_type,
    before_sleep_log,
)
import logging

import config

logger = logging.getLogger(__name__)


def retry_on_failure(
    max_attempts: Optional[int] = None,
    wait_seconds: Optional[int] = None,
    exceptions: tuple = (Exception,)
) -> Callable:
    """
    重试装饰器

    Args:
        max_attempts: 最大重试次数，默认取配置
        wait_seconds: 重试间隔（秒），默认取配置
        exceptions: 需要重试的异常类型
    """
    if max_attempts is None:
        max_attempts = config.ANTI_BAN_CONFIG["max_retries"]
    if wait_seconds is None:
        wait_seconds = config.ANTI_BAN_CONFIG["retry_delay"]

    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_fixed(wait_seconds),
        retry=retry_if_exception_type(exceptions),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


class RetryHandler:
    """重试处理器"""

    def __init__(self, max_attempts: int = None, delay: int = None):
        self.max_attempts = max_attempts or config.ANTI_BAN_CONFIG["max_retries"]
        self.delay = delay or config.ANTI_BAN_CONFIG["retry_delay"]

    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """执行函数并在失败时重试"""
        last_exception = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < self.max_attempts:
                    logger.warning(
                        f"第 {attempt} 次尝试失败: {e}, "
                        f"{self.delay}秒后重试..."
                    )
                    time.sleep(self.delay)
                else:
                    logger.error(
                        f"所有 {self.max_attempts} 次尝试均失败: {e}"
                    )

        raise last_exception
