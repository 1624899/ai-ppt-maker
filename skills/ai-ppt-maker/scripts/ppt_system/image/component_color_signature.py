from __future__ import annotations

from typing import Any

import numpy as np


def annotate_component_color_signatures(
    components: list[dict[str, Any]],
    *,
    image_array: np.ndarray,
) -> list[dict[str, Any]]:
    return [
        enrich_component_with_color_signature(component, image_array=image_array)
        for component in components
    ]


def enrich_component_with_color_signature(
    component: dict[str, Any],
    *,
    image_array: np.ndarray,
) -> dict[str, Any]:
    enriched = dict(component)
    signature = estimate_component_color_signature(component, image_array=image_array)
    enriched.update(signature)
    return enriched


def estimate_component_color_signature(
    component: dict[str, Any],
    *,
    image_array: np.ndarray,
) -> dict[str, Any]:
    left = int(component["left"])
    top = int(component["top"])
    right = int(component["right"])
    bottom = int(component["bottom"])
    crop = np.asarray(image_array[top:bottom, left:right], dtype=np.uint8)
    component_mask = np.asarray(component["mask"], dtype=bool)
    opaque_mask = component_mask & (crop[..., 3] > 0)
    pixels = crop[opaque_mask][:, :3]
    if pixels.size == 0:
        return {
            "dominant_color": (255, 255, 255),
            "mean_color": (255, 255, 255),
            "average_saturation": 0.0,
            "average_brightness": 255.0,
            "light_pixel_ratio": 1.0,
            "low_saturation_pixel_ratio": 1.0,
        }

    dominant_color = _estimate_dominant_color(pixels)
    mean_color = pixels.mean(axis=0)
    saturation = pixels.max(axis=1).astype(np.float32) - pixels.min(axis=1).astype(np.float32)
    brightness = pixels.mean(axis=1).astype(np.float32)
    return {
        "dominant_color": dominant_color,
        "mean_color": (
            int(round(float(mean_color[0]))),
            int(round(float(mean_color[1]))),
            int(round(float(mean_color[2]))),
        ),
        "average_saturation": float(saturation.mean()),
        "average_brightness": float(brightness.mean()),
        "light_pixel_ratio": float(np.mean(brightness >= 200.0)),
        "low_saturation_pixel_ratio": float(np.mean(saturation <= 60.0)),
        "vivid_pixel_ratio": float(np.mean((saturation >= 120.0) & (brightness <= 220.0))),
        "dominant_color_saturation": float(
            max(int(dominant_color[0]), int(dominant_color[1]), int(dominant_color[2]))
            - min(int(dominant_color[0]), int(dominant_color[1]), int(dominant_color[2]))
        ),
        "dominant_color_brightness": float(
            (
                int(dominant_color[0])
                + int(dominant_color[1])
                + int(dominant_color[2])
            )
            / 3.0
        ),
    }


def _estimate_dominant_color(pixels: np.ndarray) -> tuple[int, int, int]:
    quantized = (pixels // 16).astype(np.int16)
    packed = (
        (quantized[:, 0] << 8)
        | (quantized[:, 1] << 4)
        | quantized[:, 2]
    )
    _, inverse = np.unique(packed, return_inverse=True)
    counts = np.bincount(inverse)
    dominant_index = int(np.argmax(counts))
    dominant_pixels = pixels[inverse == dominant_index]
    dominant_color = dominant_pixels.mean(axis=0)
    return (
        int(round(float(dominant_color[0]))),
        int(round(float(dominant_color[1]))),
        int(round(float(dominant_color[2]))),
    )
