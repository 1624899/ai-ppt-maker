from __future__ import annotations

from typing import Any


def find_contextually_decorative_indices(
    components: list[dict[str, Any]],
    *,
    image_width: int,
    image_height: int,
) -> set[int]:
    marked: set[int] = set()
    image_area = max(1, int(image_width) * int(image_height))
    enclosed_tiny_area_threshold = max(80, int(image_area * 0.000035))
    enclosed_hairline_area_threshold = max(180, int(image_area * 0.00008))
    enclosed_skinny_area_threshold = max(96, int(image_area * 0.000045))

    for index, component in enumerate(components):
        if bool(component.get("contains_anchor", False)):
            continue
        container = _find_enclosing_container(index, components)
        if container is None:
            continue

        width = _component_width(component)
        height = _component_height(component)
        area = int(component["area"])
        density = area / max(1, width * height)
        hairline = min(width, height) <= 2
        slender = max(width, height) / max(1, min(width, height)) >= 4.0
        compact = max(width, height) <= 24
        component_count = max(1, int(component.get("component_count", 1)))
        container_area = max(1, int(container["area"]))
        area_ratio = area / container_area

        # 被更大主体完整包住的超细线，通常是边框断裂、描边残片或内部抠图毛刺。
        if component_count == 1 and hairline and area <= enclosed_hairline_area_threshold:
            marked.add(index)
            continue

        # 被更紧主体包住的超小块，通常只是高光、阴影或边角毛刺，不值得单独导出。
        if (
            component_count == 1
            and compact
            and area <= enclosed_tiny_area_threshold
            and max(width, height) <= 14
            and area_ratio <= 0.08
        ):
            marked.add(index)
            continue

        # 靠主体边缘的细长内嵌残条，通常来自描边断裂或抠图残留，保留价值很低。
        if component_count == 1 and _is_edge_attached_inner_strip(component, container):
            marked.add(index)
            continue

        # 很瘦长且面积很小的内嵌残片，通常只是断开的描边，不值得单独保留成资产。
        if component_count == 1 and slender and min(width, height) <= 5 and area <= enclosed_skinny_area_threshold:
            marked.add(index)

    return marked


def _find_enclosing_container(
    target_index: int,
    components: list[dict[str, Any]],
) -> dict[str, Any] | None:
    target = components[target_index]
    best_container: dict[str, Any] | None = None
    best_area: int | None = None
    target_area = max(1, int(target["area"]))

    for index, candidate in enumerate(components):
        if index == target_index:
            continue
        candidate_area = int(candidate["area"])
        if candidate_area < target_area * 8:
            continue
        if not _fully_contains(candidate, target):
            continue
        # 这里优先选择“最紧”的包围主体，而不是整页大框。
        # 装饰碎片通常依附在最近的语义主体边缘，拿大框做上下文会把尺度关系放大失真。
        if best_area is None or candidate_area < best_area:
            best_container = candidate
            best_area = candidate_area
    return best_container


def _is_edge_attached_inner_strip(
    component: dict[str, Any],
    container: dict[str, Any],
) -> bool:
    width = _component_width(component)
    height = _component_height(component)
    short_side = min(width, height)
    long_side = max(width, height)
    if short_side > 8 or long_side < short_side * 6:
        return False

    container_width = _component_width(container)
    container_height = _component_height(container)
    container_area = max(1, int(container["area"]))
    area_ratio = int(component["area"]) / container_area
    if area_ratio > 0.1:
        return False

    if height >= width:
        span_ratio = height / max(1, container_height)
    else:
        span_ratio = width / max(1, container_width)
    if span_ratio > 0.75:
        return False

    insets = _component_insets_within_container(container, component)
    edge_margin = max(6, min(container_width, container_height) // 12)
    return min(insets) <= edge_margin


def _fully_contains(container: dict[str, Any], component: dict[str, Any]) -> bool:
    return (
        int(component["left"]) >= int(container["left"])
        and int(component["top"]) >= int(container["top"])
        and int(component["right"]) <= int(container["right"])
        and int(component["bottom"]) <= int(container["bottom"])
    )


def _component_width(component: dict[str, Any]) -> int:
    return max(1, int(component["right"]) - int(component["left"]))


def _component_height(component: dict[str, Any]) -> int:
    return max(1, int(component["bottom"]) - int(component["top"]))


def _component_insets_within_container(
    container: dict[str, Any],
    component: dict[str, Any],
) -> tuple[int, int, int, int]:
    return (
        int(component["left"]) - int(container["left"]),
        int(component["top"]) - int(container["top"]),
        int(container["right"]) - int(component["right"]),
        int(container["bottom"]) - int(component["bottom"]),
    )
