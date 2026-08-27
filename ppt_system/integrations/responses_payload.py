from __future__ import annotations

from typing import Any


def build_responses_url(api_base_url: str) -> str:
    return f"{api_base_url}/responses"


def build_json_response_payload(
    *,
    model: str,
    messages: list[dict[str, Any]],
    reasoning_effort: str,
    stream: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "input": build_responses_input(messages),
        "text": {"format": {"type": "json_object"}},
        "store": False,
        "stream": stream,
    }
    if reasoning_effort:
        payload["reasoning"] = {"effort": reasoning_effort}
    return payload


def build_responses_image_input_item(image_url: str) -> dict[str, Any]:
    return {
        "type": "input_image",
        "image_url": image_url,
    }


def build_responses_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_messages: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "user").strip() or "user"
        normalized_messages.append(
            {
                "role": role,
                "content": normalize_responses_content(message.get("content")),
            }
        )
    return normalized_messages


def normalize_responses_content(content: Any) -> str | list[dict[str, Any]]:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        item = normalize_responses_content_item(content)
        return [item] if item else []
    if not isinstance(content, list):
        return str(content or "")

    items: list[dict[str, Any]] = []
    for raw_item in content:
        if isinstance(raw_item, str):
            if raw_item:
                items.append({"type": "input_text", "text": raw_item})
            continue
        if not isinstance(raw_item, dict):
            continue
        item = normalize_responses_content_item(raw_item)
        if item:
            items.append(item)
    return items


def normalize_responses_content_item(item: dict[str, Any]) -> dict[str, Any] | None:
    item_type = str(item.get("type") or "").strip()
    if item_type == "input_text":
        text = _coerce_text(item.get("text"))
        return {"type": "input_text", "text": text} if text else None
    if item_type == "input_image":
        return _normalize_input_image_item(item)
    if item_type in {"text", "image_url", "output_text"}:
        raise ValueError(f"Responses API 不接受旧内容块类型 `{item_type}`，请使用 input_text/input_image。")
    return dict(item)


def _normalize_input_image_item(item: dict[str, Any]) -> dict[str, Any] | None:
    image_url = _extract_image_url(item.get("image_url"))
    file_id = _coerce_text(item.get("file_id"))
    detail = _coerce_text(item.get("detail"))
    normalized: dict[str, Any] = {"type": "input_image"}
    if image_url:
        normalized["image_url"] = image_url
    if file_id:
        normalized["file_id"] = file_id
    if detail:
        normalized["detail"] = detail
    return normalized if image_url or file_id else None


def _extract_image_url(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return _coerce_text(value.get("url"))
    return ""


def _coerce_text(value: Any) -> str:
    return str(value or "").strip()
