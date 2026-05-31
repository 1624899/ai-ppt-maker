from __future__ import annotations

from typing import Any, Mapping

from ppt_system.generation.page_richness import (
    DEFAULT_PAGE_RICHNESS,
    normalize_page_richness_level,
    normalize_page_richness_map,
)
from ppt_system.generation.reference_style_adherence import normalize_reference_style_adherence


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off", ""}


def parse_bool_option(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)

    normalized = str(value).strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    return default


def default_generation_options(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    return {
        "include_cover_page": parse_bool_option(config.get("default_include_cover_page"), True),
        "page_richness_default": normalize_page_richness_level(
            config.get("default_page_richness"),
            DEFAULT_PAGE_RICHNESS,
        ),
        "reference_style_adherence": normalize_reference_style_adherence(
            config.get("default_reference_style_adherence"),
            "balanced",
        ),
        "page_richness_map": {},
    }


def resolve_generation_options(
    payload: Mapping[str, Any] | None = None,
    *,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    defaults = default_generation_options(config)
    payload = payload or {}
    raw_richness_map = payload.get("page_richness_map", {})
    if not raw_richness_map and hasattr(payload, "items"):
        raw_richness_map = {}
        for key, value in payload.items():
            key_text = str(key).strip()
            if not key_text.startswith("page_richness_"):
                continue
            suffix = key_text[len("page_richness_") :]
            if suffix == "default" or not suffix:
                continue
            raw_richness_map[suffix] = value
    return {
        "include_cover_page": parse_bool_option(
            payload.get("include_cover_page"),
            bool(defaults["include_cover_page"]),
        ),
        "page_richness_default": normalize_page_richness_level(
            payload.get("page_richness_default"),
            str(defaults["page_richness_default"]),
        ),
        "page_richness_map": normalize_page_richness_map(
            raw_richness_map,
            page_count=int(payload.get("page_count") or 0),
            default_level=str(defaults["page_richness_default"]),
        ),
        "reference_style_adherence": normalize_reference_style_adherence(
            payload.get("reference_style_adherence"),
            str(defaults["reference_style_adherence"]),
        ),
    }
