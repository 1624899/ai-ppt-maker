from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ServerSentEvent:
    event: str
    data: str


def looks_like_sse_text(text: str) -> bool:
    """判断响应体是否像服务器发送事件，避免把普通错误文本误判为流式响应。"""
    for line in _normalize_line_endings(text).split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        return stripped.startswith(("data:", "event:", "id:", "retry:", ":"))
    return False


def parse_chat_completion_sse(text: str) -> dict[str, Any]:
    """把 OpenAI 兼容的流式事件合并成普通对话响应结构。"""
    json_events = parse_sse_json_events(text)
    if not json_events:
        raise RuntimeError("对话模型返回了空 SSE 响应，无法解析 JSON。")

    chat_body = _merge_chat_completion_chunks(json_events)
    if chat_body:
        return chat_body

    response_body = _merge_response_api_events(json_events)
    if response_body:
        return response_body

    if len(json_events) == 1:
        return json_events[0]

    raise RuntimeError("对话模型返回的 SSE 响应缺少可合并的文本增量。")


def parse_sse_json_events(text: str) -> list[dict[str, Any]]:
    """解析 SSE 事件中的 JSON data，自动忽略 [DONE] 结束标记。"""
    events: list[dict[str, Any]] = []
    for event in parse_sse_events(text):
        data = event.data.strip()
        if not data or data == "[DONE]":
            continue
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"对话模型返回了无法解析的 SSE JSON 片段：{_build_text_snippet(data)}") from exc
        if isinstance(parsed, dict):
            events.append(parsed)
    return events


def parse_sse_events(text: str) -> list[ServerSentEvent]:
    """按 SSE 规范解析事件，支持 CRLF、注释行和多行 data 字段。"""
    events: list[ServerSentEvent] = []
    event_name = "message"
    data_lines: list[str] = []

    def flush_event() -> None:
        nonlocal event_name, data_lines
        if data_lines:
            events.append(ServerSentEvent(event=event_name or "message", data="\n".join(data_lines)))
        event_name = "message"
        data_lines = []

    for line in _normalize_line_endings(text).split("\n"):
        if line == "":
            flush_event()
            continue
        if line.startswith(":"):
            continue
        field, value = _split_sse_field(line)
        if field == "event":
            event_name = value or "message"
        elif field == "data":
            data_lines.append(value)

    flush_event()
    return events


def _merge_chat_completion_chunks(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    choice_parts: dict[int, list[str]] = {}
    choice_roles: dict[int, str] = {}
    finish_reasons: dict[int, Any] = {}
    metadata: dict[str, Any] = {}
    usage: Any = None
    saw_chat_choice = False

    for event in events:
        choices = event.get("choices")
        if not isinstance(choices, list):
            continue
        saw_chat_choice = True
        for key in ("id", "created", "model", "system_fingerprint"):
            if key in event:
                metadata[key] = event[key]
        if event.get("usage") is not None:
            usage = event.get("usage")

        for fallback_index, choice in enumerate(choices):
            if not isinstance(choice, dict):
                continue
            index = _coerce_choice_index(choice.get("index"), fallback_index)
            delta = choice.get("delta")
            message = choice.get("message")
            if isinstance(delta, dict):
                role = _coerce_text(delta.get("role"))
                if role:
                    choice_roles[index] = role
                text = _extract_content_text(delta.get("content"))
                if text:
                    choice_parts.setdefault(index, []).append(text)
            elif isinstance(message, dict):
                role = _coerce_text(message.get("role"))
                if role:
                    choice_roles[index] = role
                text = _extract_content_text(message.get("content"))
                if text:
                    choice_parts.setdefault(index, []).append(text)

            text = _extract_content_text(choice.get("text"))
            if text:
                choice_parts.setdefault(index, []).append(text)

            if choice.get("finish_reason") is not None:
                finish_reasons[index] = choice.get("finish_reason")

    if not saw_chat_choice:
        return None

    choice_indexes = sorted(set(choice_parts) | set(choice_roles) | set(finish_reasons) or {0})
    choices_body: list[dict[str, Any]] = []
    for index in choice_indexes:
        choices_body.append(
            {
                "index": index,
                "message": {
                    "role": choice_roles.get(index, "assistant"),
                    "content": "".join(choice_parts.get(index, [])),
                },
                "finish_reason": finish_reasons.get(index),
            }
        )

    body: dict[str, Any] = {
        "object": "chat.completion",
        "choices": choices_body,
    }
    body.update(metadata)
    if usage is not None:
        body["usage"] = usage
    return body


def _merge_response_api_events(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    text_parts: list[str] = []
    final_response: dict[str, Any] | None = None

    for event in events:
        event_type = _coerce_text(event.get("type"))
        if event_type in {"response.output_text.delta", "response.text.delta"}:
            delta = _extract_content_text(event.get("delta"))
            if delta:
                text_parts.append(delta)
            continue
        if event_type in {"response.completed", "response.done"}:
            response = event.get("response")
            if isinstance(response, dict):
                final_response = response

    if final_response is not None:
        output_text = _coerce_text(final_response.get("output_text"))
        if output_text:
            return final_response
        if text_parts:
            merged = dict(final_response)
            merged["output_text"] = "".join(text_parts)
            return merged
        return final_response

    if text_parts:
        return {"output_text": "".join(text_parts)}
    return None


def _split_sse_field(line: str) -> tuple[str, str]:
    if ":" not in line:
        return line, ""
    field, value = line.split(":", 1)
    if value.startswith(" "):
        value = value[1:]
    return field, value


def _coerce_choice_index(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _extract_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        direct_text = _coerce_text(content.get("text"), strip=False)
        if direct_text:
            return direct_text
        return _coerce_text(content.get("value"), strip=False)
    if not isinstance(content, list):
        return ""

    fragments: list[str] = []
    for item in content:
        if isinstance(item, str):
            fragments.append(item)
            continue
        if not isinstance(item, dict):
            continue
        text = _coerce_text(item.get("text"), strip=False)
        if text:
            fragments.append(text)
            continue
        value = _coerce_text(item.get("value"), strip=False)
        if value:
            fragments.append(value)
    return "".join(fragments)


def _coerce_text(value: Any, *, strip: bool = True) -> str:
    if isinstance(value, str):
        return value.strip() if strip else value
    if isinstance(value, dict):
        nested_value = value.get("value")
        if isinstance(nested_value, str):
            return nested_value.strip() if strip else nested_value
    return ""


def _normalize_line_endings(text: str) -> str:
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n")


def _build_text_snippet(text: str, limit: int = 300) -> str:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return "<empty>"
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}..."
