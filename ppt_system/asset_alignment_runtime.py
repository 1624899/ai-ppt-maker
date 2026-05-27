from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ppt_system.manifest_paths import resolve_assets_dir_from_manifest


TEXT_BOX_ARG_INDEX: dict[str, tuple[int, int, int, int]] = {
    "add_text": (2, 3, 4, 5),
    "add_center_text": (2, 3, 4, 5),
    "add_runs": (2, 3, 4, 5),
    "add_text_ref": (3, 4, 5, 6),
    "add_center_text_ref": (3, 4, 5, 6),
}


@dataclass(frozen=True)
class AssetAlignmentDecision:
    should_apply: bool
    suggested_adjustments: dict[str, Any]
    dx: int = 0
    dy: int = 0
    baseline_iou: float = 0.0
    shifted_iou: float = 0.0
    confidence: float = 0.0
    reason: str = ""
    diagnostics: dict[str, Any] | None = None


@dataclass(frozen=True)
class TextAssetOverlapReport:
    total_boxes: int
    overlap_box_count: int
    overlap_ratio: float
    max_overlap_pixels: int
    overlapping_box_indices: list[int]


def extract_text_boxes(page_script: str) -> list[tuple[int, int, int, int]]:
    """从 page_script 里提取文字框，用于遮罩参考图中的文本区域。"""
    source = str(page_script or "").strip()
    if not source:
        return []

    tree = ast.parse(source, mode="exec")
    boxes: list[tuple[int, int, int, int]] = []
    for node in tree.body:
        if not isinstance(node, ast.Expr):
            continue
        call = node.value
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
            continue
        arg_index = TEXT_BOX_ARG_INDEX.get(call.func.id)
        if arg_index is None:
            continue
        if len(call.args) <= arg_index[-1]:
            continue
        values: list[int] = []
        try:
            for index in arg_index:
                values.append(_coerce_int(ast.literal_eval(call.args[index])))
        except Exception:
            continue
        left, top, width, height = values
        if width <= 0 or height <= 0:
            continue
        boxes.append((left, top, width, height))
    return boxes


def analyze_text_asset_overlaps(
    *,
    manifest_path: Path,
    page_script: str,
    current_adjustments: dict[str, Any] | None = None,
    box_padding: int = 4,
    min_overlap_pixels: int = 24,
) -> TextAssetOverlapReport:
    """检测当前文字框是否与元素贴图发生明显重叠。"""
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    asset_canvas = _compose_asset_canvas(manifest, current_adjustments or {})
    asset_mask = np.array(asset_canvas.getchannel("A")) > 8
    text_boxes = extract_text_boxes(page_script)
    if not text_boxes:
        return TextAssetOverlapReport(
            total_boxes=0,
            overlap_box_count=0,
            overlap_ratio=0.0,
            max_overlap_pixels=0,
            overlapping_box_indices=[],
        )

    height, width = asset_mask.shape
    overlap_box_count = 0
    max_overlap_pixels = 0
    overlapping_box_indices: list[int] = []
    for index, (left, top, box_width, box_height) in enumerate(text_boxes, start=1):
        x1 = max(0, int(left) - int(box_padding))
        y1 = max(0, int(top) - int(box_padding))
        x2 = min(width, int(left + box_width + box_padding))
        y2 = min(height, int(top + box_height + box_padding))
        if x2 <= x1 or y2 <= y1:
            continue
        overlap_pixels = int(asset_mask[y1:y2, x1:x2].sum())
        max_overlap_pixels = max(max_overlap_pixels, overlap_pixels)
        if overlap_pixels >= int(min_overlap_pixels):
            overlap_box_count += 1
            overlapping_box_indices.append(index)

    total_boxes = len(text_boxes)
    overlap_ratio = overlap_box_count / max(1, total_boxes)
    return TextAssetOverlapReport(
        total_boxes=total_boxes,
        overlap_box_count=overlap_box_count,
        overlap_ratio=overlap_ratio,
        max_overlap_pixels=max_overlap_pixels,
        overlapping_box_indices=overlapping_box_indices,
    )


def analyze_global_asset_alignment(
    *,
    reference_image: Path,
    manifest_path: Path,
    page_script: str,
    current_adjustments: dict[str, Any] | None = None,
    mask_padding: int = 12,
    white_threshold: int = 245,
    min_shift_px: int = 8,
    max_spread_px: int = 48,
    min_iou_gain: float = 0.005,
    max_center_gap: int = 260,
    max_size_gap: float = 0.45,
    min_large_box_pairs: int = 1,
    min_center_reward_gain: float = 0.05,
) -> AssetAlignmentDecision:
    """检测当前页面是否存在稳定的全局元素偏移，只返回全局 dx/dy。"""
    reference = Image.open(reference_image).convert("RGB")
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    text_boxes = extract_text_boxes(page_script)

    reference_mask = _build_reference_visual_mask(
        reference,
        text_boxes=text_boxes,
        padding=mask_padding,
        white_threshold=white_threshold,
    )
    asset_canvas = _compose_asset_canvas(manifest, current_adjustments or {})
    asset_mask = np.array(asset_canvas.getchannel("A")) > 8

    if int(reference_mask.sum()) <= 0 or int(asset_mask.sum()) <= 0:
        return AssetAlignmentDecision(
            should_apply=False,
            suggested_adjustments={},
            reason="empty-mask",
        )

    asset_boxes = _adjusted_manifest_boxes(manifest, current_adjustments or {})
    large_asset_boxes = _select_large_boxes_from_manifest(
        asset_boxes,
        image_width=max(1, int(manifest.get("image_width", 1) or 1)),
        image_height=max(1, int(manifest.get("image_height", 1) or 1)),
    )
    if not large_asset_boxes:
        return AssetAlignmentDecision(
            should_apply=False,
            suggested_adjustments={},
            reason="missing-large-assets",
        )

    large_asset_offsets = _estimate_large_asset_offsets(
        manifest=manifest,
        large_asset_boxes=large_asset_boxes,
        reference_mask=reference_mask,
        search_radius_x=max_center_gap,
        search_radius_y=max_center_gap,
    )
    pair_count = len(large_asset_offsets)
    if pair_count < int(min_large_box_pairs):
        return AssetAlignmentDecision(
            should_apply=False,
            suggested_adjustments={},
            reason="no-large-box-offsets",
        )
    dx_candidates = [item["dx"] for item in large_asset_offsets]
    dy_candidates = [item["dy"] for item in large_asset_offsets]

    dx = int(round(float(np.median(dx_candidates))))
    dy = int(round(float(np.median(dy_candidates))))
    dx_spread = max(abs(value - dx) for value in dx_candidates)
    dy_spread = max(abs(value - dy) for value in dy_candidates)

    baseline_iou = _mask_iou(reference_mask, asset_mask)
    shifted_mask = _shift_mask(asset_mask, dx=dx, dy=dy)
    shifted_iou = _mask_iou(reference_mask, shifted_mask)
    iou_gain = shifted_iou - baseline_iou
    baseline_center_score = _score_text_center_alignment(text_boxes, large_asset_boxes)
    shifted_boxes = _shift_box_list(large_asset_boxes, dx=dx, dy=dy)
    shifted_center_score = _score_text_center_alignment(text_boxes, shifted_boxes)
    center_reward_gain = shifted_center_score - baseline_center_score
    shift_magnitude = max(abs(dx), abs(dy))

    diagnostics = {
        "large_asset_boxes": large_asset_boxes[:12],
        "large_asset_offsets": large_asset_offsets[:12],
        "dx_candidates": dx_candidates,
        "dy_candidates": dy_candidates,
        "pair_count": pair_count,
        "dx_spread": dx_spread,
        "dy_spread": dy_spread,
        "baseline_iou": baseline_iou,
        "shifted_iou": shifted_iou,
        "iou_gain": iou_gain,
        "baseline_center_score": baseline_center_score,
        "shifted_center_score": shifted_center_score,
        "center_reward_gain": center_reward_gain,
    }

    if shift_magnitude < int(min_shift_px):
        return AssetAlignmentDecision(
            should_apply=False,
            suggested_adjustments={},
            dx=dx,
            dy=dy,
            baseline_iou=baseline_iou,
            shifted_iou=shifted_iou,
            confidence=0.0,
            reason="shift-too-small",
            diagnostics=diagnostics,
        )
    if dx_spread > int(max_spread_px) or dy_spread > int(max_spread_px):
        return AssetAlignmentDecision(
            should_apply=False,
            suggested_adjustments={},
            dx=dx,
            dy=dy,
            baseline_iou=baseline_iou,
            shifted_iou=shifted_iou,
            confidence=0.0,
            reason="inconsistent-global-shift",
            diagnostics=diagnostics,
        )
    if iou_gain < float(min_iou_gain):
        if center_reward_gain < float(min_center_reward_gain):
            return AssetAlignmentDecision(
                should_apply=False,
                suggested_adjustments={},
                dx=dx,
                dy=dy,
                baseline_iou=baseline_iou,
                shifted_iou=shifted_iou,
                confidence=max(0.0, iou_gain + center_reward_gain),
                reason="iou-and-center-gain-too-small",
                diagnostics=diagnostics,
            )

    confidence = max(0.0, iou_gain) + max(0.0, center_reward_gain) + min(0.2, shift_magnitude / 500.0)
    return AssetAlignmentDecision(
        should_apply=True,
        suggested_adjustments={"global": {"dx": int(dx), "dy": int(dy)}},
        dx=dx,
        dy=dy,
        baseline_iou=baseline_iou,
        shifted_iou=shifted_iou,
        confidence=confidence,
        reason="apply-global-shift",
        diagnostics=diagnostics,
    )


def _compose_asset_canvas(manifest: dict[str, Any], adjustments: dict[str, Any]) -> Image.Image:
    width = max(1, int(manifest.get("image_width", 1) or 1))
    height = max(1, int(manifest.get("image_height", 1) or 1))
    canvas = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    assets_dir = resolve_assets_dir_from_manifest(manifest)
    normalized_adjustments = _normalize_adjustments(adjustments)
    global_adjustment = dict(normalized_adjustments.get("global", {}))
    asset_map = dict(normalized_adjustments.get("asset_map", {}))

    for asset in manifest.get("assets", []):
        asset_path = assets_dir / str(asset["file"])
        asset_image = Image.open(asset_path).convert("RGBA")
        left = int(asset["left"]) + int(global_adjustment.get("dx", 0))
        top = int(asset["top"]) + int(global_adjustment.get("dy", 0))

        per_asset = dict(asset_map.get(str(int(asset.get("index", 0))), {}))
        left = int(per_asset.get("left", left + int(per_asset.get("dx", 0))))
        top = int(per_asset.get("top", top + int(per_asset.get("dy", 0))))
        canvas.alpha_composite(asset_image, (left, top))
    return canvas


def _adjusted_manifest_boxes(manifest: dict[str, Any], adjustments: dict[str, Any]) -> list[tuple[int, int, int, int, int]]:
    normalized_adjustments = _normalize_adjustments(adjustments)
    global_adjustment = dict(normalized_adjustments.get("global", {}))
    asset_map = dict(normalized_adjustments.get("asset_map", {}))
    boxes: list[tuple[int, int, int, int, int]] = []
    for asset in manifest.get("assets", []):
        left = int(asset["left"]) + int(global_adjustment.get("dx", 0))
        top = int(asset["top"]) + int(global_adjustment.get("dy", 0))
        width = int(asset["width"])
        height = int(asset["height"])
        per_asset = dict(asset_map.get(str(int(asset.get("index", 0))), {}))
        left = int(per_asset.get("left", left + int(per_asset.get("dx", 0))))
        top = int(per_asset.get("top", top + int(per_asset.get("dy", 0))))
        width = int(per_asset.get("width", width + int(per_asset.get("dw", 0))))
        height = int(per_asset.get("height", height + int(per_asset.get("dh", 0))))
        if width <= 0 or height <= 0:
            continue
        area = int(asset.get("area", width * height))
        boxes.append((left, top, left + width, top + height, area))
    return boxes


def _build_reference_visual_mask(
    reference: Image.Image,
    *,
    text_boxes: list[tuple[int, int, int, int]],
    padding: int,
    white_threshold: int,
) -> np.ndarray:
    rgb = np.array(reference.convert("RGB"), dtype=np.uint8)
    mask = np.any(rgb < int(white_threshold), axis=2)
    height, width = mask.shape
    for left, top, box_width, box_height in text_boxes:
        x1 = max(0, int(left) - int(padding))
        y1 = max(0, int(top) - int(padding))
        x2 = min(width, int(left + box_width + padding))
        y2 = min(height, int(top + box_height + padding))
        mask[y1:y2, x1:x2] = False
    return mask


def _mask_bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _select_large_boxes_from_manifest(
    boxes: list[tuple[int, int, int, int, int]],
    *,
    image_width: int,
    image_height: int,
    max_count: int = 8,
) -> list[tuple[int, int, int, int, int]]:
    selected: list[tuple[int, int, int, int, int]] = []
    min_width = max(160, int(image_width * 0.16))
    min_height = max(110, int(image_height * 0.12))
    min_box_area = max(25000, int(image_width * image_height * 0.015))
    for box in boxes:
        left, top, right, bottom, area = box
        width = right - left
        height = bottom - top
        box_area = width * height
        if width < min_width or height < min_height:
            continue
        if box_area < min_box_area:
            continue
        selected.append(box)
    selected.sort(key=lambda item: item[4], reverse=True)
    return selected[:max_count]


def _estimate_large_asset_offsets(
    *,
    manifest: dict[str, Any],
    large_asset_boxes: list[tuple[int, int, int, int, int]],
    reference_mask: np.ndarray,
    search_radius_x: int,
    search_radius_y: int,
) -> list[dict[str, Any]]:
    assets_dir = resolve_assets_dir_from_manifest(manifest)
    indexed_assets = {
        int(asset["index"]): asset
        for asset in manifest.get("assets", [])
        if int(asset.get("index", 0)) > 0
    }
    results: list[dict[str, Any]] = []
    for left, top, right, bottom, area in large_asset_boxes:
        width = right - left
        height = bottom - top
        matched_index = None
        for index, asset in indexed_assets.items():
            if (
                int(asset["left"]) == left
                and int(asset["top"]) == top
                and int(asset["width"]) == width
                and int(asset["height"]) == height
            ):
                matched_index = index
                break
        if matched_index is None:
            continue
        asset_image = Image.open(assets_dir / str(indexed_assets[matched_index]["file"])).convert("RGBA")
        asset_mask = np.array(asset_image.getchannel("A")) > 8
        best = _find_best_asset_offset(
            reference_mask=reference_mask,
            asset_mask=asset_mask,
            left=left,
            top=top,
            search_radius_x=search_radius_x,
            search_radius_y=search_radius_y,
        )
        if best is None:
            continue
        dx, dy, score = best
        results.append(
            {
                "index": matched_index,
                "left": left,
                "top": top,
                "width": width,
                "height": height,
                "dx": dx,
                "dy": dy,
                "score": score,
                "area": area,
            }
        )
    return results


def _find_best_asset_offset(
    *,
    reference_mask: np.ndarray,
    asset_mask: np.ndarray,
    left: int,
    top: int,
    search_radius_x: int,
    search_radius_y: int,
) -> tuple[int, int, float] | None:
    coarse = _search_best_offset(
        reference_mask=reference_mask,
        asset_mask=asset_mask,
        left=left,
        top=top,
        search_radius_x=search_radius_x,
        search_radius_y=search_radius_y,
        step=6,
    )
    if coarse is None:
        return None
    coarse_dx, coarse_dy, _ = coarse
    fine = _search_best_offset(
        reference_mask=reference_mask,
        asset_mask=asset_mask,
        left=left + coarse_dx,
        top=top + coarse_dy,
        search_radius_x=10,
        search_radius_y=10,
        step=1,
    )
    if fine is None:
        return coarse
    fine_dx, fine_dy, fine_score = fine
    return coarse_dx + fine_dx, coarse_dy + fine_dy, fine_score


def _search_best_offset(
    *,
    reference_mask: np.ndarray,
    asset_mask: np.ndarray,
    left: int,
    top: int,
    search_radius_x: int,
    search_radius_y: int,
    step: int,
) -> tuple[int, int, float] | None:
    height, width = reference_mask.shape
    asset_h, asset_w = asset_mask.shape
    best_score: float | None = None
    best: tuple[int, int, float] | None = None
    for dy in range(-int(search_radius_y), int(search_radius_y) + 1, int(step)):
        candidate_top = int(top + dy)
        if candidate_top < 0 or candidate_top + asset_h > height:
            continue
        for dx in range(-int(search_radius_x), int(search_radius_x) + 1, int(step)):
            candidate_left = int(left + dx)
            if candidate_left < 0 or candidate_left + asset_w > width:
                continue
            ref_crop = reference_mask[candidate_top : candidate_top + asset_h, candidate_left : candidate_left + asset_w]
            intersection = int(np.logical_and(ref_crop, asset_mask).sum())
            union = int(np.logical_or(ref_crop, asset_mask).sum())
            if union <= 0:
                continue
            score = intersection / union
            if best_score is None or score > best_score:
                best_score = score
                best = (int(dx), int(dy), float(score))
    return best


def _shift_box_list(
    boxes: list[tuple[int, int, int, int, int]],
    *,
    dx: int,
    dy: int,
) -> list[tuple[int, int, int, int, int]]:
    shifted: list[tuple[int, int, int, int, int]] = []
    for left, top, right, bottom, area in boxes:
        shifted.append((left + int(dx), top + int(dy), right + int(dx), bottom + int(dy), area))
    return shifted


def _score_text_center_alignment(
    text_boxes: list[tuple[int, int, int, int]],
    candidate_boxes: list[tuple[int, int, int, int, int]],
) -> float:
    if not text_boxes or not candidate_boxes:
        return 0.0

    scores: list[float] = []
    for text_left, text_top, text_width, text_height in text_boxes:
        cx = text_left + text_width / 2.0
        cy = text_top + text_height / 2.0
        best_score = 0.0
        for left, top, right, bottom, _ in candidate_boxes:
            if not (left <= cx <= right and top <= cy <= bottom):
                continue
            width = max(1.0, right - left)
            height = max(1.0, bottom - top)
            center_x = (left + right) / 2.0
            center_y = (top + bottom) / 2.0
            norm_x = max(0.0, 1.0 - abs(cx - center_x) / (width / 2.0))
            norm_y = max(0.0, 1.0 - abs(cy - center_y) / (height / 2.0))
            score = (norm_x + norm_y) / 2.0
            best_score = max(best_score, score)
        if best_score > 0.0:
            scores.append(best_score)
    if not scores:
        return 0.0
    return float(sum(scores) / len(scores))


def _mask_iou(first: np.ndarray, second: np.ndarray) -> float:
    union = np.logical_or(first, second)
    union_count = int(union.sum())
    if union_count <= 0:
        return 1.0
    intersection_count = int(np.logical_and(first, second).sum())
    return intersection_count / union_count


def _shift_mask(mask: np.ndarray, *, dx: int, dy: int) -> np.ndarray:
    shifted = np.zeros_like(mask, dtype=bool)
    height, width = mask.shape
    dst_x1 = max(0, int(dx))
    dst_y1 = max(0, int(dy))
    dst_x2 = min(width, width + int(dx))
    dst_y2 = min(height, height + int(dy))
    if dst_x2 <= dst_x1 or dst_y2 <= dst_y1:
        return shifted

    src_x1 = max(0, -int(dx))
    src_y1 = max(0, -int(dy))
    src_x2 = src_x1 + (dst_x2 - dst_x1)
    src_y2 = src_y1 + (dst_y2 - dst_y1)
    shifted[dst_y1:dst_y2, dst_x1:dst_x2] = mask[src_y1:src_y2, src_x1:src_x2]
    return shifted


def _normalize_adjustments(adjustments: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(adjustments, dict):
        return {}

    normalized: dict[str, Any] = {}
    global_adjustment = adjustments.get("global")
    if isinstance(global_adjustment, dict):
        dx = _coerce_int(global_adjustment.get("dx"))
        dy = _coerce_int(global_adjustment.get("dy"))
        if dx or dy:
            normalized["global"] = {"dx": dx, "dy": dy}

    asset_map: dict[str, dict[str, int]] = {}
    raw_asset_map = adjustments.get("asset_map")
    if isinstance(raw_asset_map, dict):
        for raw_index, raw_plan in raw_asset_map.items():
            if not isinstance(raw_plan, dict):
                continue
            dx = _coerce_int(raw_plan.get("dx"))
            dy = _coerce_int(raw_plan.get("dy"))
            left = raw_plan.get("left")
            top = raw_plan.get("top")
            plan: dict[str, int] = {}
            if left is not None:
                plan["left"] = _coerce_int(left)
            elif dx:
                plan["dx"] = dx
            if top is not None:
                plan["top"] = _coerce_int(top)
            elif dy:
                plan["dy"] = dy
            if plan:
                asset_map[str(raw_index)] = plan
    if asset_map:
        normalized["asset_map"] = asset_map
    return normalized


def _coerce_int(value: Any) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0
