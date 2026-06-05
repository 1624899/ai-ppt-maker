from __future__ import annotations

import re
from typing import Any

from ppt_system.generation.source_content_control import SourceContentBudget


_HEADING_RE = re.compile(r"^\s*(?:第?[一二三四五六七八九十百千万]+|[0-9]+)[、.．]\s*(.+?)\s*$")
_MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
_BULLET_PREFIX_RE = re.compile(
    r"^\s*(?:[-*•·]|[0-9]+[).、．]|[（(]?[一二三四五六七八九十]+[）)]|[一二三四五六七八九十]+[、.．])\s*"
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])\s*")
_PAGE_HEADING_RE = re.compile(r"^\s*第?\s*[一二三四五六七八九十百千万0-9]+\s*页\s*[：:、.．-]\s*(.+?)\s*$")
_INLINE_PAGE_HEADING_RE = re.compile(
    r"(?P<prefix>^|[\s。！？!?；;])(?P<heading>(?:#{1,6}\s*)?第?\s*[一二三四五六七八九十百千万0-9]+\s*页\s*[：:、.．-]\s*)"
)
_MARKDOWN_DIVIDER_RE = re.compile(r"^\s*[-*_]{3,}\s*$")
_MARKDOWN_STRONG_RE = re.compile(r"(\*\*|__)(.+?)\1")
_MARKDOWN_ITALIC_STAR_RE = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")
_MARKDOWN_ITALIC_UNDERSCORE_RE = re.compile(r"(?<!_)_([^_\n]+?)_(?!_)")
_MAX_SECTION_SUMMARY_BULLETS = 8


def build_source_content_anchors(content: str, page_count: int) -> list[dict[str, Any]]:
    """把用户原文拆成可供模型选择的事实锚点。"""
    text = _normalize_content(content)
    if not text:
        return []

    lines = _content_lines(_break_inline_page_headings(text))
    sections = _split_numbered_sections(lines)
    if sections:
        return [
            _build_anchor(
                index,
                section["title"],
                section["lines"],
                structured=True,
                page_no=section.get("page_no"),
            )
            for index, section in enumerate(sections, start=1)
        ]

    facts = _extract_facts(lines)
    if not facts:
        facts = [text]
    target_count = _resolve_unstructured_anchor_count(len(facts), page_count)
    chunks = _chunk_evenly(facts, target_count)
    anchors: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks, start=1):
        if not chunk:
            continue
        title = _make_title(chunk[0], f"第 {index} 组内容")
        anchors.append(_build_anchor(index, title, chunk, structured=False))
    return anchors


def has_meaningful_source_anchors(
    content: str,
    anchors: list[dict[str, Any]],
    page_count: int,
) -> bool:
    """判断原文是否足够承载事实锚定，避免短任务说明覆盖模型结果。"""
    text = _normalize_content(content)
    if not text or not anchors:
        return False
    if sum(1 for anchor in anchors if anchor.get("structured")) >= 2:
        return True
    total_facts = sum(len(anchor.get("facts", [])) for anchor in anchors)
    return total_facts >= 1


def format_source_anchors_for_prompt(anchors: list[dict[str, Any]], *, max_anchors: int = 18) -> str:
    if not anchors:
        return "无可用事实锚点，请直接基于输入内容规划。"

    sections: list[str] = []
    for anchor in anchors[:max_anchors]:
        lines = [f"{anchor['id']}｜{anchor['title']}"]
        for fact in anchor.get("facts", [])[:6]:
            lines.append(f"- {_shorten_text(fact, 150)}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def resolve_page_source_anchors(
    raw_page: dict[str, Any],
    page_index: int,
    page_count: int,
    anchors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not anchors:
        return []

    by_id = {str(anchor.get("id", "")).strip(): anchor for anchor in anchors}
    selected_ids = _normalize_source_anchor_ids(raw_page.get("source_anchor_ids"))
    if not selected_ids:
        selected_ids = _normalize_source_anchor_ids(raw_page.get("source_anchor_id"))
    selected = [by_id[item] for item in selected_ids if item in by_id]
    selected = _filter_page_scoped_anchors(selected, page_index)
    if selected:
        return selected

    page_scoped = _anchors_for_page(anchors, page_index + 1)
    if page_scoped:
        return page_scoped

    matched = _match_anchors_by_page_text(raw_page, anchors)
    matched = _filter_page_scoped_anchors(matched, page_index)
    if matched:
        return matched

    chunks = _chunk_evenly(anchors, max(1, page_count))
    if 0 <= page_index < len(chunks) and chunks[page_index]:
        return chunks[page_index]
    return [anchors[min(page_index, len(anchors) - 1)]]


def build_page_content_from_source_anchors(
    selected_anchors: list[dict[str, Any]],
    *,
    raw_page: dict[str, Any] | None = None,
    content_budget: SourceContentBudget | None = None,
    max_bullets: int = 6,
) -> dict[str, Any]:
    raw_page = raw_page or {}
    facts = _merge_anchor_facts(selected_anchors)
    if not selected_anchors or not facts:
        return {
            "has_content": False,
            "title": "",
            "summary": "",
            "bullets": [],
            "source_anchor_ids": [],
        }

    selected_text = "\n".join(str(anchor.get("source_text", "")) for anchor in selected_anchors)
    raw_title = str(raw_page.get("title", "")).strip()
    if raw_title and _grounded_text_score(raw_title, selected_text) >= 0.45:
        title = raw_title
    elif len(selected_anchors) == 1:
        title = str(selected_anchors[0].get("title", "")).strip()
    else:
        title = _make_title("、".join(str(anchor.get("title", "")) for anchor in selected_anchors), "页面内容")

    resolved_max_bullets = content_budget.max_bullets if content_budget else max_bullets
    bullets = _select_representative_facts(facts, max_bullets=resolved_max_bullets)
    summary_fact_count = content_budget.summary_fact_count if content_budget else 2
    summary_max_chars = content_budget.summary_max_chars if content_budget else 220
    summary = _build_page_summary(facts, bullets, summary_fact_count, summary_max_chars)
    if content_budget and content_budget.allow_short_expansion:
        bullets = _add_short_content_supporting_points(bullets, content_budget)

    return {
        "has_content": True,
        "title": _shorten_title(title),
        "summary": _shorten_text(summary, summary_max_chars),
        "bullets": bullets,
        "source_anchor_ids": [str(anchor.get("id", "")).strip() for anchor in selected_anchors if anchor.get("id")],
        "content_control": {
            "richness": content_budget.richness if content_budget else "",
            "input_scale": content_budget.input_scale if content_budget else "",
            "guidance": content_budget.guidance if content_budget else "",
        },
    }


def _normalize_content(content: str) -> str:
    text = str(content or "").replace("\r\n", "\n").replace("\r", "\n")
    return text.strip().strip("“”\"'")


def _content_lines(content: str) -> list[str]:
    return [_normalize_line(line) for line in content.splitlines() if _normalize_line(line)]


def _normalize_line(line: str) -> str:
    text = str(line or "").strip()
    markdown_heading = _MARKDOWN_HEADING_RE.match(text)
    if markdown_heading:
        text = markdown_heading.group(1).strip()
    return _strip_markdown_emphasis(text).strip()


def _split_numbered_sections(lines: list[str]) -> list[dict[str, Any]]:
    if _has_page_scoped_headings(lines):
        return _split_page_scoped_sections(lines)
    return _split_outline_sections(lines)


def _has_page_scoped_headings(lines: list[str]) -> bool:
    return any(_detect_heading_info(line).get("heading_type") == "page" for line in lines)


def _split_page_scoped_sections(lines: list[str]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for line in lines:
        heading_info = _detect_heading_info(line)
        if heading_info.get("heading_type") == "page":
            if current is not None and (current["title"] or current["lines"]):
                sections.append(current)
            current = {
                "title": heading_info["title"],
                "lines": [],
                "page_no": heading_info.get("page_no"),
            }
            continue

        if current is None:
            current = {"title": "", "lines": [], "page_no": None}
        current["lines"].append(line)

    if current is not None and (current["title"] or current["lines"]):
        sections.append(current)
    return [section for section in sections if section["title"] or section["lines"]]


def _split_outline_sections(lines: list[str]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    heading_count = 0

    for line in lines:
        heading_info = _detect_heading_info(line)
        if heading_info:
            heading_count += 1
            if current is not None and (current["title"] or current["lines"]):
                sections.append(current)
            current = {
                "title": heading_info["title"],
                "lines": [],
                "page_no": heading_info.get("page_no"),
            }
            continue

        if current is None:
            current = {"title": "", "lines": [], "page_no": None}
        current["lines"].append(line)

    if current is not None and (current["title"] or current["lines"]):
        sections.append(current)
    if heading_count == 1 and sections and sections[0].get("title") and sections[0].get("lines"):
        return [section for section in sections if section["title"] or section["lines"]]
    if heading_count < 2:
        return []
    return [section for section in sections if section["title"] or section["lines"]]


def _detect_heading(line: str) -> str:
    heading_info = _detect_heading_info(line)
    return str(heading_info.get("title", "")) if heading_info else ""


def _detect_heading_info(line: str) -> dict[str, Any]:
    page_heading = _PAGE_HEADING_RE.match(line)
    if page_heading:
        return {
            "title": _shorten_title(page_heading.group(1).strip()),
            "page_no": _parse_page_heading_no(line),
            "heading_type": "page",
        }

    markdown_heading = _MARKDOWN_HEADING_RE.match(line)
    if markdown_heading:
        heading_text = markdown_heading.group(1).strip()
        page_heading = _PAGE_HEADING_RE.match(heading_text)
        if page_heading:
            return {
                "title": _shorten_title(page_heading.group(1).strip()),
                "page_no": _parse_page_heading_no(heading_text),
                "heading_type": "page",
            }
        return {"title": _shorten_title(heading_text), "page_no": None, "heading_type": "section"}

    numbered_heading = _HEADING_RE.match(line)
    if numbered_heading:
        return {"title": _shorten_title(numbered_heading.group(1).strip()), "page_no": None, "heading_type": "section"}
    return {}


def _break_inline_page_headings(content: str) -> str:
    """把一整段中的“第一页：...”页级标记提前切成行边界。"""

    text = str(content or "")
    matches = list(_INLINE_PAGE_HEADING_RE.finditer(text))
    if not matches:
        return text

    parts: list[str] = []
    cursor = 0
    for index, match in enumerate(matches):
        start = match.start("heading")
        if start > cursor:
            parts.append(text[cursor:start])
        next_start = matches[index + 1].start("heading") if index + 1 < len(matches) else len(text)
        title, body = _split_inline_page_heading_body(text[match.end("heading") : next_start])
        heading_line = f"{match.group('heading').strip()}{title}".strip()
        if parts and not parts[-1].endswith(("\n", "\r")):
            parts.append("\n")
        parts.append(heading_line)
        if body:
            parts.append("\n")
            parts.append(body)
        cursor = next_start
    return "".join(parts)


def _split_inline_page_heading_body(text: str) -> tuple[str, str]:
    raw = str(text or "").strip()
    if not raw:
        return "", ""

    newline_match = re.search(r"[\r\n]", raw)
    if newline_match:
        split_at = newline_match.start()
        return raw[:split_at].strip(), raw[split_at:].strip()

    subheading_match = re.search(r"\s+[^。！？!?；;\n\r：:]{1,24}[：:]", raw)
    if subheading_match:
        split_at = subheading_match.start()
        return raw[:split_at].strip(), raw[split_at:].strip()

    inline_sentence_split = _find_inline_title_body_split(raw)
    if inline_sentence_split is not None:
        return raw[:inline_sentence_split].strip(), raw[inline_sentence_split:].strip()

    punctuation_match = re.search(r"[。！？!?；;]", raw)
    if punctuation_match and punctuation_match.start() <= 36:
        split_at = punctuation_match.end()
        return raw[:split_at].strip(), raw[split_at:].strip()
    if len(raw) <= 36:
        return raw, ""
    return raw[:18].strip(), raw[18:].strip()


def _find_inline_title_body_split(text: str) -> int | None:
    """识别“第一页：标题 正文第一句。”这类无换行页标题。"""

    punctuation_match = re.search(r"[。！？!?；;]", text)
    if not punctuation_match or punctuation_match.start() > 48:
        return None

    sentence_prefix = text[: punctuation_match.start()]
    separators = list(re.finditer(r"\s+", sentence_prefix))
    for separator in separators:
        title = sentence_prefix[: separator.start()].strip()
        body_start = sentence_prefix[separator.end() :].strip()
        if _looks_like_inline_page_title(title, body_start):
            return separator.start()
    return None


def _looks_like_inline_page_title(title: str, body_start: str) -> bool:
    if not title or not body_start:
        return False
    if len(title) > 24 or len(body_start) < 4:
        return False
    if re.search(r"[。！？!?；;：:，,]", title):
        return False
    return True


def _parse_page_heading_no(text: str) -> int | None:
    match = re.search(r"第?\s*([一二三四五六七八九十百千万0-9]+)\s*页", str(text or ""))
    if not match:
        return None
    token = match.group(1)
    try:
        return int(token)
    except ValueError:
        return _chinese_number_to_int(token)


def _chinese_number_to_int(text: str) -> int | None:
    values = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    units = {"十": 10, "百": 100, "千": 1000, "万": 10000}
    token = str(text or "").strip()
    if not token:
        return None
    if token in values:
        return values[token]
    total = 0
    current = 0
    for char in token:
        if char in values:
            current = values[char]
        elif char in units:
            unit = units[char]
            total += (current or 1) * unit
            current = 0
        else:
            return None
    return total + current if total or current else None


def _build_anchor(
    index: int,
    title: str,
    lines: list[str],
    *,
    structured: bool,
    page_no: Any = None,
) -> dict[str, Any]:
    facts = _extract_facts(lines)
    if not facts and title:
        facts = [title]
    resolved_title = title or _make_title(facts[0] if facts else "", f"第 {index} 组内容")
    anchor = {
        "id": f"S{index:02d}",
        "title": _shorten_title(resolved_title),
        "facts": facts,
        "source_text": "\n".join([resolved_title, *facts]).strip(),
        "structured": bool(structured),
    }
    normalized_page_no = _normalize_page_no(page_no)
    if normalized_page_no is not None:
        anchor["page_no"] = normalized_page_no
    return anchor


def _extract_facts(lines: list[str]) -> list[str]:
    structured_facts = _extract_heading_scoped_facts(lines)
    if structured_facts:
        return structured_facts

    facts: list[str] = []
    for line in lines:
        normalized = _normalize_line(line).strip()
        if _should_drop_navigation_fact(normalized):
            continue
        cleaned = _clean_fact_line(normalized)
        cleaned = _strip_markdown_emphasis(cleaned)
        if not cleaned:
            continue
        if _should_drop_navigation_fact(cleaned):
            continue
        if _should_keep_line_as_fact(cleaned):
            facts.append(cleaned)
            continue
        facts.extend(_split_sentence_facts(cleaned))
    return _dedupe_keep_order(facts)


def _extract_heading_scoped_facts(lines: list[str]) -> list[str]:
    normalized_lines = [
        _normalize_line(line).strip()
        for line in lines
        if _normalize_line(line).strip() and not _should_drop_navigation_fact(_normalize_line(line).strip())
    ]
    if not normalized_lines:
        return []

    heading_indexes = [
        index
        for index, line in enumerate(normalized_lines)
        if _looks_like_fact_heading(line)
    ]
    if not heading_indexes:
        return []

    facts: list[str] = []
    consumed: set[int] = set()
    for index in heading_indexes:
        if index in consumed:
            continue
        heading = _clean_fact_line(normalized_lines[index])
        next_heading_index = next((item for item in heading_indexes if item > index), len(normalized_lines))
        body_lines = [
            _clean_fact_line(normalized_lines[item])
            for item in range(index + 1, next_heading_index)
            if _clean_fact_line(normalized_lines[item])
        ]
        if body_lines:
            facts.append(_compose_heading_fact(heading, body_lines))
            consumed.update(range(index, next_heading_index))
            continue

        next_line_is_heading = index + 1 < len(normalized_lines) and _looks_like_fact_heading(normalized_lines[index + 1])
        previous_line_is_heading = index > 0 and _looks_like_fact_heading(normalized_lines[index - 1])
        if not next_line_is_heading and not previous_line_is_heading:
            facts.append(heading)
            consumed.add(index)

    for index, line in enumerate(normalized_lines):
        if index in consumed or _looks_like_fact_heading(line):
            continue
        cleaned = _clean_fact_line(line)
        if not cleaned:
            continue
        if _should_keep_line_as_fact(cleaned):
            facts.append(cleaned)
        else:
            facts.extend(_split_sentence_facts(cleaned))

    return _dedupe_keep_order(facts)


def _looks_like_fact_heading(line: str) -> bool:
    cleaned = _clean_fact_line(line)
    if not cleaned or len(cleaned) > 28:
        return False
    if re.search(r"[。！？!?；;：:，,、]", cleaned):
        return False
    if _PAGE_HEADING_RE.match(cleaned):
        return False
    return bool(re.search(r"[\w\u4e00-\u9fff]", cleaned))


def _clean_fact_line(line: str) -> str:
    text = _strip_markdown_emphasis(str(line or "").strip())
    text = _BULLET_PREFIX_RE.sub("", text).strip()
    return _strip_markdown_emphasis(text).strip()


def _compose_heading_fact(heading: str, body_lines: list[str]) -> str:
    body = "；".join(item.strip("；; ") for item in body_lines if item.strip("；; "))
    if not heading:
        return body
    if not body:
        return heading
    return f"{heading}：{body}"


def _strip_markdown_emphasis(text: str) -> str:
    cleaned = str(text or "").strip()
    previous = None
    while previous != cleaned:
        previous = cleaned
        cleaned = _MARKDOWN_STRONG_RE.sub(lambda match: match.group(2), cleaned)
        cleaned = _MARKDOWN_ITALIC_STAR_RE.sub(lambda match: match.group(1), cleaned)
        cleaned = _MARKDOWN_ITALIC_UNDERSCORE_RE.sub(lambda match: match.group(1), cleaned)
    cleaned = re.sub(r"^[*_]+(?=\S)", "", cleaned)
    cleaned = re.sub(r"(?<=\S)[*_]+$", "", cleaned)
    cleaned = cleaned.replace("**", "").replace("__", "")
    return cleaned


def _should_drop_navigation_fact(text: str) -> bool:
    cleaned = str(text or "").strip()
    if not cleaned:
        return True
    if _MARKDOWN_DIVIDER_RE.match(cleaned):
        return True
    return bool(_PAGE_HEADING_RE.match(cleaned))


def _should_keep_line_as_fact(line: str) -> bool:
    if "：" in line or ":" in line:
        return True
    return len(line) <= 90


def _split_sentence_facts(text: str) -> list[str]:
    parts = [part.strip() for part in _SENTENCE_SPLIT_RE.split(text) if part.strip()]
    if len(parts) <= 1:
        comma_parts = _split_long_comma_facts(text)
        if comma_parts:
            return comma_parts
        return [text.strip()] if text.strip() else []
    return parts


def _split_long_comma_facts(text: str) -> list[str]:
    cleaned = str(text or "").strip()
    if len(cleaned) < 120:
        return []
    raw_parts = [part.strip() for part in re.split(r"[，,]\s*", cleaned) if part.strip()]
    if len(raw_parts) < 4:
        return []

    facts: list[str] = []
    current = ""
    for part in raw_parts:
        next_text = f"{current}，{part}" if current else part
        if len(next_text) < 45:
            current = next_text
            continue
        facts.append(next_text)
        current = ""
    if current:
        if facts and len(current) < 28:
            facts[-1] = f"{facts[-1]}，{current}"
        else:
            facts.append(current)
    return facts if len(facts) >= 2 else []


def _resolve_unstructured_anchor_count(fact_count: int, page_count: int) -> int:
    if fact_count <= 0:
        return 1
    target = max(1, min(max(page_count * 2, page_count), 16))
    return max(1, min(fact_count, target))


def _chunk_evenly(items: list[Any], chunk_count: int) -> list[list[Any]]:
    if chunk_count <= 0:
        return []
    if not items:
        return [[] for _ in range(chunk_count)]

    chunks: list[list[Any]] = []
    cursor = 0
    for index in range(chunk_count):
        remaining_items = len(items) - cursor
        remaining_chunks = chunk_count - index
        take = max(1, round(remaining_items / remaining_chunks))
        chunks.append(items[cursor : cursor + take])
        cursor += take
    if cursor < len(items):
        chunks[-1].extend(items[cursor:])
    return chunks


def _normalize_source_anchor_ids(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _filter_page_scoped_anchors(anchors: list[dict[str, Any]], page_index: int) -> list[dict[str, Any]]:
    if not anchors:
        return []

    page_no = page_index + 1
    scoped = [anchor for anchor in anchors if _normalize_page_no(anchor.get("page_no")) == page_no]
    if scoped:
        return scoped
    unscoped = [anchor for anchor in anchors if _normalize_page_no(anchor.get("page_no")) is None]
    if len(unscoped) == len(anchors):
        return anchors
    if unscoped and len(unscoped) != len(anchors):
        return unscoped
    return []


def _anchors_for_page(anchors: list[dict[str, Any]], page_no: int) -> list[dict[str, Any]]:
    return [anchor for anchor in anchors if _normalize_page_no(anchor.get("page_no")) == page_no]


def _normalize_page_no(value: Any) -> int | None:
    try:
        page_no = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return page_no if page_no > 0 else None


def _match_anchors_by_page_text(raw_page: dict[str, Any], anchors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    query_parts = [
        str(raw_page.get("title", "")),
        str(raw_page.get("summary", "")),
    ]
    bullets = raw_page.get("bullets", [])
    if isinstance(bullets, list):
        query_parts.extend(str(item) for item in bullets)
    query = " ".join(part for part in query_parts if part.strip())
    if not query.strip():
        return []

    scored = [
        (_grounded_text_score(query, str(anchor.get("source_text", ""))), anchor)
        for anchor in anchors
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored or scored[0][0] < 0.32:
        return []
    return [scored[0][1]]


def _grounded_text_score(query: str, source: str) -> float:
    query_chars = _match_chars(query)
    source_chars = _match_chars(source)
    if not query_chars or not source_chars:
        return 0.0
    return len(query_chars & source_chars) / max(1, len(query_chars))


def _match_chars(text: str) -> set[str]:
    return {
        char.lower()
        for char in str(text)
        if char.isalnum() or "\u4e00" <= char <= "\u9fff"
    }


def _merge_anchor_facts(selected_anchors: list[dict[str, Any]]) -> list[str]:
    facts: list[str] = []
    for anchor in selected_anchors:
        raw_facts = anchor.get("facts", [])
        if isinstance(raw_facts, list):
            facts.extend(str(item).strip() for item in raw_facts if str(item).strip())
    return _dedupe_keep_order(facts)


def _select_representative_facts(facts: list[str], *, max_bullets: int) -> list[str]:
    if _facts_are_section_summaries(facts):
        return _select_section_summary_facts(facts, max_bullets=max_bullets)

    max_bullets = _expand_budget_for_fact_group(facts, max_bullets)
    if len(facts) <= max_bullets:
        return facts

    indexed = list(enumerate(facts))
    prioritized = sorted(indexed, key=lambda item: (-_fact_priority(item[1]), item[0]))
    selected_indexes = sorted(index for index, _fact in prioritized[:max_bullets])
    return [facts[index] for index in selected_indexes]


def _build_page_summary(
    facts: list[str],
    bullets: list[str],
    summary_fact_count: int,
    summary_max_chars: int,
) -> str:
    if _facts_are_section_summaries(facts):
        section_summary = _summarize_section_fact_headings(facts)
        if section_summary:
            return _shorten_text(section_summary, max(summary_max_chars, 260))

    summary_facts = bullets[:summary_fact_count] if bullets else facts[:summary_fact_count]
    return _shorten_text(" ".join(summary_facts).strip(), summary_max_chars)


def _select_section_summary_facts(facts: list[str], *, max_bullets: int) -> list[str]:
    if len(facts) <= _MAX_SECTION_SUMMARY_BULLETS:
        return facts

    visible_count = max(1, min(max_bullets, _MAX_SECTION_SUMMARY_BULLETS) - 1)
    visible = facts[:visible_count]
    remaining = facts[visible_count:]
    return [*visible, _compose_section_overflow_fact(remaining)]


def _compose_section_overflow_fact(facts: list[str]) -> str:
    items = [_shorten_text(fact, 80) for fact in facts if str(fact).strip()]
    return "其他要点：" + "；".join(items)


def _summarize_section_fact_headings(facts: list[str]) -> str:
    headings = [_section_fact_heading(fact) for fact in facts]
    headings = _dedupe_keep_order([item for item in headings if item])
    if not headings:
        return ""
    if len(headings) == 1:
        return headings[0]
    return f"涵盖{'、'.join(headings)}。"


def _section_fact_heading(fact: str) -> str:
    text = str(fact or "").strip()
    for separator in ("：", ":"):
        if separator in text:
            return text.split(separator, 1)[0].strip()
    return _shorten_title(text, 24)


def _expand_budget_for_fact_group(facts: list[str], max_bullets: int) -> int:
    """遇到“包括：A类、B类、C类”这类枚举组时，尽量完整保留。"""

    if max_bullets <= 0 or len(facts) <= max_bullets:
        return max_bullets
    if len(facts) <= max_bullets + 1 and _facts_are_section_summaries(facts):
        return len(facts)

    for index, fact in enumerate(facts):
        if not _introduces_fact_group(fact):
            continue
        group_end = index + 1
        while group_end < len(facts) and _continues_fact_group(facts[group_end]):
            group_end += 1
        group_size = group_end - index
        if group_size >= 3 and index + group_size <= max_bullets + 2:
            return max(max_bullets, index + group_size)
    return max_bullets


def _facts_are_section_summaries(facts: list[str]) -> bool:
    if len(facts) < 2:
        return False
    section_like_count = sum(1 for fact in facts if "：" in fact or ":" in fact)
    return section_like_count >= max(2, len(facts) - 1)


def _introduces_fact_group(fact: str) -> bool:
    text = str(fact or "").strip()
    return text.endswith(("包括：", "包括:", "如下：", "如下:")) or "主要包括" in text


def _continues_fact_group(fact: str) -> bool:
    text = str(fact or "").strip()
    if not text:
        return False
    if len(text) > 120:
        return False
    return "：" in text or ":" in text or "、" in text


def _add_short_content_supporting_points(facts: list[str], budget: SourceContentBudget) -> list[str]:
    if not facts:
        return facts
    target_count = min(budget.max_bullets, len(facts) + 1)
    if len(facts) >= target_count:
        return facts
    supporting_point = _SHORT_CONTENT_SUPPORT_POINTS.get(budget.richness, "")
    if not supporting_point or supporting_point in facts:
        return facts
    return [*facts, supporting_point]


_SHORT_CONTENT_SUPPORT_POINTS = {
    "medium": "围绕上述信息组织页面表达，突出背景、对象和后续关注点。",
    "high": "围绕上述信息组织页面表达，补充呈现背景、对象、当前状态和后续关注点。",
}


def _fact_priority(fact: str) -> int:
    score = 0
    if "：" in fact or ":" in fact:
        score += 3
    if re.search(r"\d", fact):
        score += 2
    if "包括" in fact or "覆盖" in fact or "形成" in fact:
        score += 1
    return score


def _dedupe_keep_order(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result


def _make_title(text: str, fallback: str) -> str:
    cleaned = re.sub(r"[。！？!?，,；;：:]\s*$", "", str(text or "").strip())
    if not cleaned:
        return fallback
    return _shorten_title(cleaned)


def _shorten_title(text: str, max_chars: int = 18) -> str:
    cleaned = str(text or "").strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rstrip() + "..."


def _shorten_text(text: str, max_chars: int) -> str:
    cleaned = str(text or "").strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip() + "..."
