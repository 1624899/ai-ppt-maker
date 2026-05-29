from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from ppt_system.alpha_fill_region_cleanup import (
    analyze_fill_regions,
    clean_fill_region_boundary_fringe,
    protect_fill_region_alpha,
    purify_fill_region_artifacts,
)
from ppt_system.alpha_matte_refinement import (
    BackgroundModel,
    _bridge_narrow_gaps,
    _clean_bright_outline_residue,
    _color_cast_distance,
    _color_distance,
    _decontaminate_edge_colors,
    _dilate_mask,
    _grow_from_seeds,
    _promote_supported_soft_edges,
    _sharpen_supported_edge_detail,
    _smooth_transition_alpha,
    _suppress_weak_white_fringe,
    _tighten_background_like_edge_alpha,
    build_color_guided_alpha,
    estimate_background_model,
)


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
    steps = _build_debug_steps(
        source_rgba=source_rgba,
        background=background,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    written_paths: list[Path] = []
    for index, step in enumerate(steps, start=1):
        output_path = output_dir / f"{index:02d}_{step.name}.png"
        Image.fromarray(step.rgba, mode="RGBA").save(output_path)
        written_paths.append(output_path)
    return written_paths


def _build_debug_steps(
    *,
    source_rgba: np.ndarray,
    background: BackgroundModel,
) -> list[AlphaMatteDebugStep]:
    steps: list[AlphaMatteDebugStep] = []
    guided_alpha = build_color_guided_alpha(source_rgba, background=background)
    steps.append(_make_debug_step("01_guided_alpha", source_rgba[:, :, :3], guided_alpha))

    rgb = source_rgba[:, :, :3].astype(np.int16)
    color_distance = _color_distance(rgb, background.color)
    color_cast_distance = _color_cast_distance(rgb, background.color)

    near_background_fill = (
        (color_distance <= background.tolerance + 10)
        & (color_cast_distance <= background.color_cast_tolerance + 2)
    )
    strong_colored_foreground = (
        (color_distance >= background.tolerance + max(18, background.tolerance // 3))
        | (color_cast_distance >= background.color_cast_tolerance + 4)
    )
    supported_light_edge = near_background_fill & _dilate_mask(strong_colored_foreground, steps=1)
    removable_light_fill = near_background_fill & (~supported_light_edge)
    initial_alpha_for_refine = np.where(removable_light_fill, 0, guided_alpha).astype(np.uint8)

    base_alpha = np.where(
        initial_alpha_for_refine > 0,
        initial_alpha_for_refine,
        np.where(~near_background_fill, guided_alpha, 0),
    ).astype(np.uint8)
    steps.append(_make_debug_step("02_base_alpha", source_rgba[:, :, :3], base_alpha))

    strong_foreground = (
        (base_alpha >= 200)
        | (color_distance >= background.tolerance + max(18, background.tolerance // 3))
    )
    candidate_foreground = (
        (base_alpha >= 10)
        | (color_distance >= max(8, background.tolerance - 8))
        | (color_cast_distance >= background.color_cast_tolerance + 2)
    )
    connected_foreground = _grow_from_seeds(
        candidate_mask=candidate_foreground,
        seed_mask=strong_foreground,
    )
    support_mask = _dilate_mask(connected_foreground, steps=1)
    supported_alpha = np.where(support_mask, base_alpha, 0).astype(np.uint8)
    steps.append(_make_debug_step("03_supported_alpha", source_rgba[:, :, :3], supported_alpha))

    initial_fill_region_analysis = analyze_fill_regions(
        source_rgba[:, :, :3],
        supported_alpha,
        background_color=background.color,
    )
    protected_supported_alpha = protect_fill_region_alpha(
        supported_alpha,
        analysis=initial_fill_region_analysis,
    )
    protected_supported_overlay = _build_fill_region_overlay(
        source_rgba[:, :, :3],
        initial_fill_region_analysis.full_mask,
        initial_fill_region_analysis.core_mask,
    )
    steps.append(_make_debug_step("04_fill_region_protection", protected_supported_overlay, protected_supported_alpha))

    promoted_alpha = _promote_supported_soft_edges(
        alpha=protected_supported_alpha,
        connected_mask=connected_foreground,
        color_distance=color_distance,
        tolerance=background.tolerance,
    )
    steps.append(_make_debug_step("05_promoted_alpha", source_rgba[:, :, :3], promoted_alpha))

    bridged_alpha = _bridge_narrow_gaps(
        alpha=promoted_alpha,
        color_distance=color_distance,
        tolerance=background.tolerance,
    )
    steps.append(_make_debug_step("06_bridged_alpha", source_rgba[:, :, :3], bridged_alpha))

    suppressed_alpha = _suppress_weak_white_fringe(
        alpha=bridged_alpha,
        rgb=rgb,
        background=background,
        protected_mask=initial_fill_region_analysis.core_mask,
    )
    steps.append(_make_debug_step("07_suppress_weak_white_fringe", source_rgba[:, :, :3], suppressed_alpha))

    tightened_alpha = _tighten_background_like_edge_alpha(
        alpha=suppressed_alpha,
        rgb=rgb,
        background=background,
        protected_mask=initial_fill_region_analysis.core_mask,
    )
    steps.append(_make_debug_step("08_tighten_background_like_edge_alpha", source_rgba[:, :, :3], tightened_alpha))

    smoothed_alpha = _smooth_transition_alpha(
        tightened_alpha,
        locked_mask=(tightened_alpha >= 240) | (~support_mask) | initial_fill_region_analysis.full_mask,
        iterations=1,
    )
    steps.append(_make_debug_step("09_smoothed_alpha", source_rgba[:, :, :3], smoothed_alpha))

    fill_region_analysis = analyze_fill_regions(
        source_rgba[:, :, :3],
        smoothed_alpha,
        background_color=background.color,
    )
    protected_smoothed_alpha = protect_fill_region_alpha(
        smoothed_alpha,
        analysis=fill_region_analysis,
    )
    fill_region_overlay = _build_fill_region_overlay(
        source_rgba[:, :, :3],
        fill_region_analysis.full_mask,
        fill_region_analysis.core_mask,
    )
    steps.append(_make_debug_step("10_fill_region_analysis", fill_region_overlay, protected_smoothed_alpha))

    cleaned_rgb, cleaned_alpha = _clean_bright_outline_residue(
        rgb=source_rgba[:, :, :3],
        alpha=protected_smoothed_alpha,
        background=background,
        protected_mask=fill_region_analysis.core_mask,
    )
    steps.append(_make_debug_step("11_clean_bright_outline_residue", cleaned_rgb, cleaned_alpha))

    decontaminated_rgb = _decontaminate_edge_colors(
        cleaned_rgb,
        alpha=cleaned_alpha,
        background=background,
        protected_mask=fill_region_analysis.core_mask,
    )
    steps.append(_make_debug_step("12_decontaminate_edge_colors", decontaminated_rgb, cleaned_alpha))

    sharpened_rgb, sharpened_alpha = _sharpen_supported_edge_detail(
        rgb=decontaminated_rgb,
        alpha=cleaned_alpha,
        background=background,
        protected_mask=fill_region_analysis.core_mask,
    )
    steps.append(_make_debug_step("13_sharpen_supported_edge_detail", sharpened_rgb, sharpened_alpha))
    purified_rgb, purified_alpha = purify_fill_region_artifacts(
        source_rgba[:, :, :3],
        sharpened_rgb,
        sharpened_alpha,
        analysis=fill_region_analysis,
    )
    steps.append(_make_debug_step("14_purify_fill_region_artifacts", purified_rgb, purified_alpha))
    fill_boundary_cleaned_rgb, fill_boundary_cleaned_alpha = clean_fill_region_boundary_fringe(
        purified_rgb,
        purified_alpha,
        analysis=fill_region_analysis,
        background_color=background.color,
    )
    steps.append(
        _make_debug_step(
            "15_clean_fill_region_boundary_fringe",
            fill_boundary_cleaned_rgb,
            fill_boundary_cleaned_alpha,
        )
    )
    steps.append(_make_debug_step("16_final_alpha", fill_boundary_cleaned_rgb, fill_boundary_cleaned_alpha))
    return steps


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


def _build_fill_region_overlay(
    rgb: np.ndarray,
    full_mask: np.ndarray,
    core_mask: np.ndarray,
) -> np.ndarray:
    overlay = np.array(rgb, copy=True)
    full = np.asarray(full_mask, dtype=bool)
    core = np.asarray(core_mask, dtype=bool)
    if np.any(full):
        overlay[full] = np.array([255, 224, 224], dtype=np.uint8)
    if np.any(core):
        overlay[core] = np.array([255, 192, 192], dtype=np.uint8)
    return overlay
