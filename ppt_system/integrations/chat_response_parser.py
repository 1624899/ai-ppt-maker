from __future__ import annotations

import json
from typing import Any

from ppt_system.integrations.http_retry_policy import build_text_snippet


class AmbiguousResponseError(RuntimeError):
    """表示响应结构存在，但没有提取到可安全消费的文本内容。"""


def extract_response_text(body: dict[str, Any]) -> str:
    """从 OpenAI Responses API 响应中提取可消费文本。"""
    extracted_text = _extract_top_level_text(body)
    if extracted_text:
        return extracted_text

    status = str(body.get("status", "")).strip() or "unknown"
    raise AmbiguousResponseError(
        "对话模型未返回可用文本内容，"
        f"status={status}，响应片段：{build_text_snippet(json.dumps(body, ensure_ascii=False))}"
    )


def _extract_top_level_text(body: dict[str, Any]) -> str:
    direct_output_text = _coerce_text(body.get("output_text"))
    if direct_output_text:
        return direct_output_text

    outputs = body.get("output")
    if not isinstance(outputs, list):
        return ""
    fragments: list[str] = []
    for item in outputs:
        if not isinstance(item, dict):
            continue
        if str(item.get("type", "")).strip().lower() != "message":
            continue
        if item.get("status") not in {None, "", "completed"}:
            continue
        content_text = _extract_content_text(item.get("content"))
        if content_text:
            fragments.append(content_text)
    return "".join(fragment for fragment in fragments if fragment).strip()


def _extract_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        return _coerce_text(content.get("text"))
    if not isinstance(content, list):
        return ""

    fragments: list[str] = []
    for item in content:
        if isinstance(item, str):
            normalized = item.strip()
            if normalized:
                fragments.append(normalized)
            continue
        if not isinstance(item, dict):
            continue
        candidate = _coerce_text(item.get("text"), strip=False)
        if candidate:
            fragments.append(candidate)
            continue
        candidate = _coerce_text(item.get("value"), strip=False)
        if candidate:
            fragments.append(candidate)
    return "".join(fragment for fragment in fragments if fragment).strip()


def _coerce_text(value: Any, *, strip: bool = True) -> str:
    if isinstance(value, str):
        return value.strip() if strip else value
    if isinstance(value, dict):
        nested_value = value.get("value")
        if isinstance(nested_value, str):
            return nested_value.strip() if strip else nested_value
    return ""
