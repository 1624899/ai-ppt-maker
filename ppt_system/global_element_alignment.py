from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from collections import deque

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class GlobalElementAlignmentDecision:
    should_apply: bool
    dx: int = 0
    dy: int = 0
    baseline_iou: float = 0.0
    shifted_iou: float = 0.0
    confidence: float = 0.0
    reason: str = ""
    diagnostics: dict[str, Any] | None = None


def align_elements_image_to_reference(
    *,
    reference_image: Path,
    elements_image: Path,
    output_path: Path,
    text_boxes: list[tuple[int, int, int, int]] | None = None,
    white_threshold: int = 245,
    alpha_threshold: int = 8,
    mask_padding: int = 12,
    min_shift_px: int = 8,
    min_iou_gain: float = 0.01,
) -> GlobalElementAlignmentDecision:
    """在切分前把整张元素图按参考图坐标系做全局平移拟合。"""
    decision = analyze_global_element_alignment(
        reference_image=reference_image,
        elements_image=elements_image,
        text_boxes=text_boxes,
        white_threshold=white_threshold,
        alpha_threshold=alpha_threshold,
        mask_padding=mask_padding,
        min_shift_px=min_shift_px,
        min_iou_gain=min_iou_gain,
    )
    with Image.open(elements_image).convert("RGBA") as image:
        aligned = shift_image_content(image, dx=decision.dx, dy=decision.dy) if decision.should_apply else image.copy()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    aligned.save(output_path)
    return decision


def analyze_global_element_alignment(
    *,
    reference_image: Path,
    elements_image: Path,
    text_boxes: list[tuple[int, int, int, int]] | None = None,
    white_threshold: int = 245,
    alpha_threshold: int = 8,
    mask_padding: int = 12,
    min_shift_px: int = 8,
    min_iou_gain: float = 0.01,
    coarse_downsample: int = 4,
    coarse_margin_px: int = 40,
    fine_radius_px: int = 12,
) -> GlobalElementAlignmentDecision:
    """估计整张元素图相对参考图的稳定全局平移。"""
    with Image.open(reference_image).convert("RGB") as reference:
        reference_mask = _build_reference_mask(
            reference,
            text_boxes=text_boxes or [],
            padding=mask_padding,
            white_threshold=white_threshold,
        )
    with Image.open(elements_image).convert("RGBA") as elements:
        elements_mask = _build_elements_mask(
            elements,
            alpha_threshold=alpha_threshold,
            white_threshold=white_threshold,
        )

    reference_mask = _suppress_text_like_regions(reference_mask)
    reference_mask = _extract_structure_mask(reference_mask)
    elements_mask = _extract_structure_mask(elements_mask)

    if int(reference_mask.sum()) <= 0 or int(elements_mask.sum()) <= 0:
        return GlobalElementAlignmentDecision(
            should_apply=False,
            reason="empty-mask",
        )

    reference_bbox = _mask_bbox(reference_mask)
    elements_bbox = _mask_bbox(elements_mask)
    if reference_bbox is None or elements_bbox is None:
        return GlobalElementAlignmentDecision(
            should_apply=False,
            reason="missing-bbox",
        )

    anchor_dx = int(round(_bbox_center_x(reference_bbox) - _bbox_center_x(elements_bbox)))
    anchor_dy = int(round(_bbox_center_y(reference_bbox) - _bbox_center_y(elements_bbox)))

    coarse_factor = max(1, int(coarse_downsample))
    coarse_reference = _downsample_mask(reference_mask, factor=coarse_factor)
    coarse_elements = _downsample_mask(elements_mask, factor=coarse_factor)
    coarse_margin = max(4, int(round(int(coarse_margin_px) / coarse_factor)))
    coarse_dx_center = int(round(anchor_dx / coarse_factor))
    coarse_dy_center = int(round(anchor_dy / coarse_factor))
    coarse_result = _search_best_shift(
        reference_mask=coarse_reference,
        elements_mask=coarse_elements,
        start_dx=coarse_dx_center - coarse_margin,
        end_dx=coarse_dx_center + coarse_margin,
        start_dy=coarse_dy_center - coarse_margin,
        end_dy=coarse_dy_center + coarse_margin,
        step=1,
    )
    if coarse_result is None:
        return GlobalElementAlignmentDecision(
            should_apply=False,
            reason="coarse-search-failed",
        )

    coarse_dx, coarse_dy, _ = coarse_result
    fine_center_dx = int(coarse_dx * coarse_factor)
    fine_center_dy = int(coarse_dy * coarse_factor)
    fine_radius = max(2, int(fine_radius_px))
    fine_result = _search_best_shift(
        reference_mask=reference_mask,
        elements_mask=elements_mask,
        start_dx=fine_center_dx - fine_radius,
        end_dx=fine_center_dx + fine_radius,
        start_dy=fine_center_dy - fine_radius,
        end_dy=fine_center_dy + fine_radius,
        step=1,
    )
    if fine_result is None:
        return GlobalElementAlignmentDecision(
            should_apply=False,
            reason="fine-search-failed",
        )

    dx, dy, shifted_iou = fine_result
    baseline_iou = _mask_iou_after_shift(reference_mask, elements_mask, dx=0, dy=0)
    iou_gain = float(shifted_iou - baseline_iou)
    shift_magnitude = max(abs(int(dx)), abs(int(dy)))
    diagnostics = {
        "reference_bbox": reference_bbox,
        "elements_bbox": elements_bbox,
        "anchor_dx": anchor_dx,
        "anchor_dy": anchor_dy,
        "coarse_dx": fine_center_dx,
        "coarse_dy": fine_center_dy,
        "iou_gain": iou_gain,
    }

    if shift_magnitude < int(min_shift_px):
        return GlobalElementAlignmentDecision(
            should_apply=False,
            dx=int(dx),
            dy=int(dy),
            baseline_iou=baseline_iou,
            shifted_iou=float(shifted_iou),
            confidence=max(0.0, iou_gain),
            reason="shift-too-small",
            diagnostics=diagnostics,
        )
    if iou_gain < float(min_iou_gain):
        return GlobalElementAlignmentDecision(
            should_apply=False,
            dx=int(dx),
            dy=int(dy),
            baseline_iou=baseline_iou,
            shifted_iou=float(shifted_iou),
            confidence=max(0.0, iou_gain),
            reason="iou-gain-too-small",
            diagnostics=diagnostics,
        )

    confidence = max(0.0, iou_gain) + min(0.2, shift_magnitude / 500.0)
    return GlobalElementAlignmentDecision(
        should_apply=True,
        dx=int(dx),
        dy=int(dy),
        baseline_iou=baseline_iou,
        shifted_iou=float(shifted_iou),
        confidence=confidence,
        reason="apply-global-element-shift",
        diagnostics=diagnostics,
    )


def shift_image_content(
    image: Image.Image,
    *,
    dx: int,
    dy: int,
) -> Image.Image:
    """在同尺寸透明画布上平移元素图内容。"""
    source = np.array(image.convert("RGBA"), dtype=np.uint8)
    shifted = np.zeros_like(source, dtype=np.uint8)
    height, width = source.shape[:2]

    dst_x1 = max(0, int(dx))
    dst_y1 = max(0, int(dy))
    dst_x2 = min(width, width + int(dx))
    dst_y2 = min(height, height + int(dy))
    if dst_x2 <= dst_x1 or dst_y2 <= dst_y1:
        return Image.fromarray(shifted, mode="RGBA")

    src_x1 = max(0, -int(dx))
    src_y1 = max(0, -int(dy))
    src_x2 = src_x1 + (dst_x2 - dst_x1)
    src_y2 = src_y1 + (dst_y2 - dst_y1)
    shifted[dst_y1:dst_y2, dst_x1:dst_x2] = source[src_y1:src_y2, src_x1:src_x2]
    return Image.fromarray(shifted, mode="RGBA")


def _build_reference_mask(
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
        if x2 > x1 and y2 > y1:
            mask[y1:y2, x1:x2] = False
    return mask


def _build_elements_mask(
    image: Image.Image,
    *,
    alpha_threshold: int,
    white_threshold: int,
) -> np.ndarray:
    rgba = np.array(image.convert("RGBA"), dtype=np.uint8)
    alpha = rgba[:, :, 3]
    if int(alpha.max()) > 0:
        return alpha > int(alpha_threshold)
    rgb = rgba[:, :, :3]
    return np.any(rgb < int(white_threshold), axis=2)


def _extract_contour_mask(mask: np.ndarray) -> np.ndarray:
    """把实心区域压成细边缘，降低大面积填充与残留文字对整页拟合的干扰。"""
    source = np.asarray(mask, dtype=bool)
    if not source.any():
        return source

    neighbors = [
        np.roll(source, shift=1, axis=0),
        np.roll(source, shift=-1, axis=0),
        np.roll(source, shift=1, axis=1),
        np.roll(source, shift=-1, axis=1),
    ]
    interior = source.copy()
    for neighbor in neighbors:
        interior &= neighbor

    # 修正 np.roll 在边界处的环绕影响。
    interior[0, :] = False
    interior[-1, :] = False
    interior[:, 0] = False
    interior[:, -1] = False

    contour = source & ~interior
    if int(contour.sum()) <= 0:
        return source

    # 轻量扩一圈，让细线/虚线在匹配时稍微更稳，不至于过度稀疏。
    expanded = contour.copy()
    expanded[:-1, :] |= contour[1:, :]
    expanded[1:, :] |= contour[:-1, :]
    expanded[:, :-1] |= contour[:, 1:]
    expanded[:, 1:] |= contour[:, :-1]
    return expanded


def _extract_structure_mask(mask: np.ndarray) -> np.ndarray:
    """从整块前景中提取更偏结构化的细线轮廓，尽量压掉文字和整页光晕干扰。"""
    contour = _extract_contour_mask(mask)
    if not contour.any():
        return contour

    height, width = contour.shape
    result = np.zeros_like(contour, dtype=bool)
    for component in _iter_components(contour):
        left, top, right, bottom = component["bbox"]
        box_width = right - left
        box_height = bottom - top
        area = component["area"]
        box_area = max(1, box_width * box_height)
        fill_ratio = float(area) / float(box_area)
        width_ratio = float(box_width) / float(max(1, width))
        height_ratio = float(box_height) / float(max(1, height))

        if _should_keep_structure_component(
            area=area,
            box_width=box_width,
            box_height=box_height,
            fill_ratio=fill_ratio,
            width_ratio=width_ratio,
            height_ratio=height_ratio,
        ):
            result[top:bottom, left:right] |= component["mask"]

    if result.any():
        return result
    return contour


def _suppress_text_like_regions(mask: np.ndarray) -> np.ndarray:
    """从参考图前景中剔除更像文字的高密度连通域，避免它们主导整页拟合。"""
    source = np.asarray(mask, dtype=bool)
    if not source.any():
        return source

    height, width = source.shape
    result = source.copy()
    removed_count = 0
    for component in _iter_components(source):
        left, top, right, bottom = component["bbox"]
        box_width = right - left
        box_height = bottom - top
        area = component["area"]
        box_area = max(1, box_width * box_height)
        fill_ratio = float(area) / float(box_area)
        width_ratio = float(box_width) / float(max(1, width))
        height_ratio = float(box_height) / float(max(1, height))

        if not _looks_like_text_component(
            area=area,
            box_width=box_width,
            box_height=box_height,
            fill_ratio=fill_ratio,
            width_ratio=width_ratio,
            height_ratio=height_ratio,
        ):
            continue

        local_mask = _dilate_local_mask(component["mask"], radius=2)
        result[top:bottom, left:right][local_mask] = False
        removed_count += 1

    if removed_count > 0 and result.any():
        return result
    return source


def _should_keep_structure_component(
    *,
    area: int,
    box_width: int,
    box_height: int,
    fill_ratio: float,
    width_ratio: float,
    height_ratio: float,
) -> bool:
    # 过滤覆盖几乎整页且极度稀疏的背景光晕/阴影轮廓。
    if width_ratio >= 0.9 and height_ratio >= 0.9 and fill_ratio <= 0.02:
        return False

    # 保留大跨度线框、横条和主结构。
    if area >= 900 and (width_ratio >= 0.22 or height_ratio >= 0.12) and fill_ratio <= 0.22:
        return True

    # 保留中等尺寸的图标/框线结构，尽量压掉高密度文字轮廓。
    if area >= 180 and box_width >= 18 and box_height >= 18 and fill_ratio <= 0.28:
        return True

    # 保留细长的连接线、箭头和虚线主干。
    if area >= 80 and fill_ratio <= 0.2 and (box_width >= 80 or box_height >= 80):
        return True

    return False


def _looks_like_text_component(
    *,
    area: int,
    box_width: int,
    box_height: int,
    fill_ratio: float,
    width_ratio: float,
    height_ratio: float,
) -> bool:
    # 文字通常更致密、更扁平，且不会像框体那样以大跨度稀疏线条出现。
    if area < 60:
        return False
    if box_width < 14 or box_height < 12:
        return False
    if width_ratio > 0.75 and height_ratio > 0.12:
        return False
    if fill_ratio >= 0.32 and box_height <= 140:
        return True
    if fill_ratio >= 0.24 and box_height <= 110 and box_width >= 28:
        return True
    if fill_ratio >= 0.18 and box_height <= 72 and box_width >= 48:
        return True
    return False


def _iter_components(mask: np.ndarray) -> list[dict[str, Any]]:
    binary = np.asarray(mask, dtype=bool)
    height, width = binary.shape
    visited = np.zeros_like(binary, dtype=bool)
    components: list[dict[str, Any]] = []
    neighbors = ((1, 0), (-1, 0), (0, 1), (0, -1))

    ys, xs = np.nonzero(binary)
    for start_y, start_x in zip(ys.tolist(), xs.tolist()):
        if visited[start_y, start_x]:
            continue

        queue: deque[tuple[int, int]] = deque([(start_y, start_x)])
        visited[start_y, start_x] = True
        points: list[tuple[int, int]] = []
        while queue:
            y, x = queue.popleft()
            points.append((y, x))
            for dy, dx in neighbors:
                ny = y + dy
                nx = x + dx
                if ny < 0 or nx < 0 or ny >= height or nx >= width:
                    continue
                if not binary[ny, nx] or visited[ny, nx]:
                    continue
                visited[ny, nx] = True
                queue.append((ny, nx))

        component_ys = [point[0] for point in points]
        component_xs = [point[1] for point in points]
        top = min(component_ys)
        bottom = max(component_ys) + 1
        left = min(component_xs)
        right = max(component_xs) + 1
        local_mask = np.zeros((bottom - top, right - left), dtype=bool)
        for y, x in points:
            local_mask[y - top, x - left] = True
        components.append(
            {
                "area": len(points),
                "bbox": (left, top, right, bottom),
                "mask": local_mask,
            }
        )
    return components


def _dilate_local_mask(mask: np.ndarray, *, radius: int) -> np.ndarray:
    expanded = np.asarray(mask, dtype=bool).copy()
    for _ in range(max(0, int(radius))):
        next_mask = expanded.copy()
        next_mask[:-1, :] |= expanded[1:, :]
        next_mask[1:, :] |= expanded[:-1, :]
        next_mask[:, :-1] |= expanded[:, 1:]
        next_mask[:, 1:] |= expanded[:, :-1]
        expanded = next_mask
    return expanded


def _downsample_mask(mask: np.ndarray, *, factor: int) -> np.ndarray:
    resolved_factor = max(1, int(factor))
    if resolved_factor == 1:
        return np.asarray(mask, dtype=bool)
    return np.asarray(mask, dtype=bool)[::resolved_factor, ::resolved_factor]


def _search_best_shift(
    *,
    reference_mask: np.ndarray,
    elements_mask: np.ndarray,
    start_dx: int,
    end_dx: int,
    start_dy: int,
    end_dy: int,
    step: int,
) -> tuple[int, int, float] | None:
    best: tuple[int, int, float] | None = None
    best_score: float | None = None
    for dy in range(int(start_dy), int(end_dy) + 1, max(1, int(step))):
        for dx in range(int(start_dx), int(end_dx) + 1, max(1, int(step))):
            score = _mask_iou_after_shift(reference_mask, elements_mask, dx=dx, dy=dy)
            if best_score is None or score > best_score:
                best_score = score
                best = (int(dx), int(dy), float(score))
    return best


def _mask_iou_after_shift(
    reference_mask: np.ndarray,
    elements_mask: np.ndarray,
    *,
    dx: int,
    dy: int,
) -> float:
    height, width = reference_mask.shape
    dst_x1 = max(0, int(dx))
    dst_y1 = max(0, int(dy))
    dst_x2 = min(width, width + int(dx))
    dst_y2 = min(height, height + int(dy))
    if dst_x2 <= dst_x1 or dst_y2 <= dst_y1:
        return 0.0

    src_x1 = max(0, -int(dx))
    src_y1 = max(0, -int(dy))
    src_x2 = src_x1 + (dst_x2 - dst_x1)
    src_y2 = src_y1 + (dst_y2 - dst_y1)

    reference_crop = reference_mask[dst_y1:dst_y2, dst_x1:dst_x2]
    shifted_crop = elements_mask[src_y1:src_y2, src_x1:src_x2]
    shifted_count = int(shifted_crop.sum())
    reference_count = int(reference_mask.sum())
    if shifted_count <= 0 or reference_count <= 0:
        return 0.0

    intersection = int(np.logical_and(reference_crop, shifted_crop).sum())
    union = reference_count + shifted_count - intersection
    if union <= 0:
        return 1.0
    return intersection / union


def _mask_bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _bbox_center_x(bbox: tuple[int, int, int, int]) -> float:
    left, _, right, _ = bbox
    return (left + right) / 2.0


def _bbox_center_y(bbox: tuple[int, int, int, int]) -> float:
    _, top, _, bottom = bbox
    return (top + bottom) / 2.0
