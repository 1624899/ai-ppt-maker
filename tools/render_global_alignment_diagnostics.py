from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ppt_system.global_element_alignment import (
    _build_elements_mask,
    _build_reference_mask,
    _extract_contour_mask,
    _extract_structure_mask,
    _suppress_text_like_regions,
    analyze_global_element_alignment,
    shift_image_content,
)


def _overlay_reference_with_elements(reference: Image.Image, elements: Image.Image, *, alpha: int) -> Image.Image:
    tinted = np.array(elements.convert("RGBA"), dtype=np.uint8)
    mask = tinted[:, :, 3] > 0
    tinted[mask, 0] = 20
    tinted[mask, 1] = 90
    tinted[mask, 2] = 255
    tinted[mask, 3] = int(alpha)
    return Image.alpha_composite(reference.convert("RGBA"), Image.fromarray(tinted, mode="RGBA"))


def _render_mask_diff(reference_mask: np.ndarray, elements_mask: np.ndarray) -> Image.Image:
    canvas = np.full((reference_mask.shape[0], reference_mask.shape[1], 4), 255, dtype=np.uint8)
    only_reference = reference_mask & ~elements_mask
    only_elements = elements_mask & ~reference_mask
    overlap = reference_mask & elements_mask
    canvas[only_reference] = [255, 80, 80, 255]
    canvas[only_elements] = [80, 140, 255, 255]
    canvas[overlap] = [80, 180, 120, 255]
    return Image.fromarray(canvas, mode="RGBA")


def main() -> None:
    project_path = Path(r"output/d6af0cda6c24/project.page05.preview.json")
    output_dir = Path(r"output/page05_global_fit_rerun/diagnostics")
    transparent_path = Path(r"output/page05_global_fit_rerun/work/page_05/page_05_transparent.png")

    project = json.loads(project_path.read_text(encoding="utf-8"))
    page = project["pages"][0]
    reference_path = Path(str(page["reference_image"]))
    text_boxes = [
        (
            int(item.get("left", 0)),
            int(item.get("top", 0)),
            int(item.get("width", 0)),
            int(item.get("height", 0)),
        )
        for item in page.get("texts", [])
        if isinstance(item, dict)
    ]

    decision = analyze_global_element_alignment(
        reference_image=reference_path,
        elements_image=transparent_path,
        text_boxes=text_boxes,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(reference_path).convert("RGBA") as reference:
        with Image.open(transparent_path).convert("RGBA") as elements:
            aligned = shift_image_content(elements, dx=decision.dx, dy=decision.dy) if decision.should_apply else elements.copy()

            _overlay_reference_with_elements(reference, elements, alpha=110).save(output_dir / "overlay_before.png")
            _overlay_reference_with_elements(reference, aligned, alpha=110).save(output_dir / "overlay_after.png")

            reference_mask = _build_reference_mask(reference.convert("RGB"), text_boxes=text_boxes, padding=12, white_threshold=245)
            elements_mask = _build_elements_mask(elements, alpha_threshold=8, white_threshold=245)
            aligned_mask = _build_elements_mask(aligned, alpha_threshold=8, white_threshold=245)
            reference_suppressed = _suppress_text_like_regions(reference_mask)
            reference_contour = _extract_contour_mask(reference_mask)
            reference_suppressed_contour = _extract_contour_mask(reference_suppressed)
            elements_contour = _extract_contour_mask(elements_mask)
            aligned_contour = _extract_contour_mask(aligned_mask)
            reference_structure = _extract_structure_mask(reference_suppressed)
            elements_structure = _extract_structure_mask(elements_mask)
            aligned_structure = _extract_structure_mask(aligned_mask)
            _render_mask_diff(reference_mask, elements_mask).save(output_dir / "mask_before.png")
            _render_mask_diff(reference_mask, aligned_mask).save(output_dir / "mask_after.png")
            _render_mask_diff(reference_contour, elements_contour).save(output_dir / "contour_before.png")
            _render_mask_diff(reference_contour, aligned_contour).save(output_dir / "contour_after.png")
            _render_mask_diff(reference_suppressed_contour, elements_contour).save(output_dir / "suppressed_contour_before.png")
            _render_mask_diff(reference_suppressed_contour, aligned_contour).save(output_dir / "suppressed_contour_after.png")
            _render_mask_diff(reference_structure, elements_structure).save(output_dir / "structure_before.png")
            _render_mask_diff(reference_structure, aligned_structure).save(output_dir / "structure_after.png")

    (output_dir / "alignment_decision.json").write_text(
        json.dumps(
            {
                "should_apply": decision.should_apply,
                "dx": decision.dx,
                "dy": decision.dy,
                "baseline_iou": decision.baseline_iou,
                "shifted_iou": decision.shifted_iou,
                "confidence": decision.confidence,
                "reason": decision.reason,
                "diagnostics": decision.diagnostics,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(output_dir.resolve())


if __name__ == "__main__":
    main()
