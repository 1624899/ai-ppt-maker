from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests

from ppt_system.integrations.api_url import normalize_api_base_url


DEFAULT_CONNECTIVITY_TIMEOUT_SECONDS = 20
RESPONSE_SNIPPET_LIMIT = 300


@dataclass(frozen=True)
class ConnectivityResult:
    ok: bool
    message: str
    status_code: int | None = None
    elapsed_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "message": self.message,
            "elapsed_ms": self.elapsed_ms,
        }
        if self.status_code is not None:
            payload["status_code"] = self.status_code
        return payload


def test_model_connectivity(
    model_type: str,
    profile: dict[str, Any],
    *,
    timeout: int = DEFAULT_CONNECTIVITY_TIMEOUT_SECONDS,
) -> ConnectivityResult:
    normalized_type = str(model_type or "").strip().lower()
    normalized_profile = normalize_profile(profile)
    validate_profile(normalized_type, normalized_profile)
    if normalized_type == "chat":
        return test_chat_connectivity(normalized_profile, timeout=timeout)
    if normalized_type == "image":
        return test_image_connectivity(normalized_profile, timeout=timeout)
    raise ValueError("模型类型只能是 chat 或 image。")


# 这是业务探测函数，不是 pytest 测试用例；避免被测试收集误判为需要 fixture 的测试函数。
test_model_connectivity.__test__ = False


def normalize_profile(profile: dict[str, Any]) -> dict[str, Any]:
    item = dict(profile or {})
    item["base_url"] = normalize_api_base_url(str(item.get("base_url", "")))
    item["api_key"] = str(item.get("api_key", "")).strip()
    item["model"] = str(item.get("model", "")).strip()
    return item


def validate_profile(model_type: str, profile: dict[str, Any]) -> None:
    if model_type not in {"chat", "image"}:
        raise ValueError("模型类型只能是 chat 或 image。")
    if not profile.get("base_url") or not profile.get("model"):
        raise ValueError("Base URL 和模型名不能为空。")
    if not profile.get("api_key"):
        raise ValueError("API Key 不能为空。")


def test_chat_connectivity(profile: dict[str, Any], *, timeout: int) -> ConnectivityResult:
    payload: dict[str, Any] = {
        "model": profile["model"],
        "messages": [
            {"role": "system", "content": "只回复 ok。"},
            {"role": "user", "content": "ping"},
        ],
        "temperature": 0,
        "max_tokens": 8,
    }
    reasoning_effort = str(profile.get("reasoning_effort", "")).strip().lower()
    if reasoning_effort in {"low", "medium", "high"}:
        payload["reasoning_effort"] = reasoning_effort

    return post_json_probe(
        f"{profile['base_url']}/chat/completions",
        profile["api_key"],
        payload,
        timeout=timeout,
        success_message="对话模型连通正常。",
        failure_prefix="对话模型连通失败",
    )


def test_image_connectivity(profile: dict[str, Any], *, timeout: int) -> ConnectivityResult:
    # 用 models 端点做轻量鉴权和网络探测，避免连通测试触发真实生图计费。
    started_at = time.perf_counter()
    try:
        response = requests.get(
            f"{profile['base_url']}/models",
            headers={"Authorization": f"Bearer {profile['api_key']}"},
            timeout=timeout,
        )
    except requests.Timeout:
        return ConnectivityResult(False, f"生图模型连通超时：{timeout}s。", elapsed_ms=elapsed_ms_since(started_at))
    except requests.RequestException as exc:
        return ConnectivityResult(False, f"生图模型连通异常：{exc}", elapsed_ms=elapsed_ms_since(started_at))

    elapsed_ms = elapsed_ms_since(started_at)
    if response.ok:
        return ConnectivityResult(True, "生图模型服务连通正常。", response.status_code, elapsed_ms)
    return ConnectivityResult(
        False,
        build_http_failure_message("生图模型连通失败", response),
        response.status_code,
        elapsed_ms,
    )


def post_json_probe(
    url: str,
    api_key: str,
    payload: dict[str, Any],
    *,
    timeout: int,
    success_message: str,
    failure_prefix: str,
) -> ConnectivityResult:
    started_at = time.perf_counter()
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
    except requests.Timeout:
        return ConnectivityResult(False, f"{failure_prefix}：请求超时 {timeout}s。", elapsed_ms=elapsed_ms_since(started_at))
    except requests.RequestException as exc:
        return ConnectivityResult(False, f"{failure_prefix}：{exc}", elapsed_ms=elapsed_ms_since(started_at))

    elapsed_ms = elapsed_ms_since(started_at)
    if response.ok:
        return ConnectivityResult(True, success_message, response.status_code, elapsed_ms)
    return ConnectivityResult(
        False,
        build_http_failure_message(failure_prefix, response),
        response.status_code,
        elapsed_ms,
    )


def build_http_failure_message(prefix: str, response: requests.Response) -> str:
    detail = extract_response_error(response)
    if detail:
        return f"{prefix}：HTTP {response.status_code}，{detail}"
    return f"{prefix}：HTTP {response.status_code}。"


def extract_response_error(response: requests.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return build_text_snippet(response.text)

    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            return build_text_snippet(str(error.get("message") or error.get("code") or error))
        if isinstance(error, str):
            return build_text_snippet(error)
        message = body.get("message")
        if isinstance(message, str):
            return build_text_snippet(message)
    return build_text_snippet(str(body))


def build_text_snippet(text: str, limit: int = RESPONSE_SNIPPET_LIMIT) -> str:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return ""
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}..."


def elapsed_ms_since(started_at: float) -> int:
    return max(0, int((time.perf_counter() - started_at) * 1000))
