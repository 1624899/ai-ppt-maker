from __future__ import annotations

import copy
from datetime import datetime
from typing import Any, Mapping


def get_active_plan_payload(state: Mapping[str, Any]) -> dict[str, Any]:
    """从任务状态中提取可编辑规划快照。"""
    plan = copy.deepcopy(state.get("plan", {})) if isinstance(state.get("plan"), dict) else {}
    pages = state.get("pages", [])
    if isinstance(pages, list):
        plan["pages"] = [extract_page_plan(page) for page in pages if isinstance(page, Mapping)]
    else:
        plan["pages"] = []

    job_meta = state.get("job_meta", {})
    if isinstance(job_meta, Mapping):
        plan["page_count"] = int(job_meta.get("page_count") or plan.get("page_count") or len(plan["pages"]))
        plan["title"] = str(plan.get("title") or job_meta.get("content") or "").strip()
    else:
        plan["page_count"] = int(plan.get("page_count") or len(plan["pages"]))
    return normalize_plan_payload(plan)


def extract_page_plan(page: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "page_no": int(page.get("page_no", 0) or 0),
        "title": str(page.get("title") or "").strip(),
        "summary": str(page.get("summary") or "").strip(),
        "bullets": normalize_string_list(page.get("bullets")),
        "layout_intent": str(page.get("layout_intent") or "").strip(),
        "layout_family": str(page.get("layout_family") or "").strip(),
        "page_richness": str(page.get("page_richness") or "").strip(),
        "visual_suggestion": str(page.get("visual_suggestion") or page.get("style_constraints") or "").strip(),
        "reference_mode": str(page.get("reference_mode") or "generation").strip(),
        "prompt_profile": str(page.get("prompt_profile") or "compressed").strip(),
        "reference_prompt": str(page.get("reference_prompt") or page.get("image_prompt") or "").strip(),
        "elements_prompt": str(page.get("elements_prompt") or "").strip(),
        "layout_slots": normalize_string_list(page.get("layout_slots")),
        "texts": copy.deepcopy(page.get("texts", [])) if isinstance(page.get("texts"), list) else [],
        "element_plan": copy.deepcopy(page.get("element_plan", {})),
    }


def normalize_plan_payload(plan: Mapping[str, Any]) -> dict[str, Any]:
    pages = plan.get("pages", [])
    normalized_pages: list[dict[str, Any]] = []
    if isinstance(pages, list):
        for index, page in enumerate(pages):
            if not isinstance(page, Mapping):
                continue
            page_plan = extract_page_plan({**page, "page_no": page.get("page_no") or index + 1})
            if page_plan["page_no"] <= 0:
                page_plan["page_no"] = len(normalized_pages) + 1
            normalized_pages.append(page_plan)
    normalized_pages = renumber_pages(normalized_pages)

    return {
        "title": str(plan.get("title") or "").strip(),
        "summary": str(plan.get("summary") or plan.get("narrative") or "").strip(),
        "audience": str(plan.get("audience") or "").strip(),
        "style_type": str(plan.get("style_type") or "").strip(),
        "style_notes": str(plan.get("style_notes") or "").strip(),
        "style_guide": copy.deepcopy(plan.get("style_guide", {})) if isinstance(plan.get("style_guide"), dict) else {},
        "generation_options": copy.deepcopy(plan.get("generation_options", {}))
        if isinstance(plan.get("generation_options"), dict)
        else {},
        "image_preset": copy.deepcopy(plan.get("image_preset", {})) if isinstance(plan.get("image_preset"), dict) else {},
        "page_count": len(normalized_pages),
        "pages": normalized_pages,
    }


def save_plan_version(
    state: dict[str, Any],
    *,
    source: str,
    summary: str,
    plan: Mapping[str, Any] | None = None,
    activate: bool = True,
) -> dict[str, Any]:
    """保存规划版本并按需设为当前版本。"""
    normalized_plan = normalize_plan_payload(plan or get_active_plan_payload(state))
    versions = state.setdefault("plan_versions", [])
    if not isinstance(versions, list):
        versions = []
        state["plan_versions"] = versions
    version_no = len(versions) + 1
    version_id = f"plan_v{version_no}"
    while any(str(item.get("version_id")) == version_id for item in versions if isinstance(item, Mapping)):
        version_no += 1
        version_id = f"plan_v{version_no}"
    version = {
        "version_id": version_id,
        "source": str(source or "system"),
        "created_at": _utc_timestamp(),
        "summary": str(summary or "").strip(),
        "plan": normalized_plan,
        "pages": copy.deepcopy(normalized_plan["pages"]),
    }
    versions.append(version)
    if activate:
        state["active_plan_version_id"] = version_id
    return version


def apply_plan_to_state(state: dict[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]:
    """把编辑后的规划写回运行态，保留已有产物字段用于后续恢复。"""
    normalized_plan = normalize_plan_payload(plan)
    old_pages = {
        int(page.get("page_no", 0) or 0): page
        for page in state.get("pages", [])
        if isinstance(page, Mapping)
    }
    state["plan"] = {
        **(state.get("plan", {}) if isinstance(state.get("plan"), dict) else {}),
        "title": normalized_plan["title"],
        "style_type": normalized_plan["style_type"],
        "audience": normalized_plan["audience"],
        "narrative": normalized_plan["summary"],
        "page_count": normalized_plan["page_count"],
        "style_guide": normalized_plan["style_guide"],
        "generation_options": normalized_plan["generation_options"],
        "image_preset": normalized_plan["image_preset"],
        "style_notes": normalized_plan["style_notes"],
        "pages": [
            {
                **page,
                "image_prompt": page.get("reference_prompt", ""),
            }
            for page in normalized_plan["pages"]
        ],
    }

    state["pages"] = [_merge_runtime_page_fields(page, old_pages.get(int(page["page_no"]))) for page in normalized_plan["pages"]]
    state["reference_pages"] = _filter_artifacts_by_pages(state.get("reference_pages"), normalized_plan["pages"])
    state["element_pages"] = _filter_artifacts_by_pages(state.get("element_pages"), normalized_plan["pages"])
    job_meta = state.setdefault("job_meta", {})
    job_meta["page_count"] = normalized_plan["page_count"]
    if normalized_plan["style_notes"]:
        job_meta["style_notes"] = normalized_plan["style_notes"]
    return normalized_plan


def get_active_plan_version(state: Mapping[str, Any]) -> dict[str, Any] | None:
    versions = state.get("plan_versions", [])
    if not isinstance(versions, list):
        return None
    active_id = str(state.get("active_plan_version_id") or "").strip()
    for version in versions:
        if isinstance(version, dict) and str(version.get("version_id") or "") == active_id:
            return version
    for version in reversed(versions):
        if isinstance(version, dict):
            return version
    return None


def build_plan_response(state: Mapping[str, Any]) -> dict[str, Any]:
    job_meta = state.get("job_meta", {}) if isinstance(state.get("job_meta"), Mapping) else {}
    return {
        "job_id": str(state.get("job_id") or ""),
        "workflow_mode": str(job_meta.get("workflow_mode") or "auto"),
        "confirmation_policy": copy.deepcopy(job_meta.get("confirmation_policy", {})),
        "plan_confirmation": copy.deepcopy(job_meta.get("plan_confirmation", {})),
        "active_plan_version_id": str(state.get("active_plan_version_id") or ""),
        "plan": get_active_plan_payload(state),
        "plan_versions": copy.deepcopy(state.get("plan_versions", [])) if isinstance(state.get("plan_versions"), list) else [],
    }


def normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def renumber_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sorted_pages = sorted(pages, key=lambda item: int(item.get("page_no", 0) or 0))
    for index, page in enumerate(sorted_pages, start=1):
        page["page_no"] = index
    return sorted_pages


def _merge_runtime_page_fields(page: dict[str, Any], old_page: Mapping[str, Any] | None) -> dict[str, Any]:
    old_page = old_page or {}
    return {
        **page,
        "status": str(old_page.get("status") or "planned"),
        "reference_image": str(old_page.get("reference_image") or ""),
        "element_image": str(old_page.get("element_image") or ""),
        "reference_prompt": str(page.get("reference_prompt") or old_page.get("reference_prompt") or ""),
        "elements_prompt": str(page.get("elements_prompt") or old_page.get("elements_prompt") or ""),
    }


def _filter_artifacts_by_pages(items: Any, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    page_numbers = {int(page.get("page_no", 0) or 0) for page in pages}
    if not isinstance(items, list):
        return []
    return [
        copy.deepcopy(item)
        for item in items
        if isinstance(item, Mapping) and int(item.get("page_no", 0) or 0) in page_numbers
    ]


def _utc_timestamp() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
