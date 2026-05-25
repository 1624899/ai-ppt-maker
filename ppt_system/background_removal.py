from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

from ppt_system.alpha_matte_refinement import (
    build_color_guided_alpha,
    estimate_background_model,
    refine_background_removed_image,
)
from ppt_system.alpha_artifact_filter import prune_alpha_artifacts

BACKGROUND_REMOVAL_STRATEGY_PRESERVE_ALPHA = "preserve-alpha"
BACKGROUND_REMOVAL_STRATEGY_BUILTIN_ALPHA_REFINE = "builtin-alpha-refine"


@dataclass(frozen=True)
class BackgroundRemovalResult:
    image: Image.Image
    strategy: str
    warning: str | None = None


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
    warning: str,
) -> BackgroundRemovalResult:
    source_rgba = np.array(image.convert("RGBA"), dtype=np.uint8)
    background = estimate_background_model(
        source_rgba,
        fallback_bg_threshold=fallback_bg_threshold,
    )
    guided_alpha = build_color_guided_alpha(
        source_rgba,
        background=background,
    )
    initial_removed = np.array(source_rgba, copy=True)
    initial_removed[:, :, 3] = np.minimum(initial_removed[:, :, 3], guided_alpha)
    refined = refine_background_removed_image(
        image,
        Image.fromarray(initial_removed, mode="RGBA"),
        fallback_bg_threshold=fallback_bg_threshold,
    )
    rgba = prune_alpha_artifacts(np.array(refined, dtype=np.uint8))
    processed = Image.fromarray(rgba, mode="RGBA")
    return BackgroundRemovalResult(
        image=processed,
        strategy=BACKGROUND_REMOVAL_STRATEGY_BUILTIN_ALPHA_REFINE,
        warning=warning,
    )


def _prune_background_artifacts(image: Image.Image) -> Image.Image:
    rgba = np.array(image.convert("RGBA"), dtype=np.uint8)
    cleaned = prune_alpha_artifacts(rgba)
    return Image.fromarray(cleaned, mode="RGBA")
