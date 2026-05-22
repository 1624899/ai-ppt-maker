from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter


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


def make_transparent(input_path: Path, output_path: Path, fallback_bg_threshold: int = 245) -> Path:
    image = Image.open(input_path).convert("RGBA")
    alpha = image.getchannel("A")
    if alpha.getextrema()[0] < 255:
        image.save(output_path)
        return output_path

    try:
        from rembg import remove
    except ImportError:
        data = image.load()
        for y in range(image.height):
            for x in range(image.width):
                r, g, b, a = data[x, y]
                if r >= fallback_bg_threshold and g >= fallback_bg_threshold and b >= fallback_bg_threshold:
                    data[x, y] = (r, g, b, 0)
        image.save(output_path)
        return output_path

    removed = remove(image)
    removed.save(output_path)
    return output_path

