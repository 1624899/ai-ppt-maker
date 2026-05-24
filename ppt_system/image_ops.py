from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

from ppt_system.background_removal import remove_background


@dataclass(frozen=True)
class TransparentImageResult:
    output_path: Path
    strategy: str
    warning: str | None = None


def enhance_image(input_path: Path, output_path: Path) -> Path:
    image = Image.open(input_path).convert("RGBA")

    # 轻量锐化和对比度增强，尽量保留透明边界，不做会破坏 alpha 的重采样。
    rgb = image.convert("RGB")
    rgb = ImageEnhance.Contrast(rgb).enhance(1.12)
    rgb = ImageEnhance.Sharpness(rgb).enhance(1.35)
    rgb = rgb.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=3))
    enhanced = Image.merge("RGBA", (*rgb.split(), image.getchannel("A")))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    enhanced.save(output_path)
    return output_path


def make_transparent(
    input_path: Path,
    output_path: Path,
    fallback_bg_threshold: int = 245,
) -> TransparentImageResult:
    image = Image.open(input_path).convert("RGBA")
    result = remove_background(image, fallback_bg_threshold=fallback_bg_threshold)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.image.save(output_path)
    return TransparentImageResult(
        output_path=output_path,
        strategy=result.strategy,
        warning=result.warning,
    )
