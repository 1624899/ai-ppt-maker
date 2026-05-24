from __future__ import annotations

import re
from typing import Any

from ppt_system.style_runtime import classify_background_tone

try:
    from ppt_system.design_grammar import ALLOWED_LAYOUT_FAMILIES, validate_layout_family
except ImportError:
    ALLOWED_LAYOUT_FAMILIES = [
        "grid_n_x_m", "timeline_horizontal", "timeline_vertical", "hub_and_spoke",
        "split_left_right", "split_top_bottom", "compare_dual_axis",
        "process_horizontal", "process_vertical", "hero_with_supporting_cards",
    ]

    def validate_layout_family(name: str) -> bool:
        return name in ALLOWED_LAYOUT_FAMILIES


_ABSTRACT_FAMILY_PATTERN = re.compile(
    r"^(grid_\w+|timeline_\w+|hub_and_spoke|split_\w+|compare_\w+|process_\w+|hero_\w+)$",
    re.IGNORECASE,
)


def _check_layout_repeat(page: dict, previous_pages: list[dict], max_repeat: int) -> list[str]:
    issues: list[str] = []
    if not previous_pages:
        return issues
    family = page.get("layout_family", "")
    consecutive = 0
    for prev in reversed(previous_pages):
        if prev.get("layout_family") == family:
            consecutive += 1
        else:
            break
    if consecutive >= max_repeat:
        issues.append(f"layout_family '{family}' 与前页连续重复 {consecutive} 次（上限 {max_repeat}）")
    return issues


def _check_primitive_coverage(page: dict, style_guide: dict) -> list[str]:
    issues: list[str] = []
    prompt = _normalize_visual_text(page.get("image_prompt") or page.get("prompt") or "")
    expected_terms = _collect_expected_visual_terms(page, style_guide)
    if not expected_terms:
        return issues

    matched = [term for term in expected_terms if _matches_visual_term(term, prompt)]
    match_ratio = len(matched) / len(expected_terms)
    if match_ratio < 0.4:
        issues.append(
            f"prompt 对本页视觉元素计划覆盖不足，命中 {len(matched)}/{len(expected_terms)}"
        )
    return issues


def _check_background_tone(page: dict, style_guide: dict) -> list[str]:
    issues: list[str] = []
    style_core = style_guide.get("style_core", {})
    expected_tone = style_core.get("background_tone", "")
    if not expected_tone:
        return issues
    expected_label = classify_background_tone(expected_tone)
    prompt = page.get("image_prompt") or page.get("prompt") or ""
    prompt_label = classify_background_tone(prompt)
    if expected_label != "unknown" and prompt_label != "unknown" and expected_label != prompt_label:
        issues.append(f"背景明度偏离 style_core.background_tone: 期望 '{expected_label}'，prompt 倾向 '{prompt_label}'")
    return issues


def _check_negative_rules(page: dict, style_guide: dict) -> list[str]:
    issues: list[str] = []
    prompt = (page.get("image_prompt") or page.get("prompt") or "").lower()
    negation_markers = ["不要", "禁止", "避免", "不", "请勿", "切勿", "不可", "不能"]
    for rule in style_guide.get("negative_rules", []):
        keywords = [kw.strip() for kw in re.split(r"[，,；;、]", rule) if kw.strip()]
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower not in prompt:
                continue
            if any(kw_lower.startswith(marker) for marker in negation_markers):
                continue
            idx = prompt.find(kw_lower)
            context_before = prompt[max(0, idx - 10):idx]
            if any(marker in context_before for marker in negation_markers):
                continue
            issues.append(f"prompt 未以约束形式表达禁忌词 '{kw}'（规则：{rule}）")
            break
    return issues


def _check_family_naming(page: dict) -> list[str]:
    issues: list[str] = []
    family = page.get("layout_family", "")
    if not family:
        return issues
    if not _ABSTRACT_FAMILY_PATTERN.match(family):
        issues.append(f"layout_family '{family}' 不符合抽象命名模式")
    return issues


def _check_prompt_compression(page: dict, style_guide: dict) -> list[str]:
    issues: list[str] = []
    anchor = style_guide.get("prompt_anchor", "")
    if not anchor:
        return issues
    prompt = page.get("image_prompt") or page.get("prompt") or ""
    anchor_keywords = [kw.strip() for kw in re.split(r"[，,、\s]", anchor) if len(kw.strip()) >= 2]
    if not anchor_keywords:
        return issues
    prompt_lower = prompt.lower()
    matched = sum(1 for kw in anchor_keywords if kw.lower() in prompt_lower)
    ratio = matched / len(anchor_keywords) if anchor_keywords else 1
    if ratio < 0.3:
        issues.append(f"压缩后 prompt 丢失关键风格约束（锚点命中率 {ratio:.0%}）")
    return issues


def _collect_expected_visual_terms(page: dict, style_guide: dict) -> list[str]:
    raw_terms: list[str] = []
    element_plan = page.get("element_plan", {})
    if isinstance(element_plan, dict):
        primitives = element_plan.get("primitives", [])
        icon_topics = element_plan.get("icon_topics", [])
        diagram_type = element_plan.get("diagram_type", "")
        if isinstance(primitives, list):
            raw_terms.extend(str(item).strip() for item in primitives if str(item).strip())
        if isinstance(icon_topics, list):
            raw_terms.extend(str(item).strip() for item in icon_topics if str(item).strip())
        if str(diagram_type).strip():
            raw_terms.append(str(diagram_type).strip())

    if not raw_terms:
        primitives = style_guide.get("element_primitives", [])
        if isinstance(primitives, list):
            raw_terms.extend(str(item).strip() for item in primitives if str(item).strip())

    unique_terms: list[str] = []
    seen: set[str] = set()
    for term in raw_terms:
        norm = _normalize_visual_text(term)
        if norm and norm not in seen:
            unique_terms.append(term)
            seen.add(norm)
    return unique_terms


def _matches_visual_term(term: str, prompt: str) -> bool:
    norm_term = _normalize_visual_text(term)
    if not norm_term:
        return False
    if norm_term in prompt:
        return True

    for variant in _expand_visual_variants(norm_term):
        if variant and variant in prompt:
            return True
    return False


def _expand_visual_variants(term: str) -> list[str]:
    variants: list[str] = []
    if "_" in term:
        ascii_tokens = [item for item in term.split("_") if len(item) >= 3]
        variants.extend(ascii_tokens)

    max_suffix_len = min(6, len(term))
    for suffix_len in range(2, max_suffix_len + 1):
        variants.append(term[-suffix_len:])

    deduped: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        if variant not in seen:
            deduped.append(variant)
            seen.add(variant)
    return deduped


def _normalize_visual_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[\s\-_/:：，,；;（）()【】\[\]·]+", "", text)


def evaluate_page(page: dict, style_guide: dict, previous_pages: list[dict]) -> dict:
    issues: list[str] = []
    max_repeat = 1
    variation_policy = style_guide.get("variation_policy", {})
    if isinstance(variation_policy, dict):
        max_repeat = variation_policy.get("same_layout_max_repeat", 1)

    issues.extend(_check_layout_repeat(page, previous_pages, max_repeat))
    issues.extend(_check_primitive_coverage(page, style_guide))
    issues.extend(_check_background_tone(page, style_guide))
    issues.extend(_check_negative_rules(page, style_guide))
    issues.extend(_check_family_naming(page))
    issues.extend(_check_prompt_compression(page, style_guide))

    penalty = min(len(issues) * 0.12, 0.6)
    score = round(max(1.0 - penalty, 0.0), 2)

    return {
        "score": score,
        "issues": issues,
        "passed": score >= 0.7,
    }


def evaluate_plan(plan: dict, style_guide: dict) -> dict:
    pages = plan.get("pages", [])
    if not pages:
        return {
            "overall_score": 0.0,
            "page_scores": [],
            "summary": "规划中无页面数据",
        }

    page_scores: list[dict] = []
    previous_pages: list[dict] = []
    total_score = 0.0

    for page in pages:
        result = evaluate_page(page, style_guide, previous_pages)
        page_entry = {
            "page_no": page.get("page_no", len(page_scores) + 1),
            "score": result["score"],
            "issues": result["issues"],
            "passed": result["passed"],
        }
        page_scores.append(page_entry)
        total_score += result["score"]
        previous_pages.append(page)

    overall_score = round(total_score / len(pages), 2)
    failed_count = sum(1 for ps in page_scores if not ps["passed"])

    if failed_count == 0:
        summary = f"全部 {len(pages)} 页通过评估，整体得分 {overall_score}"
    else:
        summary = f"{len(pages)} 页中 {failed_count} 页未通过，整体得分 {overall_score}"

    return {
        "overall_score": overall_score,
        "page_scores": page_scores,
        "summary": summary,
    }
