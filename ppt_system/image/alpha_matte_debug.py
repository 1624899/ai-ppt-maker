from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from ppt_system.image.alpha_matte_refinement import estimate_background_model
from ppt_system.image.white_axis_cutout import build_white_axis_cutout


@dataclass(frozen=True)
class AlphaMatteDebugStep:
    name: str
    rgba: np.ndarray


def export_alpha_matte_debug_steps(
    source_path: Path,
    output_dir: Path,
    *,
    fallback_bg_threshold: int = 245,
) -> list[Path]:
    source_rgba = np.array(Image.open(source_path).convert("RGBA"), dtype=np.uint8)
    background = estimate_background_model(
        source_rgba,
        fallback_bg_threshold=fallback_bg_threshold,
    )
    artifacts = build_white_axis_cutout(
        source_rgba,
        background_color=background.color,
        background_tolerance=background.tolerance,
        background_cast_tolerance=background.color_cast_tolerance,
    )
    steps = [
        _make_debug_step("01_source", source_rgba),
        _make_mask_step("02_visual_white_mask", source_rgba[:, :, :3], artifacts.visual_white_mask),
        _make_mask_step("03_seed_mask", source_rgba[:, :, :3], artifacts.seed_mask),
        _make_mask_step("04_candidate_mask", source_rgba[:, :, :3], artifacts.candidate_mask),
        _make_mask_step("05_connected_foreground", source_rgba[:, :, :3], artifacts.connected_mask),
        _make_debug_step("06_raw_alpha", source_rgba[:, :, :3], artifacts.raw_alpha),
        _make_debug_step("07_final_alpha", source_rgba[:, :, :3], artifacts.final_alpha),
        _make_debug_step("08_cutout", artifacts.rgba),
    ]

    output_dir.mkdir(parents=True, exist_ok=True)
    written_paths: list[Path] = []
    for index, step in enumerate(steps, start=1):
        output_path = output_dir / f"{index:02d}_{step.name}.png"
        Image.fromarray(step.rgba, mode="RGBA").save(output_path)
        written_paths.append(output_path)
    return written_paths


def _make_debug_step(name: str, rgb_or_rgba: np.ndarray, alpha: np.ndarray | None = None) -> AlphaMatteDebugStep:
    if alpha is None:
        rgba = np.asarray(rgb_or_rgba, dtype=np.uint8)
        if rgba.ndim != 3 or rgba.shape[2] != 4:
            raise ValueError("调试步骤需要 RGBA 图像。")
        return AlphaMatteDebugStep(name=name, rgba=rgba)

    rgb = np.asarray(rgb_or_rgba, dtype=np.uint8)
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("调试步骤需要 RGB 图像。")
    rgba = np.zeros((rgb.shape[0], rgb.shape[1], 4), dtype=np.uint8)
    rgba[:, :, :3] = rgb
    rgba[:, :, 3] = np.asarray(alpha, dtype=np.uint8)
    return AlphaMatteDebugStep(name=name, rgba=rgba)


def _make_mask_step(name: str, rgb: np.ndarray, mask: np.ndarray) -> AlphaMatteDebugStep:
    alpha = np.where(np.asarray(mask, dtype=bool), 255, 0).astype(np.uint8)
    return _make_debug_step(name, rgb, alpha)
