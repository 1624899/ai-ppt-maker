from __future__ import annotations

from http.client import RemoteDisconnected

from requests.exceptions import ChunkedEncodingError, ConnectTimeout, ConnectionError, ProxyError, ReadTimeout


RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504, 524}


def is_retryable_status_code(status_code: int) -> bool:
    return status_code in RETRYABLE_STATUS_CODES


def transport_retry_budget(
    exc: BaseException,
    *,
    transport_retry_count: int,
    ambiguous_transport_retry_count: int,
) -> int:
    if is_connection_setup_error(exc):
        return max(0, int(transport_retry_count))
    return max(0, int(ambiguous_transport_retry_count))


def is_connection_setup_error(exc: BaseException) -> bool:
    chain = list(iter_exception_chain(exc))
    if any(isinstance(item, (ConnectTimeout, ProxyError)) for item in chain):
        return True

    message = build_exception_message(chain)
    markers = (
        "failed to establish a new connection",
        "temporary failure in name resolution",
        "name or service not known",
        "nodename nor servname provided",
        "connection refused",
        "proxyerror",
    )
    return any(marker in message for marker in markers)


def is_ambiguous_transport_error(exc: BaseException) -> bool:
    chain = list(iter_exception_chain(exc))
    if any(
        isinstance(
            item,
            (
                RemoteDisconnected,
                ConnectionResetError,
                BrokenPipeError,
                EOFError,
                ReadTimeout,
                ChunkedEncodingError,
            ),
        )
        for item in chain
    ):
        return True
    if any(isinstance(item, ConnectionError) for item in chain):
        return True

    message = build_exception_message(chain)
    markers = (
        "remote end closed connection without response",
        "connection aborted",
        "connection reset by peer",
        "unexpected eof",
        "server disconnected",
    )
    return any(marker in message for marker in markers)


def build_transport_error_message(exc: BaseException) -> str:
    if is_ambiguous_transport_error(exc):
        return f"图像接口请求异常：{exc}。该异常可能发生在服务端已接收请求之后；为避免重复扣费，系统已停止自动重试，可直接点击“继续”从当前进度恢复。"
    return f"图像接口请求异常：{exc}"


def iter_exception_chain(exc: BaseException):
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        yield current
        seen.add(id(current))
        current = current.__cause__ or current.__context__

    for item in getattr(exc, "args", ()):
        if isinstance(item, BaseException) and id(item) not in seen:
            yield from iter_exception_chain(item)


def build_exception_message(chain: list[BaseException]) -> str:
    return " ".join(str(item).lower() for item in chain if str(item))
