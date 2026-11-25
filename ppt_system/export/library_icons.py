from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Callable

from ppt_system.export.export_step_checkpoint import (
    build_export_step_signature,
    build_file_content_signature,
    load_export_step_checkpoint,
    save_export_step_checkpoint,
)
from ppt_system.image.icon_library import render_icon, search_icons
from ppt_system.runtime.interruptible_execution import run_interruptible_call


ICON_PLACEMENT_PROMPT = """识别原稿图中需要用本地 Lucide 线性图标替换的独立通用 icon。
只识别可独立放置的通用小图标；保留照片、品牌标志、复杂插画、图表、流程连接线和卡片容器。
第二张图已要求抹除这些图标及文字，用它核对图标位置；不要把文字、数字或编号徽标识别成图标。
每个图标给出简短英文检索词 query（优先常见 Lucide 名称，如 users、shield-check、chart-column），
原稿中的像素坐标 left/top/width/height（仅图标本体，不包含卡片、背景和文字），及主笔画颜色 color（#RRGGBB）。
不增加原稿中不存在的图标。没有通用图标时返回空数组。
只返回严格 JSON：{"icons":[{"query":"users","left":0,"top":0,"width":40,"height":40,"color":"#2563EB"}]}。
画布尺寸：{width}x{height}。"""


def normalize_icon_placements(result: Any, width: int, height: int) -> list[dict[str, Any]]:
    if not isinstance(result, dict) or not isinstance(result.get("icons"), list):
        raise ValueError("图标识别结果必须包含 icons 数组。")
    icons = []
    for item in result["icons"]:
        if not isinstance(item, dict):
            raise ValueError("图标记录必须是对象。")
        query = str(item.get("query") or "").strip()
        names = search_icons(query, limit=1)
        if not names:
            raise ValueError(f"本地图标未匹配到检索词：{query}，请调整图标描述后重试。")
        color = str(item.get("color") or "").strip()
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError("图标识别结果的 color 必须是 #RRGGBB。")
        box = {}
        for field in ("left", "top", "width", "height"):
            value = item.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"图标坐标 {field} 必须是有限数值。")
            box[field] = round(value)
        if (box["left"] < 0 or box["top"] < 0 or box["width"] <= 0 or box["height"] <= 0
                or box["left"] + box["width"] > width or box["top"] + box["height"] > height):
            raise ValueError("图标识别结果超出画布或尺寸为空。")
        icons.append({"name": names[0], "query": query, "color": color.upper(), **box})
    return icons


def identify_library_icons(
    provider: Any, *, reference_image: Path, elements_image: Path, page_dir: Path,
    page_no: int, width: int, height: int, stop_checker: Callable[[], bool] | None = None,
) -> list[dict[str, Any]]:
    """识别图标并保存独立检查点，重试导出时复用已确认的模型结果。"""
    prompt = ICON_PLACEMENT_PROMPT.replace("{width}", str(width)).replace("{height}", str(height))
    signature = build_export_step_signature(
        step_name="library_icons", operation="identify_library_icons",
        page_signature={"page_no": page_no}, provider=provider,
        inputs={"reference": build_file_content_signature(reference_image),
                "elements": build_file_content_signature(elements_image), "prompt": prompt},
    )
    checkpoint = load_export_step_checkpoint(page_dir, step_name="library_icons", expected_signature=signature)
    if checkpoint is not None:
        return normalize_icon_placements(checkpoint.payload, width, height)
    messages = [{"role": "user", "content": [
        {"type": "input_text", "text": prompt},
        provider.build_image_message_item(reference_image),
        provider.build_image_message_item(elements_image),
    ]}]
    result = run_interruptible_call(
        lambda: provider.complete_json(messages, purpose=f"第 {page_no} 页本地图标定位"),
        stop_checker=stop_checker, interruption_message="图标定位已被中断",
    )
    icons = normalize_icon_placements(result, width, height)
    save_export_step_checkpoint(page_dir, step_name="library_icons", signature=signature,
                                payload={"icons": icons})
    return icons


def append_library_icon_assets(manifest_path: Path, manifest: dict[str, Any], icons: list[dict[str, Any]]) -> None:
    """沿用普通素材清单，使预览、合层和分层导出使用同一组图标。"""
    for index, icon in enumerate(icons, start=1):
        filename = f"icon_{index:03d}.png"
        size = min(icon["width"], icon["height"])
        render_icon(icon["name"], manifest_path.parent / filename,
                    color=icon["color"], size=min(4096, max(64, size * 3)))
        manifest["assets"].append({
            "file": filename, "left": icon["left"] + (icon["width"] - size) // 2,
            "top": icon["top"] + (icon["height"] - size) // 2, "width": size, "height": size,
            "source": "lucide", "icon_name": icon["name"], "color": icon["color"],
        })
    manifest["count"] = len(manifest["assets"])
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
