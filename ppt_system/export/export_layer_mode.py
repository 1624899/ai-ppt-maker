from __future__ import annotations

from dataclasses import dataclass
from typing import Any


OVERLAY_LAYER_MODE = "overlay"
SEPARATE_LAYER_MODE = "separate_slides"


@dataclass(frozen=True)
class SlideLayerSpec:
    layer_key: str
    include_assets: bool
    include_text: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "layer_key": self.layer_key,
            "include_assets": bool(self.include_assets),
            "include_text": bool(self.include_text),
        }


def normalize_layer_mode(value: Any, default: str = OVERLAY_LAYER_MODE) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == OVERLAY_LAYER_MODE:
        return OVERLAY_LAYER_MODE
    if normalized == SEPARATE_LAYER_MODE:
        return SEPARATE_LAYER_MODE
    return str(default or OVERLAY_LAYER_MODE)


def build_slide_layer_specs(layer_mode: Any) -> list[SlideLayerSpec]:
    resolved_mode = normalize_layer_mode(layer_mode)
    if resolved_mode == SEPARATE_LAYER_MODE:
        return [
            SlideLayerSpec(layer_key="assets", include_assets=True, include_text=False),
            SlideLayerSpec(layer_key="texts", include_assets=False, include_text=True),
        ]
    return [
        SlideLayerSpec(layer_key="overlay", include_assets=True, include_text=True),
    ]


def count_output_slides(logical_page_count: int, layer_mode: Any) -> int:
    safe_page_count = max(0, int(logical_page_count))
    return safe_page_count * len(build_slide_layer_specs(layer_mode))
