from __future__ import annotations

import base64
from pathlib import Path
from typing import Any
from urllib.parse import unquote_to_bytes

import requests


def save_image_from_response_payload(
    response_json: dict[str, Any],
    output_path: Path,
    *,
    timeout: int,
) -> dict[str, Any]:
    """兼容多种图片响应格式，并将首张图片写入目标文件。"""
    data = response_json.get("data", [])
    if not data:
        raise RuntimeError(f"图像接口没有返回 data：{response_json}")

    image = data[0]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(resolve_image_bytes(image, timeout=timeout))
    return image


def resolve_image_bytes(image_payload: dict[str, Any], *, timeout: int) -> bytes:
    """从单张图片响应中提取二进制内容。"""
    b64_json = image_payload.get("b64_json")
    if b64_json:
        return _decode_base64_bytes(str(b64_json))

    image_url = str(image_payload.get("url", "")).strip()
    if not image_url:
        raise RuntimeError(f"图像接口没有返回 b64_json 或 url：{image_payload}")

    if image_url.startswith("data:"):
        return decode_data_uri(image_url)

    image_response = requests.get(image_url, timeout=timeout)
    image_response.raise_for_status()
    return image_response.content


def decode_data_uri(data_uri: str) -> bytes:
    """解析 data URI，兼容 base64 与百分号编码的数据体。"""
    if not data_uri.startswith("data:"):
        raise ValueError("仅支持 data: 开头的图片数据。")

    header, separator, payload = data_uri.partition(",")
    if not separator:
        raise ValueError("data URI 缺少数据内容。")

    if ";base64" in header.lower():
        return _decode_base64_bytes(payload)
    return unquote_to_bytes(payload)


def _decode_base64_bytes(payload: str) -> bytes:
    try:
        return base64.b64decode(payload)
    except Exception as exc:  # pragma: no cover - 依赖底层异常类型
        raise RuntimeError("图像数据不是合法的 Base64 内容。") from exc
