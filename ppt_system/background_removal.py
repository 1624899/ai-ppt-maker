from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np
from PIL import Image

from ppt_system.alpha_matte_refinement import (
    refine_background_removed_image,
)

BACKGROUND_REMOVAL_STRATEGY_PRESERVE_ALPHA = "preserve-alpha"
BACKGROUND_REMOVAL_STRATEGY_BUILTIN_ALPHA_REFINE = "builtin-alpha-refine"
BACKGROUND_REMOVAL_STRATEGY = BACKGROUND_REMOVAL_STRATEGY_BUILTIN_ALPHA_REFINE


@dataclass(frozen=True)
class BackgroundRemovalResult:
    image: Image.Image
    strategy: str
    warning: str | None = None


@dataclass(frozen=True)
class _AlphaComponent:
    pixels: list[tuple[int, int]]
    area: int
    width: int
    height: int
    max_alpha: int
    anchor_area: int

    @property
    def bbox_area(self) -> int:
        return max(1, self.width * self.height)

    @property
    def fill_ratio(self) -> float:
        return float(self.area) / float(self.bbox_area)

    @property
    def min_side(self) -> int:
        return min(self.width, self.height)

    @property
    def max_side(self) -> int:
        return max(self.width, self.height)


def remove_background(
    image: Image.Image,
    *,
    fallback_bg_threshold: int = 245,
) -> BackgroundRemovalResult:
    alpha = image.getchannel("A")
    if alpha.getextrema()[0] < 255:
        return BackgroundRemovalResult(
            image=image.copy(),
            strategy=BACKGROUND_REMOVAL_STRATEGY_PRESERVE_ALPHA,
            warning=None,
        )

    return _remove_background_with_threshold(
        image,
        fallback_bg_threshold,
        warning=None,
    )


def _remove_background_with_threshold(
    image: Image.Image,
    fallback_bg_threshold: int,
    *,
    warning: str | None,
) -> BackgroundRemovalResult:
    refined = refine_background_removed_image(
        image,
        image,
        fallback_bg_threshold=fallback_bg_threshold,
    )
    rgba = prune_alpha_artifacts(np.asarray(refined, dtype=np.uint8))
    processed = Image.fromarray(rgba, mode="RGBA")
    return BackgroundRemovalResult(
        image=processed,
        strategy=BACKGROUND_REMOVAL_STRATEGY,
        warning=warning,
    )


def prune_alpha_artifacts(
    rgba: np.ndarray,
    *,
    foreground_threshold: int = 1,
    anchor_threshold: int = 160,
) -> np.ndarray:
    """清理抠图后缺少实心锚点的毛刺和噪点，尽量不影响真实前景。"""
    if rgba.ndim != 3 or rgba.shape[2] != 4:
        return rgba

    result = np.array(rgba, copy=True)
    alpha = result[..., 3]
    if alpha.size == 0:
        return result

    components = _find_alpha_components(
        alpha,
        foreground_threshold=max(0, int(foreground_threshold)),
        anchor_threshold=max(0, int(anchor_threshold)),
    )
    if not components:
        return result

    removed_mask = np.zeros(alpha.shape, dtype=bool)
    for component in components:
        if not _should_remove_component(component):
            continue
        for y, x in component.pixels:
            removed_mask[y, x] = True

    if not removed_mask.any():
        return result

    result[removed_mask, 3] = 0
    return result


def _find_alpha_components(
    alpha: np.ndarray,
    *,
    foreground_threshold: int,
    anchor_threshold: int,
) -> list[_AlphaComponent]:
    mask = np.asarray(alpha, dtype=np.uint8) > foreground_threshold
    height, width = mask.shape
    visited = np.zeros(mask.shape, dtype=bool)
    components: list[_AlphaComponent] = []
    neighbors = (
        (-1, -1),
        (0, -1),
        (1, -1),
        (-1, 0),
        (1, 0),
        (-1, 1),
        (0, 1),
        (1, 1),
    )

    ys, xs = np.nonzero(mask)
    for start_y, start_x in zip(ys.tolist(), xs.tolist()):
        if visited[start_y, start_x]:
            continue
        visited[start_y, start_x] = True
        queue: deque[tuple[int, int]] = deque([(start_y, start_x)])
        pixels: list[tuple[int, int]] = []
        min_x = max_x = int(start_x)
        min_y = max_y = int(start_y)
        max_alpha = int(alpha[start_y, start_x])
        anchor_area = 0

        while queue:
            current_y, current_x = queue.popleft()
            pixels.append((current_y, current_x))
            current_alpha = int(alpha[current_y, current_x])
            max_alpha = max(max_alpha, current_alpha)
            if current_alpha >= anchor_threshold:
                anchor_area += 1
            min_x = min(min_x, current_x)
            max_x = max(max_x, current_x)
            min_y = min(min_y, current_y)
            max_y = max(max_y, current_y)

            for delta_y, delta_x in neighbors:
                next_y = current_y + delta_y
                next_x = current_x + delta_x
                if (
                    0 <= next_y < height
                    and 0 <= next_x < width
                    and mask[next_y, next_x]
                    and not visited[next_y, next_x]
                ):
                    visited[next_y, next_x] = True
                    queue.append((next_y, next_x))

        components.append(
            _AlphaComponent(
                pixels=pixels,
                area=len(pixels),
                width=max_x - min_x + 1,
                height=max_y - min_y + 1,
                max_alpha=max_alpha,
                anchor_area=anchor_area,
            )
        )
    return components


def _should_remove_component(component: _AlphaComponent) -> bool:
    if component.anchor_area > 0:
        return False

    if component.area <= 20 and component.max_side <= 8:
        return True

    if (
        component.area <= 48
        and component.min_side <= 2
        and component.max_side >= 6
    ):
        return True

    if (
        component.area <= 72
        and component.fill_ratio <= 0.3
        and component.max_alpha <= 112
    ):
        return True

    return False
