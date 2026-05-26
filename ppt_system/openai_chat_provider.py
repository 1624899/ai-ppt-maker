from __future__ import annotations

import json
import re
import time
import base64
from pathlib import Path
from typing import Any

import requests

from ppt_system.logging_utils import format_log_line


class OpenAIChatProvider:
    def __init__(self, config: dict[str, Any], profile: dict[str, Any]) -> None:
        self.profile = profile
        self.api_key = str(profile.get("api_key", "")).strip()
        self.api_base_url = str(profile.get("base_url", config.get("chat_api_base_url", "https://api.openai.com/v1"))).rstrip("/")
        self.model = str(profile.get("model", config.get("chat_model", "gpt-5.5")))
        self.temperature = float(profile.get("temperature", config.get("chat_temperature", 0.3)))
        self.max_tokens = int(profile.get("max_tokens", config.get("chat_max_tokens", 5000)))
        self.reasoning_effort = self._resolve_reasoning_effort(config, profile)
        self.timeout = int(config.get("request_timeout_seconds", 600))
        self.retry_count = int(config.get("request_retry_count", 3))
        self.retry_initial_delay = float(config.get("request_retry_initial_delay_seconds", 5))

        if not self.api_key:
            raise RuntimeError("未在模型配置中填写对话模型 API Key。")

    @property
    def chat_completions_url(self) -> str:
        return f"{self.api_base_url}/chat/completions"

    def complete_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        print(
            format_log_line(
                "chat",
                f"开始请求模型 `{self.model}`，timeout={self.timeout}s，max_tokens={self.max_tokens}",
            ),
            flush=True,
        )
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
        }
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        started_at = time.perf_counter()
        response = self._post_with_retry(payload)
        elapsed = time.perf_counter() - started_at
        print(
            format_log_line(
                "chat",
                f"模型响应完成，status={response.status_code}，耗时={elapsed:.1f}s",
            ),
            flush=True,
        )
        self._raise_for_error(response)
        body = _parse_response_json(response)
        content = body["choices"][0]["message"]["content"]
        return parse_json_content(content)

    def build_image_message_item(self, image_path: Path) -> dict[str, Any]:
        return {
            "type": "image_url",
            "image_url": {
                "url": file_to_data_url(image_path),
            },
        }

    def _post_with_retry(self, payload: dict[str, Any]) -> requests.Response:
        last_response: requests.Response | None = None
        for attempt in range(self.retry_count + 1):
            attempt_no = attempt + 1
            print(
                format_log_line(
                    "chat",
                    f"发送第 {attempt_no}/{self.retry_count + 1} 次请求 -> {self.chat_completions_url}",
                ),
                flush=True,
            )
            request_started_at = time.perf_counter()
            try:
                response = requests.post(
                    self.chat_completions_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=self.timeout,
                )
            except requests.Timeout as exc:
                elapsed = time.perf_counter() - request_started_at
                print(
                    format_log_line(
                        "chat",
                        f"第 {attempt_no} 次请求超时，耗时={elapsed:.1f}s，timeout={self.timeout}s",
                    ),
                    flush=True,
                )
                if attempt >= self.retry_count:
                    raise RuntimeError(f"对话模型请求超时：{self.timeout}s") from exc
                delay = self.retry_initial_delay * (2**attempt)
                print(format_log_line("chat", f"将在 {delay:.1f}s 后重试"), flush=True)
                time.sleep(delay)
                continue
            except requests.RequestException as exc:
                elapsed = time.perf_counter() - request_started_at
                print(
                    format_log_line(
                        "chat",
                        f"第 {attempt_no} 次请求异常：{exc.__class__.__name__}，耗时={elapsed:.1f}s",
                    ),
                    flush=True,
                )
                if attempt >= self.retry_count:
                    raise RuntimeError(f"对话模型请求异常：{exc}") from exc
                delay = self.retry_initial_delay * (2**attempt)
                print(format_log_line("chat", f"将在 {delay:.1f}s 后重试"), flush=True)
                time.sleep(delay)
                continue
            last_response = response
            elapsed = time.perf_counter() - request_started_at
            print(
                format_log_line(
                    "chat",
                    f"第 {attempt_no} 次请求返回 HTTP {response.status_code}，耗时={elapsed:.1f}s",
                ),
                flush=True,
            )
            if not should_retry(response) or attempt >= self.retry_count:
                return response

            retry_after = response.headers.get("Retry-After", "").strip()
            delay = float(retry_after) if retry_after.isdigit() else self.retry_initial_delay * (2**attempt)
            print(
                format_log_line(
                    "chat",
                    f"命中可重试状态码 {response.status_code}，将在 {delay:.1f}s 后重试",
                ),
                flush=True,
            )
            time.sleep(delay)
        return last_response

    @staticmethod
    def _raise_for_error(response: requests.Response) -> None:
        if response.ok:
            return
        try:
            body = response.json()
        except ValueError:
            body = response.text
        raise RuntimeError(f"对话模型请求失败：HTTP {response.status_code}，{body}")

    @staticmethod
    def _resolve_reasoning_effort(config: dict[str, Any], profile: dict[str, Any]) -> str:
        raw_value = profile.get("reasoning_effort", config.get("chat_reasoning_effort", ""))
        resolved = str(raw_value or "").strip().lower()
        return resolved if resolved in {"low", "medium", "high"} else ""


def should_retry(response: requests.Response) -> bool:
    return response.status_code in {408, 409, 425, 429, 500, 502, 503, 504}


def parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise RuntimeError(f"对话模型没有返回 JSON：{content}")
        return json.loads(match.group(0))


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
        for encoding in ("utf-8-sig", "utf-8"):
            try:
                return json.loads(response_content.decode(encoding))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue

    if callable(response_json):
        return response_json()

    response_text = getattr(response, "text", "")
    if isinstance(response_text, str) and response_text.strip():
        return json.loads(response_text)
    raise RuntimeError("对话模型返回空响应，无法解析 JSON。")
