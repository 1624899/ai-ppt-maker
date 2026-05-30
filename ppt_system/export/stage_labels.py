from __future__ import annotations

from typing import Any


STAGE_LABELS = {
    "queued": "等待执行",
    "planning": "模型规划",
    "reference_generation": "参考图生成",
    "elements_generation": "元素图生成",
    "ppt_export": "可编辑元素生成",
    "completed": "全部完成",
}


def get_stage_label(stage_key: Any, fallback: str = "处理中") -> str:
    normalized = str(stage_key or "").strip()
    return STAGE_LABELS.get(normalized, fallback)


def normalize_stage_label(stage_key: Any, stage_label: Any) -> str:
    text = str(stage_label or "").strip()
    if _looks_like_corrupted_label(text):
        return get_stage_label(stage_key)
    return text or get_stage_label(stage_key)


def _looks_like_corrupted_label(text: str) -> bool:
    if not text:
        return True
    meaningful = text.replace(" ", "")
    if not meaningful:
        return True
    if all(char in {"?", "？", "\ufffd"} for char in meaningful):
        return True
    return ("?" in meaningful or "？" in meaningful or "\ufffd" in meaningful) and len(meaningful) <= 12
