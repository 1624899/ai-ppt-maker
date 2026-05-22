from __future__ import annotations

import json
import re
import time
import base64
from pathlib import Path
from typing import Any

import requests


class OpenAIChatProvider:
    def __init__(self, config: dict[str, Any], profile: dict[str, Any]) -> None:
        self.profile = profile
        self.api_key = str(profile.get("api_key", "")).strip()
        self.api_base_url = str(profile.get("base_url", config.get("chat_api_base_url", "https://api.openai.com/v1"))).rstrip("/")
        self.model = str(profile.get("model", config.get("chat_model", "gpt-5.5")))
        self.temperature = float(profile.get("temperature", config.get("chat_temperature", 0.3)))
        self.max_tokens = int(profile.get("max_tokens", config.get("chat_max_tokens", 5000)))
        self.timeout = int(config.get("request_timeout_seconds", 600))
        self.retry_count = int(config.get("request_retry_count", 3))
        self.retry_initial_delay = float(config.get("request_retry_initial_delay_seconds", 5))

        if not self.api_key:
            raise RuntimeError("未在模型配置中填写对话模型 API Key。")

    @property
    def chat_completions_url(self) -> str:
        return f"{self.api_base_url}/chat/completions"

    def complete_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
        }
        response = self._post_with_retry(payload)
        self._raise_for_error(response)
        body = response.json()
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
            response = requests.post(
                self.chat_completions_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout,
            )
            last_response = response
            if not should_retry(response) or attempt >= self.retry_count:
                return response

            retry_after = response.headers.get("Retry-After", "").strip()
            delay = float(retry_after) if retry_after.isdigit() else self.retry_initial_delay * (2**attempt)
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
