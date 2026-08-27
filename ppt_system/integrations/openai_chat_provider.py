from __future__ import annotations

import json
import re
import time
import base64
from pathlib import Path
from typing import Any

import requests
from ppt_system.integrations.chat_request_limiter import CHAT_REQUEST_SEMAPHORE

from ppt_system.integrations.api_url import normalize_api_base_url
from ppt_system.integrations.chat_response_parser import AmbiguousResponseError, extract_response_text
from ppt_system.integrations.chat_stream_parser import looks_like_sse_text, parse_response_sse
from ppt_system.integrations.http_retry_policy import (
    build_text_snippet,
    build_transport_error_message,
    build_transport_error_summary,
    is_retryable_status_code,
    transport_retry_budget,
)
from ppt_system.integrations.responses_payload import (
    build_json_response_payload,
    build_responses_image_input_item,
    build_responses_url,
)
from ppt_system.runtime.logging_utils import format_log_line, format_stage_tag


class _RequestAttemptCounter:
    """一次完整模型调用内跨多次 HTTP 请求共享的累计序号。

    JSON 解析重试、空响应补充重试都会重新进入请求循环，
    只有把序号放在这次调用的共享状态里，日志中的“第 N 次请求”
    才能连续递增而不是每次从 1 重新计算。
    """

    __slots__ = ("count",)

    def __init__(self) -> None:
        self.count = 0

    def next(self) -> int:
        self.count += 1
        return self.count


class OpenAIChatProvider:
    def __init__(self, config: dict[str, Any], profile: dict[str, Any]) -> None:
        self.profile = profile
        self.api_key = str(profile.get("api_key", "")).strip()
        self.api_base_url = normalize_api_base_url(
            str(profile.get("base_url", config.get("chat_api_base_url", "https://api.openai.com/v1")))
        )
        self.model = str(profile.get("model", config.get("chat_model", "gpt-5.5")))
        self.reasoning_effort = self._resolve_reasoning_effort(config, profile)
        self.timeout = int(config.get("request_timeout_seconds", 180))
        self.total_timeout = max(1, int(config.get("chat_total_timeout_seconds", 240)))
        self.retry_count = int(config.get("chat_retry_count", config.get("request_retry_count", 3)))
        self.transport_retry_count = int(
            config.get("chat_transport_retry_count", config.get("request_transport_retry_count", 1))
        )
        self.ambiguous_transport_retry_count = int(
            config.get("chat_ambiguous_transport_retry_count", config.get("request_ambiguous_retry_count", 0))
        )
        self.ambiguous_retry_count = int(config.get("chat_ambiguous_retry_count", 1))
        self.json_retry_count = int(config.get("chat_json_retry_count", 1))
        self.retry_initial_delay = float(config.get("request_retry_initial_delay_seconds", 5))

        if not self.api_key:
            raise RuntimeError("未在模型配置中填写对话模型 API Key。")

    @property
    def responses_url(self) -> str:
        return build_responses_url(self.api_base_url)

    def complete_json(
        self,
        messages: list[dict[str, Any]],
        *,
        purpose: str = "模型调用",
    ) -> dict[str, Any]:
        """请求对话模型并解析 JSON 结果。

        purpose 用于在日志中标注本次调用的业务阶段（如“内容规划”“单页文字脚本”），
        避免多条并行日志无法定位来自哪个阶段。
        """
        stage_tag = format_stage_tag(purpose)
        print(
            format_log_line(
                "chat",
                f"开始请求模型 `{self.model}`{stage_tag}，timeout={self.timeout}s",
            ),
            flush=True,
        )
        payload = build_json_response_payload(
            model=self.model,
            messages=messages,
            reasoning_effort=self.reasoning_effort,
            stream=True,
        )
        started_at = time.perf_counter()
        attempt = _RequestAttemptCounter()
        try:
            response = self._post_with_retry(payload, attempt, purpose=purpose)
            self._raise_for_error(response)
            body = _parse_response_json(response)
            result, response = self._parse_json_with_retry(
                body, payload, attempt, purpose=purpose, response=response
            )
        except Exception as exc:
            elapsed = time.perf_counter() - started_at
            print(
                format_log_line(
                    "chat",
                    f"模型请求失败{stage_tag}：{build_text_snippet(str(exc))}，"
                    f"共请求 {attempt.count} 次，耗时={elapsed:.1f}s",
                ),
                flush=True,
            )
            raise
        elapsed = time.perf_counter() - started_at
        print(
            format_log_line(
                "chat",
                f"模型响应完成{stage_tag}，status={response.status_code}，"
                f"共请求 {attempt.count} 次，耗时={elapsed:.1f}s",
            ),
            flush=True,
        )
        return result

    def build_image_message_item(self, image_path: Path) -> dict[str, Any]:
        return build_responses_image_input_item(file_to_data_url(image_path))

    def _post_with_retry(
        self,
        payload: dict[str, Any],
        attempt: _RequestAttemptCounter,
        *,
        purpose: str,
        reason: str = "",
    ) -> requests.Response:
        """发送 HTTP 请求并按策略重试。

        attempt 在一次完整的模型调用内跨所有重试层共享，
        保证 JSON 解析重试、空响应补充重试后序号仍然连续递增。
        reason 用于标注本次请求是由哪一层重试触发的。
        限流只覆盖本轮实际 HTTP 及其传输/状态码重试，
        解析层退避必须在锁外进行，避免空响应或 JSON 重试占满槽位。
        """
        response_attempt = 0
        transport_attempt = 0
        deadline = time.monotonic() + self.total_timeout
        stage_tag = format_stage_tag(purpose)
        with CHAT_REQUEST_SEMAPHORE:
            while True:
                request_attempt = attempt.next()
                reason_suffix = f"（{reason}）" if reason else ""
                print(
                    format_log_line(
                        "chat",
                        f"发送第 {request_attempt} 次请求{stage_tag}{reason_suffix} -> {self.responses_url}",
                    ),
                    flush=True,
                )
                request_started_at = time.perf_counter()
                try:
                    response = requests.post(
                        self.responses_url,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                        timeout=min(self.timeout, max(0.001, deadline - time.monotonic())),
                    )
                except requests.RequestException as exc:
                    elapsed = time.perf_counter() - request_started_at
                    error_summary = build_transport_error_summary(exc)
                    print(
                        format_log_line(
                            "chat",
                            f"第 {request_attempt} 次请求异常{stage_tag}：{error_summary}，耗时={elapsed:.1f}s",
                        ),
                        flush=True,
                    )
                    retry_budget = transport_retry_budget(
                        exc,
                        transport_retry_count=self.transport_retry_count,
                        ambiguous_transport_retry_count=self.ambiguous_transport_retry_count,
                    )
                    if transport_attempt >= retry_budget:
                        error_message = build_transport_error_message(exc, api_name="对话模型")
                        print(
                            format_log_line(
                                "chat",
                                f"请求异常已停止自动重试{stage_tag}：{build_text_snippet(error_message)}",
                            ),
                            flush=True,
                        )
                        raise RuntimeError(error_message) from exc
                    delay = self.retry_initial_delay * (2**transport_attempt)
                    transport_attempt += 1
                    print(
                        format_log_line(
                            "chat",
                            f"将在 {delay:.1f}s 后重试传输异常（{transport_attempt}/{retry_budget}）{stage_tag}",
                        ),
                        flush=True,
                    )
                    if time.monotonic() + delay >= deadline:
                        raise RuntimeError(f"对话模型请求超过总时限 {self.total_timeout} 秒，已停止重试") from exc
                    time.sleep(delay)
                    continue
                elapsed = time.perf_counter() - request_started_at
                print(
                    format_log_line(
                        "chat",
                        f"第 {request_attempt} 次请求返回 HTTP {response.status_code}{stage_tag}，耗时={elapsed:.1f}s",
                    ),
                    flush=True,
                )
                if not should_retry(response) or response_attempt >= self.retry_count:
                    return response

                retry_after = response.headers.get("Retry-After", "").strip()
                delay = float(retry_after) if retry_after.isdigit() else self.retry_initial_delay * (2**response_attempt)
                response_attempt += 1
                print(
                    format_log_line(
                        "chat",
                        f"命中可重试状态码 {response.status_code}，将在 {delay:.1f}s 后重试{stage_tag}",
                    ),
                    flush=True,
                )
                if time.monotonic() + delay >= deadline:
                    raise RuntimeError(f"对话模型请求超过总时限 {self.total_timeout} 秒，已停止重试")
                time.sleep(delay)

    def _extract_json_content_with_retry(
        self,
        body: dict[str, Any],
        payload: dict[str, Any],
        attempt: _RequestAttemptCounter,
        *,
        purpose: str,
        response: requests.Response,
    ) -> tuple[str, requests.Response]:
        attempt_in_retry = 0
        current_body = body
        current_response = response
        while True:
            try:
                content = _extract_response_content(current_body)
                print(format_log_line("chat", _build_response_diagnostic(current_body, content)), flush=True)
                return content, current_response
            except AmbiguousResponseError as exc:
                if _has_billable_usage(current_body):
                    message = _build_billable_ambiguous_response_message(current_body, exc)
                    print(format_log_line("chat", message), flush=True)
                    raise AmbiguousResponseError(message) from exc
                if attempt_in_retry >= self.ambiguous_retry_count:
                    raise
                attempt_in_retry += 1
                print(
                    format_log_line(
                        "chat",
                        "检测到歧义空响应，"
                        f"{build_text_snippet(str(exc))}，"
                        f"将执行第 {attempt_in_retry}/{self.ambiguous_retry_count} 次补充重试"
                        f"{format_stage_tag(purpose)}",
                    ),
                    flush=True,
                )
                time.sleep(self.retry_initial_delay * (2 ** (attempt_in_retry - 1)))
                current_response = self._post_with_retry(
                    payload,
                    attempt,
                    purpose=purpose,
                    reason=f"空响应补充重试 {attempt_in_retry}/{self.ambiguous_retry_count}",
                )
                self._raise_for_error(current_response)
                current_body = _parse_response_json(current_response)

    def _parse_json_with_retry(
        self,
        body: dict[str, Any],
        payload: dict[str, Any],
        attempt: _RequestAttemptCounter,
        *,
        purpose: str,
        response: requests.Response,
    ) -> tuple[dict[str, Any], requests.Response]:
        """解析模型 JSON；对返回异常且无法解析的响应按原参数重试。"""
        current_body = body
        current_payload = payload
        current_response = response
        for attempt_in_retry in range(max(0, self.json_retry_count) + 1):
            try:
                _raise_for_incomplete_response(current_body)
                content, current_response = self._extract_json_content_with_retry(
                    current_body,
                    current_payload,
                    attempt,
                    purpose=purpose,
                    response=current_response,
                )
                return parse_json_content(content), current_response
            except AmbiguousResponseError:
                raise
            except RuntimeError as exc:
                content = _try_extract_response_content(current_body)
                print(
                    format_log_line(
                        "chat",
                        "模型 JSON 解析失败诊断："
                        f"{_build_response_diagnostic(current_body, content)}，"
                        f"error={build_text_snippet(str(exc))}",
                    ),
                    flush=True,
                )
                if attempt_in_retry >= max(0, self.json_retry_count):
                    raise
                next_attempt = attempt_in_retry + 1
                print(
                    format_log_line(
                        "chat",
                        f"模型返回的 JSON 无法解析，将执行第 {next_attempt}/{self.json_retry_count} 次重试"
                        f"{format_stage_tag(purpose)}",
                    ),
                    flush=True,
                )
                time.sleep(self.retry_initial_delay * (2**attempt_in_retry))
                current_response = self._post_with_retry(
                    current_payload,
                    attempt,
                    purpose=purpose,
                    reason=f"JSON 解析重试 {next_attempt}/{self.json_retry_count}",
                )
                self._raise_for_error(current_response)
                current_body = _parse_response_json(current_response)
        raise AssertionError("JSON 解析重试流程异常结束")

    @staticmethod
    def _raise_for_error(response: requests.Response) -> None:
        if response.ok:
            return
        try:
            body = response.json()
        except ValueError:
            body = response.text
        raise RuntimeError(f"对话模型请求失败：HTTP {response.status_code}，{build_text_snippet(body)}")

    @staticmethod
    def _resolve_reasoning_effort(config: dict[str, Any], profile: dict[str, Any]) -> str:
        raw_value = profile.get("reasoning_effort", config.get("chat_reasoning_effort", ""))
        resolved = str(raw_value or "").strip().lower()
        return resolved if resolved in {"low", "medium", "high"} else ""


def should_retry(response: requests.Response) -> bool:
    return is_retryable_status_code(response.status_code)


def parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    if not text:
        raise RuntimeError("对话模型返回的 message.content 为空，无法解析 JSON。")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        start = text.find("{")
        if start < 0:
            raise RuntimeError(f"对话模型没有返回 JSON，响应片段：{build_text_snippet(text)}") from exc
        try:
            value, _ = json.JSONDecoder().raw_decode(text[start:])
            if not isinstance(value, dict):
                raise ValueError("JSON 根节点不是对象")
            return value
        except json.JSONDecodeError as nested_exc:
            raise RuntimeError(f"对话模型返回了疑似 JSON 片段，但格式无效：{build_text_snippet(text)}") from nested_exc
        except ValueError as nested_exc:
            raise RuntimeError(f"对话模型返回的 JSON 根节点无效：{build_text_snippet(text)}") from nested_exc


def _raise_for_incomplete_response(body: dict[str, Any]) -> None:
    status = str(body.get("status", "")).strip().lower()
    details = body.get("incomplete_details")
    if status != "incomplete" and not isinstance(details, dict):
        return
    reason = details.get("reason") if isinstance(details, dict) else "unknown"
    raise RuntimeError(
        "对话模型响应未完成，无法解析 JSON："
        f"status={status or 'unknown'}，reason={reason or 'unknown'}，"
        f"响应片段：{build_text_snippet(json.dumps(body, ensure_ascii=False))}"
    )


def file_to_data_url(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        mime_type = "image/jpeg"
    elif suffix == ".webp":
        mime_type = "image/webp"
    else:
        mime_type = "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _parse_response_json(response: requests.Response) -> dict[str, Any]:
    """优先按 UTF-8 解析响应体，避免上游缺失 charset 时把中文误解码成乱码。"""
    response_json = getattr(response, "json", None)
    response_content = getattr(response, "content", None)

    if isinstance(response_content, bytes) and response_content:
        decoded_candidates: list[str] = []
        for encoding in ("utf-8-sig", "utf-8"):
            try:
                decoded_text = response_content.decode(encoding)
                decoded_candidates.append(decoded_text)
                return json.loads(decoded_text)
            except UnicodeDecodeError:
                continue
            except json.JSONDecodeError:
                continue
        for decoded_text in decoded_candidates:
            if looks_like_sse_text(decoded_text):
                return parse_response_sse(decoded_text)

    if callable(response_json):
        try:
            return response_json()
        except ValueError as exc:
            raise RuntimeError(_build_invalid_json_message(response)) from exc

    response_text = getattr(response, "text", "")
    if isinstance(response_text, str) and response_text.strip():
        try:
            return json.loads(response_text)
        except json.JSONDecodeError as exc:
            if looks_like_sse_text(response_text):
                return parse_response_sse(response_text)
            raise RuntimeError(_build_invalid_json_message(response, response_text)) from exc
    raise RuntimeError("对话模型返回空响应，无法解析 JSON。")


def _extract_response_content(body: dict[str, Any]) -> str:
    return extract_response_text(body)


def _has_billable_usage(body: dict[str, Any]) -> bool:
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return False
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        if _coerce_positive_int(usage.get(key)) > 0:
            return True
    return False


def _build_billable_ambiguous_response_message(body: dict[str, Any], exc: BaseException) -> str:
    response_id = str(body.get("id", "")).strip() or "unknown"
    usage_summary = _build_usage_summary(body.get("usage"))
    return (
        "检测到可能已计费的歧义空响应，"
        f"response_id={response_id}，{usage_summary}，"
        "已停止自动补充重试以避免重复扣费。"
        f"{build_text_snippet(str(exc))}"
    )


def _build_usage_summary(usage: Any) -> str:
    if not isinstance(usage, dict):
        return "usage=unknown"
    parts = []
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        if key in usage:
            parts.append(f"{key}={usage.get(key)}")
    return "usage=" + (", ".join(parts) if parts else "unknown")


def _build_response_diagnostic(body: dict[str, Any], content: str) -> str:
    """输出响应元数据和文本长度，避免记录完整业务内容。"""
    response_id = str(body.get("id", "")).strip() or "unknown"
    status = str(body.get("status", "")).strip() or "unknown"
    details = body.get("incomplete_details")
    reason = details.get("reason") if isinstance(details, dict) else ""
    text = str(content or "")
    return (
        "模型响应诊断："
        f"response_id={response_id}，status={status}，"
        f"incomplete_reason={reason or 'none'}，{_build_usage_summary(body.get('usage'))}，"
        f"text_chars={len(text)}，text_utf8_bytes={len(text.encode('utf-8'))}"
    )


def _try_extract_response_content(body: dict[str, Any]) -> str:
    try:
        return _extract_response_content(body)
    except (AmbiguousResponseError, RuntimeError):
        return ""


def _coerce_positive_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _build_invalid_json_message(response: requests.Response, response_text: str | None = None) -> str:
    snippet_source = response_text if response_text is not None else _read_response_text(response)
    return f"对话模型返回了非 JSON 响应：HTTP {response.status_code}，响应片段：{build_text_snippet(snippet_source)}"


def _read_response_text(response: requests.Response) -> str:
    response_content = getattr(response, "content", None)
    if isinstance(response_content, bytes) and response_content:
        for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
            try:
                return response_content.decode(encoding)
            except UnicodeDecodeError:
                continue
    response_text = getattr(response, "text", "")
    return response_text if isinstance(response_text, str) else ""

