from __future__ import annotations

import re
from typing import Any


DEFAULT_JOB_TITLE = "未命名 PPT 任务"
MAX_TITLE_CHARS = 36

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_HEADING_RE = re.compile(r"<h[1-3]\b[^>]*>(.*?)</h[1-3]>", re.IGNORECASE | re.DOTALL)
_TITLE_LABEL_RE = re.compile(r"^\s*(?:ppt\s*)?(?:标题|题目|主题|名称|title|topic)\s*[:：]\s*", re.IGNORECASE)
_SECTION_LABEL_RE = re.compile(
    r"^\s*(?:任务内容|内容|目标受众|受众|风格|页数|要求|摘要|背景|说明|输出|页面|结构)\s*[:：]\s*",
    re.IGNORECASE,
)
_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*•·]+|\d+[.)、]|[一二三四五六七八九十]+[、.])\s*")


def normalize_title_text(value: Any, *, max_chars: int = MAX_TITLE_CHARS) -> str:
    """清理可展示标题，避免把 HTML 或长正文直接塞进标题字段。"""
    raw_text = str(value or "").strip()
    if not raw_text:
        return ""
    if _looks_like_rich_content(raw_text):
        return _extract_markup_heading(raw_text, max_chars=max_chars) or _extract_explicit_title(
            raw_text,
            max_chars=max_chars,
        ) or _extract_short_heading_line(
            raw_text,
            max_chars=max_chars,
        )
    return _finalize_title(raw_text, max_chars=max_chars)


def derive_title_from_content(content: Any, *, fallback: str = DEFAULT_JOB_TITLE, max_chars: int = MAX_TITLE_CHARS) -> str:
    """从任务正文中提取短标题；找不到明确标题时返回通用任务名。"""
    raw_text = str(content or "").strip()
    if not raw_text:
        return fallback

    explicit = _extract_markup_heading(raw_text, max_chars=max_chars) or _extract_explicit_title(
        raw_text,
        max_chars=max_chars,
    )
    if explicit:
        return explicit

    short_line = _extract_short_heading_line(raw_text, max_chars=max_chars)
    if short_line:
        return short_line

    return fallback


def resolve_plan_title(*values: Any, fallback_content: Any = "", fallback: str = DEFAULT_JOB_TITLE) -> str:
    """优先使用结构化标题字段，其次从正文提取，最后使用通用标题。"""
    for value in values:
        title = normalize_title_text(value)
        if title:
            return title
    return derive_title_from_content(fallback_content, fallback=fallback)


def _extract_markup_heading(text: str, *, max_chars: int) -> str:
    for match in _HTML_HEADING_RE.finditer(text):
        heading = _finalize_title(match.group(1), max_chars=max_chars)
        if heading:
            return heading
    return ""


def _extract_explicit_title(text: str, *, max_chars: int) -> str:
    for raw_line in _iter_candidate_lines(text):
        line = _clean_text(raw_line)
        if not line:
            continue
        matched = _TITLE_LABEL_RE.match(line)
        if not matched:
            continue
        title = line[matched.end():].strip()
        return _finalize_title(title, max_chars=max_chars)
    return ""


def _extract_short_heading_line(text: str, *, max_chars: int) -> str:
    for raw_line in _iter_candidate_lines(text):
        line = _clean_text(raw_line)
        if not line or _TITLE_LABEL_RE.match(line) or _SECTION_LABEL_RE.match(line):
            continue
        line = _LIST_MARKER_RE.sub("", line).strip()
        if _looks_like_heading(line, max_chars=max_chars):
            return _finalize_title(line, max_chars=max_chars)
    return ""


def _iter_candidate_lines(text: str) -> list[str]:
    html_normalized = re.sub(r"</(?:p|h[1-6]|div|li|br)\s*>", "\n", text, flags=re.IGNORECASE)
    lines = re.split(r"[\r\n]+", html_normalized)
    candidates: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            candidates.append(stripped)
    if candidates:
        return candidates[:8]
    return [text]


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = _HTML_TAG_RE.sub(" ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return " ".join(text.split())


def _finalize_title(value: Any, *, max_chars: int) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    text = _TITLE_LABEL_RE.sub("", text).strip()
    text = _SECTION_LABEL_RE.sub("", text).strip()
    if not text:
        return ""
    return _clip_title(text, max_chars=max_chars)


def _looks_like_rich_content(text: str) -> bool:
    if "\n" in text or "\r" in text:
        return True
    if re.search(r"</?(?:p|h[1-6]|div|li|br|section|article)\b", text, flags=re.IGNORECASE):
        return True
    return len(_clean_text(text)) > MAX_TITLE_CHARS * 2


def _looks_like_heading(text: str, *, max_chars: int) -> bool:
    if not text:
        return False
    if len(text) > max_chars:
        return False
    if any(mark in text for mark in ("。", "！", "？", "；", ";")):
        return False
    if text.count("，") + text.count(",") >= 2:
        return False
    return True


def _clip_title(text: str, *, max_chars: int) -> str:
    cleaned = " ".join(str(text or "").strip().split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rstrip() + "..."
