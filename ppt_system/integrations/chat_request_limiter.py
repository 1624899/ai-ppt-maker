from __future__ import annotations

from threading import BoundedSemaphore


# 对话模型请求统一限流，避免多个任务同时把模型连接占满。
CHAT_REQUEST_SEMAPHORE = BoundedSemaphore(value=2)
