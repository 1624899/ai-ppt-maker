from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageColor, ImageOps


CANVAS_RESIZE_MODES = {"auto", "stretch", "contain", "cover"}
JPEG_SUFFIXES = {".jpg", ".jpeg"}


@dataclass(frozen=True)
class CanvasNormalizationResult:
    source_width: int
    source_height: int
    target_width: int
    target_height: int
    resize_mode: str
    applied_resize_mode: str
    normalized: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_size": {"width": int(self.source_width), "height": int(self.source_height)},
            "target_size": {"width": int(self.target_width), "height": int(self.target_height)},
            "resize_mode": self.resize_mode,
            "applied_resize_mode": self.applied_resize_mode,
            "normalized": bool(self.normalized),
        }


def normalize_image_canvas(
    source_path: Path,
    output_path: Path,
    *,
    target_width: int,
    target_height: int,
    resize_mode: str = "auto",
    background: str | tuple[int, ...] | None = None,
    flatten: bool = False,
    aspect_tolerance: float = 0.01,
) -> CanvasNormalizationResult:
    """把图片写入固定画布，保证后续坐标系只基于声明尺寸。"""
    resolved_target = _validate_target_size(target_width, target_height)
    resolved_mode = normalize_canvas_resize_mode(resize_mode)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source_path) as raw_image:
        image = raw_image.convert("RGBA")
        source_width, source_height = image.size
        background_rgba = _resolve_background_rgba(image, background)
        applied_mode = _resolve_applied_resize_mode(
            image,
            target_width=resolved_target[0],
            target_height=resolved_target[1],
            resize_mode=resolved_mode,
            aspect_tolerance=aspect_tolerance,
        )
        normalized = _resize_to_canvas(
            image,
            target_width=resolved_target[0],
            target_height=resolved_target[1],
            resize_mode=applied_mode,
            background_rgba=background_rgba,
        )
        _save_normalized_image(normalized, output_path, background_rgba=background_rgba, flatten=flatten)

    return CanvasNormalizationResult(
        source_width=int(source_width),
        source_height=int(source_height),
        target_width=int(resolved_target[0]),
        target_height=int(resolved_target[1]),
        resize_mode=resolved_mode,
        applied_resize_mode=applied_mode,
        normalized=(int(source_width), int(source_height)) != resolved_target,
    )


def ensure_image_canvas_size(
    image_path: Path,
    *,
    target_width: int,
    target_height: int,
    resize_mode: str = "auto",
    background: str | tuple[int, ...] | None = None,
    flatten: bool = False,
    aspect_tolerance: float = 0.01,
) -> CanvasNormalizationResult:
    """原地确保图片画布尺寸一致；尺寸已匹配且不需压平时不重写文件。"""
    resolved_target = _validate_target_size(target_width, target_height)
    resolved_mode = normalize_canvas_resize_mode(resize_mode)
    with Image.open(image_path) as raw_image:
        source_width, source_height = raw_image.size

    if (int(source_width), int(source_height)) == resolved_target and not flatten:
        return CanvasNormalizationResult(
            source_width=int(source_width),
            source_height=int(source_height),
            target_width=int(resolved_target[0]),
            target_height=int(resolved_target[1]),
            resize_mode=resolved_mode,
            applied_resize_mode="unchanged",
            normalized=False,
        )

    return normalize_image_canvas(
        image_path,
        image_path,
        target_width=resolved_target[0],
        target_height=resolved_target[1],
        resize_mode=resolved_mode,
        background=background,
        flatten=flatten,
        aspect_tolerance=aspect_tolerance,
    )


def normalize_canvas_resize_mode(value: Any, *, default: str = "auto") -> str:
    mode = str(value or default).strip().lower()
    if mode not in CANVAS_RESIZE_MODES:
        raise ValueError(f"图片画布适配方式只能是：{', '.join(sorted(CANVAS_RESIZE_MODES))}")
    return mode


def _validate_target_size(target_width: int, target_height: int) -> tuple[int, int]:
    width = int(target_width)
    height = int(target_height)
    if width <= 0 or height <= 0:
        raise ValueError("目标画布宽高必须大于 0。")
    return width, height


def _resolve_background_rgba(image: Image.Image, background: str | tuple[int, ...] | None) -> tuple[int, int, int, int]:
    if background is not None:
        if isinstance(background, tuple):
            values = tuple(int(channel) for channel in background)
            if len(values) == 3:
                return values[0], values[1], values[2], 255
            if len(values) == 4:
                return values[0], values[1], values[2], values[3]
            raise ValueError("背景色元组必须包含 3 或 4 个通道。")
        return ImageColor.getcolor(str(background), "RGBA")

    min_alpha, _max_alpha = image.getchannel("A").getextrema()
    if int(min_alpha) < 255:
        return 255, 255, 255, 0
    return 255, 255, 255, 255


def _resolve_applied_resize_mode(
    image: Image.Image,
    *,
    target_width: int,
    target_height: int,
    resize_mode: str,
    aspect_tolerance: float,
) -> str:
    if resize_mode != "auto":
        return resize_mode
    source_width, source_height = image.size
    source_ratio = float(source_width) / max(1.0, float(source_height))
    target_ratio = float(target_width) / max(1.0, float(target_height))
    relative_delta = abs(source_ratio / target_ratio - 1.0)
    return "stretch" if relative_delta <= max(0.0, float(aspect_tolerance)) else "contain"


def _resize_to_canvas(
    image: Image.Image,
    *,
    target_width: int,
    target_height: int,
    resize_mode: str,
    background_rgba: tuple[int, int, int, int],
) -> Image.Image:
    target_size = (int(target_width), int(target_height))
    if resize_mode == "stretch":
        return image.resize(target_size, Image.Resampling.LANCZOS)
    if resize_mode == "cover":
        return ImageOps.fit(image, target_size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    if resize_mode == "contain":
        canvas = Image.new("RGBA", target_size, background_rgba)
        contained = ImageOps.contain(image, target_size, method=Image.Resampling.LANCZOS)
        left = (target_width - contained.width) // 2
        top = (target_height - contained.height) // 2
        canvas.alpha_composite(contained, (left, top))
        return canvas
    raise ValueError(f"不支持的图片画布适配方式：{resize_mode}")


def _save_normalized_image(
    image: Image.Image,
    output_path: Path,
    *,
    background_rgba: tuple[int, int, int, int],
    flatten: bool,
) -> None:
    if flatten or output_path.suffix.lower() in JPEG_SUFFIXES:
        flattened = Image.new("RGBA", image.size, _opaque_background(background_rgba))
        flattened.alpha_composite(image)
        flattened.convert("RGB").save(output_path)
        return
    image.save(output_path)


def _opaque_background(background_rgba: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    red, green, blue, _alpha = background_rgba
    return int(red), int(green), int(blue), 255
