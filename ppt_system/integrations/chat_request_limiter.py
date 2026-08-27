from __future__ import annotations

from threading import BoundedSemaphore


# 对话模型请求统一限流，只覆盖正在发出的 HTTP 及其传输/状态码重试，
# 避免多个任务同时把模型连接占满。解析层退避不得占用槽位。
CHAT_REQUEST_SEMAPHORE = BoundedSemaphore(value=2)
