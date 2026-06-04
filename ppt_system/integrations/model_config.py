from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from ppt_system.integrations.api_url import normalize_api_base_url
from ppt_system.runtime.env_loader import load_dotenv


MODEL_TYPES = {"chat", "image"}
KEY_PLACEHOLDER = "__ENV__"
ENV_KEY_PREFIX = "PPT_SYSTEM"
LOCAL_CONFIG_FILENAME = "config.local.json"


def read_config(path: Path) -> dict[str, Any]:
    config = read_merged_config(path)
    return hydrate_model_config_api_keys(config, env_path=path.with_name(".env"))


def write_config(path: Path, config: dict[str, Any]) -> None:
    target_path = resolve_writable_config_path(path)
    target_path.write_text(json.dumps(strip_model_config_api_keys(config), ensure_ascii=False, indent=2), encoding="utf-8")


def read_merged_config(path: Path) -> dict[str, Any]:
    config = read_json_object(path)
    local_path = resolve_local_config_path(path)
    if local_path.exists():
        config = merge_config(config, read_json_object(local_path))
    return config


def resolve_local_config_path(path: Path) -> Path:
    return path.with_name(LOCAL_CONFIG_FILENAME)


def resolve_writable_config_path(path: Path) -> Path:
    local_path = resolve_local_config_path(path)
    if local_path.exists():
        return local_path
    return path


def read_json_object(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"配置文件必须是 JSON 对象：{path}")
    return config


def merge_config(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy_config(base)
    _merge_mapping(merged, override)
    return merged


def _merge_mapping(base: dict[str, Any], override: dict[str, Any]) -> None:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge_mapping(base[key], value)
        else:
            base[key] = copy_config(value) if isinstance(value, (dict, list)) else value


def list_model_configs(config: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    model_configs = ensure_model_configs(config)
    return {
        "chat": [build_public_model_config(item) for item in model_configs["chat"]],
        "image": [build_public_model_config(item) for item in model_configs["image"]],
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
                if not item["api_key"]:
                    item["api_key"] = str(existing.get("api_key", "")).strip()
                if model_type == "image" and "supports_extended_options" not in payload:
                    item["supports_extended_options"] = _coerce_bool(
                        existing.get("supports_extended_options", item["supports_extended_options"])
                    )
                configs[index] = item
                return item
        raise ValueError("没有找到要更新的模型配置。")

    item["id"] = make_config_id(model_type)
    configs.append(item)
    config[f"active_{model_type}_config_id"] = item["id"]
    return item


def delete_model_config(config: dict[str, Any], model_type: str, config_id: str) -> dict[str, Any]:
    if model_type not in MODEL_TYPES:
        raise ValueError("模型类型只能是 chat 或 image。")

    configs = ensure_model_configs(config)[model_type]
    for existing in configs:
        if existing.get("id") == config_id:
            removed = dict(existing)
            break
    else:
        raise ValueError("没有找到要删除的模型配置。")

    config["model_configs"][model_type] = [item for item in configs if item.get("id") != config_id]

    active_key = f"active_{model_type}_config_id"
    next_configs = config["model_configs"][model_type]
    if config.get(active_key) == config_id:
        config[active_key] = next_configs[0]["id"] if next_configs else ""
    return removed


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
        raise ValueError("配置名称、Base URL 和模型名不能为空。")

    if model_type == "chat":
        item["temperature"] = float(payload.get("temperature", 0.3))
        item["max_tokens"] = int(payload.get("max_tokens", 5000))
        reasoning_effort = str(payload.get("reasoning_effort", "")).strip().lower()
        item["reasoning_effort"] = reasoning_effort if reasoning_effort in {"low", "medium", "high"} else ""
    else:
        item["output_format"] = str(payload.get("output_format", "png")).strip()
        item["supports_extended_options"] = _coerce_bool(payload.get("supports_extended_options", True))
    return item


def make_config_id(model_type: str) -> str:
    return f"{model_type}_{uuid.uuid4().hex[:8]}"


def hydrate_model_config_api_keys(config: dict[str, Any], env_path: Path) -> dict[str, Any]:
    load_dotenv(env_path)
    hydrated = copy_config(config)
    model_configs = ensure_model_configs(hydrated)
    for model_type in MODEL_TYPES:
        items = []
        for item in model_configs[model_type]:
            next_item = dict(item)
            api_key = resolve_model_api_key(env_path, model_type, next_item)
            next_item["api_key"] = api_key
            items.append(next_item)
        model_configs[model_type] = items
    return hydrated


def strip_model_config_api_keys(config: dict[str, Any]) -> dict[str, Any]:
    sanitized = copy_config(config)
    model_configs = ensure_model_configs(sanitized)
    for model_type in MODEL_TYPES:
        model_configs[model_type] = [build_persisted_model_config(item) for item in model_configs[model_type]]
    return sanitized


def build_public_model_config(item: dict[str, Any]) -> dict[str, Any]:
    public_item = dict(item)
    api_key = str(item.get("api_key", "")).strip()
    public_item["api_key"] = api_key
    public_item["api_key_configured"] = bool(api_key)
    public_item["api_key_preview"] = build_api_key_preview(api_key)
    return public_item


def build_persisted_model_config(item: dict[str, Any]) -> dict[str, Any]:
    persisted = dict(item)
    persisted["api_key"] = KEY_PLACEHOLDER if str(item.get("api_key", "")).strip() else ""
    return persisted


def resolve_model_api_key_env_name(model_type: str, item: dict[str, Any]) -> str:
    raw_config_id = str(item.get("id", "")).strip()
    token = raw_config_id or str(item.get("name", "")).strip() or model_type
    safe_token = "".join(char if char.isalnum() else "_" for char in token).upper().strip("_")
    if not safe_token:
        safe_token = model_type.upper()
    return f"{ENV_KEY_PREFIX}_{model_type.upper()}_{safe_token}_API_KEY"


def resolve_model_api_key(env_path: Path, model_type: str, item: dict[str, Any]) -> str:
    env_key = resolve_model_api_key_env_name(model_type, item)
    env_value = os.environ.get(env_key, "").strip()
    if env_value:
        return env_value
    inline_value = str(item.get("api_key", "")).strip()
    if inline_value and inline_value != KEY_PLACEHOLDER:
        return inline_value
    return ""


def save_model_api_key(env_path: Path, model_type: str, item: dict[str, Any]) -> None:
    api_key = str(item.get("api_key", "")).strip()
    if not api_key:
        return
    entries = read_env_entries(env_path)
    env_key = resolve_model_api_key_env_name(model_type, item)
    entries[env_key] = api_key
    write_env_entries(env_path, entries)
    os.environ[env_key] = api_key


def delete_model_api_key(env_path: Path, model_type: str, item: dict[str, Any]) -> None:
    entries = read_env_entries(env_path)
    env_key = resolve_model_api_key_env_name(model_type, item)
    if env_key in entries:
        del entries[env_key]
        write_env_entries(env_path, entries)
    os.environ.pop(env_key, None)


def copy_config(config: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(config, ensure_ascii=False))


def read_env_entries(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    entries: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        entries[key.strip()] = value.strip().strip('"').strip("'")
    return entries


def write_env_entries(path: Path, entries: dict[str, str]) -> None:
    lines = [f"{key}={value}" for key, value in sorted(entries.items())]
    content = "\n".join(lines)
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8")


def build_api_key_preview(api_key: str) -> str:
    secret = str(api_key or "").strip()
    if not secret:
        return ""
    if len(secret) <= 10:
        return f"{secret[:2]}{'*' * max(1, len(secret) - 4)}{secret[-2:]}"
    visible_prefix = min(7, len(secret) - 3)
    visible_suffix = min(3, max(1, len(secret) - visible_prefix))
    masked_length = max(4, len(secret) - visible_prefix - visible_suffix)
    return f"{secret[:visible_prefix]}{'*' * masked_length}{secret[-visible_suffix:]}"


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"0", "false", "no", "off"}:
        return False
    if text in {"1", "true", "yes", "on"}:
        return True
    return bool(value)
