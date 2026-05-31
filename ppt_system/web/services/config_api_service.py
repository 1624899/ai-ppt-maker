from __future__ import annotations

from flask import jsonify, request

from ppt_system.integrations.model_config import sanitize_model_config
from ppt_system.integrations.model_connectivity import test_model_connectivity
from ppt_system.generation.reference_style_adherence import (
    REFERENCE_STYLE_ADHERENCE_LABELS,
    REFERENCE_STYLE_ADHERENCE_LEVELS,
)
from ppt_system.web.runtime import get_runtime_module


def api_config():
    runtime = get_runtime_module()
    config = runtime.read_config()
    defaults = runtime.default_generation_options(config)
    return jsonify(
        {
            "max_pages": config["max_pages"],
            "default_pages": config["default_pages"],
            "default_image_preset": config["default_image_preset"],
            "image_presets": config["image_presets"],
            "image_width": config["image_width"],
            "image_height": config["image_height"],
            "generation_mode": config["generation_mode"],
            "api_base_url": config["api_base_url"],
            "image_model": config["image_model"],
            "image_size": config["image_size"],
            "image_resolution": config["image_resolution"],
            "image_quality": config["image_quality"],
            "image_background": config["image_background"],
            "image_output_format": config["image_output_format"],
            "default_include_cover_page": bool(defaults["include_cover_page"]),
            "default_page_richness": str(defaults["page_richness_default"]),
            "page_richness_options": list(runtime.PAGE_RICHNESS_LEVELS),
            "default_reference_style_adherence": str(defaults["reference_style_adherence"]),
            "reference_style_adherence_options": [
                {"value": value, "label": REFERENCE_STYLE_ADHERENCE_LABELS[value]}
                for value in REFERENCE_STYLE_ADHERENCE_LEVELS
            ],
            "job_db_maintenance": runtime.resolve_job_db_maintenance_config(config),
            "active_chat_config_id": config.get("active_chat_config_id", ""),
            "active_image_config_id": config.get("active_image_config_id", ""),
        }
    )


def api_model_configs():
    runtime = get_runtime_module()
    config = runtime.read_config()
    return jsonify(
        {
            "active_chat_config_id": config.get("active_chat_config_id", ""),
            "active_image_config_id": config.get("active_image_config_id", ""),
            "configs": runtime.list_model_configs(config),
        }
    )


def api_create_model_config(model_type: str):
    runtime = get_runtime_module()
    config = runtime.read_config()
    try:
        item = runtime.upsert_model_config(config, model_type, request.get_json(force=True))
        runtime.save_model_api_key(runtime.ENV_PATH, model_type, item)
        runtime.write_config(runtime.CONFIG_PATH, config)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(runtime.list_model_configs(config)[model_type][-1])


def api_update_model_config(model_type: str, config_id: str):
    runtime = get_runtime_module()
    config = runtime.read_config()
    try:
        runtime.upsert_model_config(config, model_type, request.get_json(force=True), config_id=config_id)
        item = next(
            candidate
            for candidate in runtime.list_model_configs(config)[model_type]
            if candidate.get("id") == config_id
        )
        runtime.save_model_api_key(runtime.ENV_PATH, model_type, item)
        runtime.write_config(runtime.CONFIG_PATH, config)
        return jsonify(item)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except StopIteration:
        return jsonify({"error": "保存后未找到配置。"}), 500


def api_delete_model_config(model_type: str, config_id: str):
    runtime = get_runtime_module()
    config = runtime.read_config()
    try:
        removed = runtime.delete_model_config(config, model_type, config_id)
        runtime.delete_model_api_key(runtime.ENV_PATH, model_type, removed)
        runtime.write_config(runtime.CONFIG_PATH, config)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True})


def api_activate_model_config(model_type: str, config_id: str):
    runtime = get_runtime_module()
    config = runtime.read_config()
    try:
        runtime.set_active_model_config(config, model_type, config_id)
        runtime.write_config(runtime.CONFIG_PATH, config)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True})


def api_test_model_config(model_type: str):
    runtime = get_runtime_module()
    config = runtime.read_config()
    payload = request.get_json(force=True) or {}
    try:
        profile = build_connectivity_profile(runtime, config, model_type, payload)
        timeout = int(config.get("connectivity_test_timeout_seconds", 20))
        result = test_model_connectivity(model_type, profile, timeout=timeout)
    except ValueError as exc:
        return jsonify({"error": str(exc), "ok": False}), 400
    return jsonify(result.to_dict()), (200 if result.ok else 400)


def build_connectivity_profile(runtime, config: dict, model_type: str, payload: dict) -> dict:
    if model_type not in {"chat", "image"}:
        raise ValueError("模型类型只能是 chat 或 image。")

    profile = dict(payload)
    config_id = str(profile.get("id", "")).strip()
    existing = find_model_config(config, model_type, config_id) if config_id else None
    if existing:
        merged = dict(existing)
        merged.update({key: value for key, value in profile.items() if key != "api_key"})
        api_key = str(profile.get("api_key", "")).strip()
        if api_key:
            merged["api_key"] = api_key
        profile = merged

    sanitized = sanitize_model_config(model_type, profile)
    if not sanitized.get("api_key") and existing:
        sanitized["api_key"] = str(existing.get("api_key", "")).strip()
    return sanitized


def find_model_config(config: dict, model_type: str, config_id: str) -> dict | None:
    configs = config.get("model_configs", {}).get(model_type, [])
    for item in configs:
        if str(item.get("id", "")).strip() == config_id:
            return dict(item)
    return None
