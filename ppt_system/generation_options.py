from __future__ import annotations

from typing import Any, Mapping


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
    }


def resolve_generation_options(
    payload: Mapping[str, Any] | None = None,
    *,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    defaults = default_generation_options(config)
    payload = payload or {}
    return {
        "include_cover_page": parse_bool_option(
            payload.get("include_cover_page"),
            bool(defaults["include_cover_page"]),
        ),
    }
