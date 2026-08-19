from __future__ import annotations

from flask import jsonify, request

from ppt_system.generation.generation_options import default_generation_options
from ppt_system.generation.page_richness import PAGE_RICHNESS_LEVELS
from ppt_system.integrations.model_config import (
    delete_model_config,
    delete_model_env_fields,
    list_model_configs,
    sanitize_model_config,
    save_model_env_fields,
    set_active_model_config,
    upsert_model_config,
    write_config,
)
from ppt_system.integrations.model_connectivity import test_model_connectivity
from ppt_system.generation.design_grammar import build_layout_family_options
from ppt_system.generation.text_layout import build_layout_slots_by_family
from ppt_system.generation.layout_geometry import build_layout_preview, get_layout_category
from ppt_system.generation.reference_style_adherence import (
    REFERENCE_STYLE_ADHERENCE_LABELS,
    REFERENCE_STYLE_ADHERENCE_LEVELS,
)
from ppt_system.jobs.db_maintenance_scheduler import resolve_job_db_maintenance_config
from ppt_system.runtime import runtime_context
from ppt_system.web.services.api_response import api_error, api_ok
from ppt_system.web.services.app_config_runtime import read_config


def api_config():
    config = read_config()
    defaults = default_generation_options(config)
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
            "page_richness_options": list(PAGE_RICHNESS_LEVELS),
            "layout_family_options": _build_layout_family_options_with_slots(),
            "default_reference_style_adherence": str(defaults["reference_style_adherence"]),
            "reference_style_adherence_options": [
                {"value": value, "label": REFERENCE_STYLE_ADHERENCE_LABELS[value]}
                for value in REFERENCE_STYLE_ADHERENCE_LEVELS
            ],
            "job_db_maintenance": resolve_job_db_maintenance_config(config),
            "active_chat_config_id": config.get("active_chat_config_id", ""),
            "active_image_config_id": config.get("active_image_config_id", ""),
        }
    )


def _build_layout_family_options_with_slots() -> list[dict]:
    """让前端缩略图与实际文字排版共用同一套槽位坐标。"""
    options = build_layout_family_options()
    for option in options:
        slots = build_layout_slots_by_family(option["value"], 1000, 562, "medium")
        option["preview_slots"] = [
            {"name": name, "left": box[0], "top": box[1], "width": box[2], "height": box[3]}
            for name, box in slots.get("slot_coords", {}).items()
        ]
        option["preview_shapes"] = build_layout_preview(option["value"])
        option["category"] = get_layout_category(option["value"])
    return options


def api_model_configs():
    config = read_config()
    return jsonify(
        {
            "active_chat_config_id": config.get("active_chat_config_id", ""),
            "active_image_config_id": config.get("active_image_config_id", ""),
            "configs": list_model_configs(config),
        }
    )


def api_create_model_config(model_type: str):
    config = read_config()
    try:
        item = upsert_model_config(config, model_type, request.get_json(force=True))
        save_model_env_fields(runtime_context.ENV_PATH, model_type, item)
        write_config(runtime_context.CONFIG_PATH, config, local_path=runtime_context.LOCAL_CONFIG_PATH)
    except ValueError as exc:
        return api_error(exc)
    return jsonify(list_model_configs(config)[model_type][-1])


def api_update_model_config(model_type: str, config_id: str):
    config = read_config()
    try:
        upsert_model_config(config, model_type, request.get_json(force=True), config_id=config_id)
        item = next(
            candidate
            for candidate in list_model_configs(config)[model_type]
            if candidate.get("id") == config_id
        )
        save_model_env_fields(runtime_context.ENV_PATH, model_type, item)
        write_config(runtime_context.CONFIG_PATH, config, local_path=runtime_context.LOCAL_CONFIG_PATH)
        return jsonify(item)
    except ValueError as exc:
        return api_error(exc)
    except StopIteration:
        return api_error("保存后未找到配置。", 500)


def api_delete_model_config(model_type: str, config_id: str):
    config = read_config()
    try:
        removed = delete_model_config(config, model_type, config_id)
        delete_model_env_fields(runtime_context.ENV_PATH, model_type, removed)
        write_config(runtime_context.CONFIG_PATH, config, local_path=runtime_context.LOCAL_CONFIG_PATH)
    except ValueError as exc:
        return api_error(exc)
    return api_ok()


def api_activate_model_config(model_type: str, config_id: str):
    config = read_config()
    try:
        set_active_model_config(config, model_type, config_id)
        write_config(runtime_context.CONFIG_PATH, config, local_path=runtime_context.LOCAL_CONFIG_PATH)
    except ValueError as exc:
        return api_error(exc)
    return api_ok()


def api_test_model_config(model_type: str):
    config = read_config()
    payload = request.get_json(force=True) or {}
    try:
        profile = build_connectivity_profile(config, model_type, payload)
        timeout = int(config.get("connectivity_test_timeout_seconds", 20))
        result = test_model_connectivity(model_type, profile, timeout=timeout)
    except ValueError as exc:
        return api_error(exc, ok=False)
    return jsonify(result.to_dict()), (200 if result.ok else 400)


def build_connectivity_profile(config: dict, model_type: str, payload: dict) -> dict:
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
