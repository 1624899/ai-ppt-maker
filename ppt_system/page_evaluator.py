from __future__ import annotations

import re
from typing import Any

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

_BRIGHTNESS_KEYWORDS = {
    "light": {"白", "浅", "亮", "light", "bright", "白底", "浅色", "明亮"},
    "dark": {"黑", "深", "暗", "dark", "深色", "暗色", "黑底"},
    "neutral": {"灰", "中性", "gray", "grey", "中灰"},
}


def _classify_brightness(text: str) -> str:
    lower = text.lower()
    for label, keywords in _BRIGHTNESS_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return label
    return "unknown"


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
    prompt = (page.get("image_prompt") or page.get("prompt") or "").lower()
    primitives = style_guide.get("element_primitives", [])
    if not primitives:
        return issues
    missing = [p for p in primitives if p.lower() not in prompt]
    if len(missing) > len(primitives) * 0.6:
        issues.append(f"prompt 未覆盖大部分元素原语，缺失 {len(missing)}/{len(primitives)}")
    return issues


def _check_background_tone(page: dict, style_guide: dict) -> list[str]:
    issues: list[str] = []
    style_core = style_guide.get("style_core", {})
    expected_tone = style_core.get("background_tone", "")
    if not expected_tone:
        return issues
    expected_label = _classify_brightness(expected_tone)
    prompt = page.get("image_prompt") or page.get("prompt") or ""
    prompt_label = _classify_brightness(prompt)
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
