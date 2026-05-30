from __future__ import annotations

from typing import Any

import numpy as np


def component_bbox(component: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        int(component["left"]),
        int(component["top"]),
        int(component["right"]),
        int(component["bottom"]),
    )


def merge_bbox(
    first: tuple[int, int, int, int],
    second: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    return (
        min(first[0], second[0]),
        min(first[1], second[1]),
        max(first[2], second[2]),
        max(first[3], second[3]),
    )


def bbox_gap(
    first: dict[str, Any],
    second: dict[str, Any],
) -> tuple[int, int]:
    return bbox_gap_from_bbox(component_bbox(first), component_bbox(second))


def bbox_gap_from_bbox(
    first: tuple[int, int, int, int],
    second: tuple[int, int, int, int],
) -> tuple[int, int]:
    left_gap = max(0, first[0] - second[2], second[0] - first[2])
    top_gap = max(0, first[1] - second[3], second[1] - first[3])
    return left_gap, top_gap


def bbox_gap_distance(
    first: tuple[int, int, int, int],
    second: tuple[int, int, int, int],
) -> float:
    dx = max(0, max(first[0], second[0]) - min(first[2], second[2]))
    dy = max(0, max(first[1], second[1]) - min(first[3], second[3]))
    return float(np.hypot(dx, dy))


def bbox_center_x(component: dict[str, Any]) -> float:
    return (int(component["left"]) + int(component["right"])) / 2.0


def bbox_center_y(component: dict[str, Any]) -> float:
    return (int(component["top"]) + int(component["bottom"])) / 2.0


def component_long_side(component: dict[str, Any]) -> int:
    return max(
        int(component["right"]) - int(component["left"]),
        int(component["bottom"]) - int(component["top"]),
    )
