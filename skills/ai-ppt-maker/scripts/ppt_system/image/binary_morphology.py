from __future__ import annotations

import numpy as np

try:
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - 按运行环境决定
    cv2 = None


def rgb_absdiff_to_gray(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    """计算两张 RGB 图的绝对差灰度图，优先使用 OpenCV。"""
    first_rgb = np.asarray(first, dtype=np.uint8)
    second_rgb = np.asarray(second, dtype=np.uint8)
    if first_rgb.shape != second_rgb.shape:
        raise ValueError("输入图像尺寸必须一致")
    if cv2 is not None:
        diff = cv2.absdiff(first_rgb, second_rgb)
        return cv2.cvtColor(diff, cv2.COLOR_RGB2GRAY)
    diff = np.abs(first_rgb.astype(np.int16) - second_rgb.astype(np.int16)).astype(np.uint8)
    return np.round(
        diff[:, :, 0].astype(np.float32) * 0.299
        + diff[:, :, 1].astype(np.float32) * 0.587
        + diff[:, :, 2].astype(np.float32) * 0.114
    ).astype(np.uint8)


def morphology_open(mask: np.ndarray, *, kernel_width: int, kernel_height: int) -> np.ndarray:
    return _morphology(mask, kernel_width=kernel_width, kernel_height=kernel_height, mode="open")


def morphology_close(mask: np.ndarray, *, kernel_width: int, kernel_height: int) -> np.ndarray:
    return _morphology(mask, kernel_width=kernel_width, kernel_height=kernel_height, mode="close")


def _morphology(
    mask: np.ndarray,
    *,
    kernel_width: int,
    kernel_height: int,
    mode: str,
) -> np.ndarray:
    binary = np.asarray(mask, dtype=bool)
    resolved_kernel_width = max(1, int(kernel_width))
    resolved_kernel_height = max(1, int(kernel_height))
    if cv2 is not None:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (resolved_kernel_width, resolved_kernel_height),
        )
        op = cv2.MORPH_OPEN if mode == "open" else cv2.MORPH_CLOSE
        return cv2.morphologyEx(binary.astype(np.uint8), op, kernel).astype(bool)
    if mode == "open":
        return _dilate(_erode(binary, kernel_width=resolved_kernel_width, kernel_height=resolved_kernel_height), kernel_width=resolved_kernel_width, kernel_height=resolved_kernel_height)
    if mode == "close":
        return _erode(_dilate(binary, kernel_width=resolved_kernel_width, kernel_height=resolved_kernel_height), kernel_width=resolved_kernel_width, kernel_height=resolved_kernel_height)
    raise ValueError(f"不支持的形态学模式：{mode}")


def _dilate(mask: np.ndarray, *, kernel_width: int, kernel_height: int) -> np.ndarray:
    pad_y = kernel_height // 2
    pad_x = kernel_width // 2
    padded = np.pad(mask, ((pad_y, pad_y), (pad_x, pad_x)), mode="constant", constant_values=False)
    result = np.zeros(mask.shape, dtype=bool)
    for offset_y in range(kernel_height):
        for offset_x in range(kernel_width):
            result |= padded[offset_y : offset_y + mask.shape[0], offset_x : offset_x + mask.shape[1]]
    return result


def _erode(mask: np.ndarray, *, kernel_width: int, kernel_height: int) -> np.ndarray:
    pad_y = kernel_height // 2
    pad_x = kernel_width // 2
    padded = np.pad(mask, ((pad_y, pad_y), (pad_x, pad_x)), mode="constant", constant_values=False)
    result = np.ones(mask.shape, dtype=bool)
    for offset_y in range(kernel_height):
        for offset_x in range(kernel_width):
            result &= padded[offset_y : offset_y + mask.shape[0], offset_x : offset_x + mask.shape[1]]
    return result
