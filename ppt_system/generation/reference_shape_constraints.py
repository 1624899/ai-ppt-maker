from __future__ import annotations

from typing import Any


def build_shape_clarity_prompt_lines(
    style_guide: dict[str, Any] | None = None,
    *,
    detail: str = "compact",
) -> list[str]:
    style_guide = style_guide or {}
    normalized_detail = str(detail).strip().lower() or "compact"
    dashed_allowed = _style_prefers_dashed_connectors(style_guide)

    lines = [
        "切分底线：先服从参考版式和内容语义，不因切分新增卡片、容器或描边；已出现的主体、图标、标签等边界清楚，避免糊边、弱阴影、发光粘背景。",
        _build_connector_constraint(dashed_allowed),
        "元素底线：可保留透明、渐变、柔和质感；元素外沿不融入背景，相邻元素留可识别间隔，便于后续抠图和切分。",
        "风格平衡：不要因切分要求统一卡片化、加厚边框或增加模板化装饰。",
    ]
    if normalized_detail == "full":
        return lines
    return lines[:3]


def _build_connector_constraint(dashed_allowed: bool) -> str:
    if dashed_allowed:
        return (
            "连接线底线：参考风格含虚线时可保留；线段间距均匀，关键箭头与连接关系清楚。"
        )
    return (
        "连接线底线：不要主动增加虚线装饰；确需连接线时，线段、箭头和起止关系清楚。"
    )


def _style_prefers_dashed_connectors(style_guide: dict[str, Any]) -> bool:
    style_core = style_guide.get("style_core", {})
    line_style = ""
    if isinstance(style_core, dict):
        line_style = str(style_core.get("line_style", "")).strip()

    candidates = [
        line_style,
        str(style_guide.get("prompt_anchor", "")).strip(),
        " ".join(_normalize_text_list(style_guide.get("element_primitives", []))),
    ]
    for text in candidates:
        lowered = text.lower()
        if "虚线" in text or "dashed" in lowered or "dash" in lowered:
            return True
    return False


def _normalize_text_list(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [str(item).strip() for item in items if str(item).strip()]
