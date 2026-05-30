from __future__ import annotations

import json
from typing import Any


RESPONSE_SNIPPET_LIMIT = 400


class AmbiguousChatResponseError(RuntimeError):
    """表示响应结构存在，但没有提取到可安全消费的文本内容。"""


def extract_chat_completion_text(body: dict[str, Any]) -> str:
    """从兼容 OpenAI 的聊天响应中提取文本，兼容常见代理的字段差异。"""
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        top_level_text = _extract_top_level_text(body)
        if top_level_text:
            return top_level_text
        raise RuntimeError(f"对话模型响应结构缺少 choices：{_build_text_snippet(json.dumps(body, ensure_ascii=False))}")

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise RuntimeError(f"对话模型响应结构缺少可解析的 choice 对象：{_build_text_snippet(json.dumps(body, ensure_ascii=False))}")

    extracted_text = _extract_choice_text(first_choice)
    if extracted_text:
        return extracted_text

    top_level_text = _extract_top_level_text(body)
    if top_level_text:
        return top_level_text

    finish_reason = str(first_choice.get("finish_reason", "")).strip() or "unknown"
    raise AmbiguousChatResponseError(
        "对话模型未返回可用文本内容，"
        f"finish_reason={finish_reason}，响应片段：{_build_text_snippet(json.dumps(body, ensure_ascii=False))}"
    )


def _extract_choice_text(choice: dict[str, Any]) -> str:
    message = choice.get("message")
    if isinstance(message, dict):
        message_content = _extract_content_text(message.get("content"))
        if message_content:
            return message_content

        # 兼容少数代理把文本直接挂在 message.text。
        direct_message_text = _coerce_text(message.get("text"))
        if direct_message_text:
            return direct_message_text

    # 兼容传统 completion 风格的 text 字段。
    direct_choice_text = _coerce_text(choice.get("text"))
    if direct_choice_text:
        return direct_choice_text
    return ""


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


def _build_text_snippet(text: str, limit: int = RESPONSE_SNIPPET_LIMIT) -> str:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return "<empty>"
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}..."
