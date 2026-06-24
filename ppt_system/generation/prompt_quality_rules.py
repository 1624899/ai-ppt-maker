from __future__ import annotations

import re
from typing import Iterable


REFERENCE_CLEAN_RENDERING_LINE = (
    "画面质量底线：整体画面必须干净、平滑、统一，强调大色块叙事与整体轮廓，不要细碎噪点，"
    "不要高频纹理，不要脏污颗粒，不要密集小装饰，边缘清晰利落，表面干净，画面呼吸感强，一目了然。"
)

_CLAUSE_SPLIT_RE = re.compile(r"[；;\n]+")


def strip_generated_prompt_clauses(text: str, reserved_prefixes: Iterable[str] | None = None) -> str:
    """移除最终提示词会统一生成的片段，避免页面视觉建议重复表达同一类规则。"""

    prefixes = tuple(str(item).strip() for item in (reserved_prefixes or ("内容丰富度要求",)) if str(item).strip())
    if not prefixes:
        return str(text or "").strip()

    clauses = _split_prompt_clauses(text)
    kept = [clause for clause in clauses if not _starts_with_reserved_prefix(clause, prefixes)]
    return "；".join(kept)


def ensure_clean_rendering_line(lines: list[str]) -> list[str]:
    """把统一画面质量底线加入提示词，并避免重复加入。"""

    if any(REFERENCE_CLEAN_RENDERING_LINE in str(line) for line in lines):
        return lines
    return [*lines, REFERENCE_CLEAN_RENDERING_LINE]


def enrich_reference_prompt_text(prompt: str) -> str:
    """为整段原稿图提示词补齐全局画面质量底线。"""

    cleaned = str(prompt or "").strip()
    if not cleaned or REFERENCE_CLEAN_RENDERING_LINE in cleaned:
        return cleaned
    return f"{cleaned}\n{REFERENCE_CLEAN_RENDERING_LINE}"


def _split_prompt_clauses(text: str) -> list[str]:
    return [clause.strip() for clause in _CLAUSE_SPLIT_RE.split(str(text or "")) if clause.strip()]


def _starts_with_reserved_prefix(clause: str, prefixes: tuple[str, ...]) -> bool:
    normalized = clause.strip().lstrip("：: ")
    return any(normalized.startswith(prefix) for prefix in prefixes)
