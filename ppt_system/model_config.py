from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from ppt_system.api_url import normalize_api_base_url


MODEL_TYPES = {"chat", "image"}


def read_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_config(path: Path, config: dict[str, Any]) -> None:
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def list_model_configs(config: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    model_configs = ensure_model_configs(config)
    return {
        "chat": list(model_configs["chat"]),
        "image": list(model_configs["image"]),
    }


def ensure_model_configs(config: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    model_configs = config.setdefault("model_configs", {})
    model_configs.setdefault("chat", [])
    model_configs.setdefault("image", [])
    return model_configs


def get_active_model_config(config: dict[str, Any], model_type: str) -> dict[str, Any]:
    configs = ensure_model_configs(config)
    if model_type not in MODEL_TYPES:
        raise ValueError("模型类型只能是 chat 或 image。")

    active_id = config.get(f"active_{model_type}_config_id")
    candidates = configs[model_type]
    for item in candidates:
        if item.get("id") == active_id:
            return dict(item)

    if candidates:
        return dict(candidates[0])

    raise ValueError(f"未配置 {model_type} 模型。")


def upsert_model_config(
    config: dict[str, Any],
    model_type: str,
    payload: dict[str, Any],
    config_id: str | None = None,
) -> dict[str, Any]:
    if model_type not in MODEL_TYPES:
        raise ValueError("模型类型只能是 chat 或 image。")

    configs = ensure_model_configs(config)[model_type]
    item = sanitize_model_config(model_type, payload)
    if config_id:
        item["id"] = config_id
        for index, existing in enumerate(configs):
            if existing.get("id") == config_id:
                configs[index] = item
                return item
        raise ValueError("没有找到要更新的模型配置。")

    item["id"] = make_config_id(model_type)
    configs.append(item)
    config[f"active_{model_type}_config_id"] = item["id"]
    return item


def delete_model_config(config: dict[str, Any], model_type: str, config_id: str) -> None:
    if model_type not in MODEL_TYPES:
        raise ValueError("模型类型只能是 chat 或 image。")

    configs = ensure_model_configs(config)[model_type]
    next_configs = [item for item in configs if item.get("id") != config_id]
    if len(next_configs) == len(configs):
        raise ValueError("没有找到要删除的模型配置。")
    config["model_configs"][model_type] = next_configs

    active_key = f"active_{model_type}_config_id"
    if config.get(active_key) == config_id:
        config[active_key] = next_configs[0]["id"] if next_configs else ""


def set_active_model_config(config: dict[str, Any], model_type: str, config_id: str) -> None:
    configs = ensure_model_configs(config)[model_type]
    if not any(item.get("id") == config_id for item in configs):
        raise ValueError("没有找到要启用的模型配置。")
    config[f"active_{model_type}_config_id"] = config_id


def sanitize_model_config(model_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    item = {
        "name": str(payload.get("name", "")).strip(),
        "base_url": normalize_api_base_url(str(payload.get("base_url", ""))),
        "api_key": str(payload.get("api_key", "")).strip(),
        "model": str(payload.get("model", "")).strip(),
        "enabled": bool(payload.get("enabled", True)),
    }
    if not item["name"] or not item["base_url"] or not item["model"]:
        raise ValueError("名称、Base URL 和模型名不能为空。")

    if model_type == "chat":
        item["temperature"] = float(payload.get("temperature", 0.3))
        item["max_tokens"] = int(payload.get("max_tokens", 5000))
        reasoning_effort = str(payload.get("reasoning_effort", "")).strip().lower()
        item["reasoning_effort"] = reasoning_effort if reasoning_effort in {"low", "medium", "high"} else ""
    else:
        item["output_format"] = str(payload.get("output_format", "png")).strip()
    return item


def make_config_id(model_type: str) -> str:
    return f"{model_type}_{uuid.uuid4().hex[:8]}"
