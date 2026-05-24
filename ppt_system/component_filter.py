from __future__ import annotations

from typing import Any


def filter_decorative_components(
    components: list[dict[str, Any]],
    *,
    image_width: int,
    image_height: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    for component in components:
        if _should_drop_component(
            component,
            image_width=image_width,
            image_height=image_height,
        ):
            removed.append(component)
        else:
            kept.append(component)
    return kept, removed


def _should_drop_component(
    component: dict[str, Any],
    *,
    image_width: int,
    image_height: int,
) -> bool:
    left = int(component["left"])
    top = int(component["top"])
    right = int(component["right"])
    bottom = int(component["bottom"])
    width = max(1, right - left)
    height = max(1, bottom - top)
    area = int(component["area"])
    density = area / max(1, width * height)

    min_side = min(image_width, image_height)
    image_area = max(1, image_width * image_height)
    near_edge_margin = max(12, int(min_side * 0.015))
    tiny_area_threshold = max(36, int(image_area * 0.000015))
    small_area_threshold = max(96, int(image_area * 0.00004))
    sparse_strip_area_threshold = max(120, int(image_area * 0.00018))

    near_edge = (
        left <= near_edge_margin
        or top <= near_edge_margin
        or right >= image_width - near_edge_margin
        or bottom >= image_height - near_edge_margin
    )
    touches_edge = (
        left <= 1
        or top <= 1
        or right >= image_width - 1
        or bottom >= image_height - 1
    )
    hairline = min(width, height) <= 2
    compact = max(width, height) <= near_edge_margin * 2
    slender = max(width, height) / max(1, min(width, height)) >= 4.0

    # 贴边的超细线和稀疏小残片，大多来自背景装饰或抠图残留，保留价值很低。
    if touches_edge and area <= small_area_threshold and (hairline or density <= 0.18 or compact):
        return True

    # 靠边的极小碎片通常不是可编辑主体，优先清理，避免 PPT 对象数继续膨胀。
    if near_edge and compact and area <= max(24, tiny_area_threshold // 2):
        return True
    if near_edge and hairline and area <= small_area_threshold // 2:
        return True
    if near_edge and area <= tiny_area_threshold and density <= 0.08:
        return True

    # 贴边的稀疏长条残片通常依附在大底板或边框附近，本身很难作为独立元素复用。
    if (
        near_edge
        and area <= sparse_strip_area_threshold
        and density <= 0.045
        and (touches_edge or slender)
    ):
        return True

    return False
