from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass(frozen=True)
class ImageAlphaProfile:
    min_alpha: int
    max_alpha: int

    @property
    def has_transparency(self) -> bool:
        return int(self.min_alpha) < 255

    @property
    def has_visible_pixels(self) -> bool:
        return int(self.max_alpha) > 0


def inspect_image_alpha(image_path: Path) -> ImageAlphaProfile:
    """读取图片 alpha 分布，帮助上层决定是否复用现成透明图。"""
    with Image.open(image_path) as source_image:
        alpha = source_image.convert("RGBA").getchannel("A")
        min_alpha, max_alpha = alpha.getextrema()
    return ImageAlphaProfile(
        min_alpha=int(min_alpha),
        max_alpha=int(max_alpha),
    )
