from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ppt_system.generation_prompts import build_reference_prompt_by_mode

@dataclass(frozen=True)
class PromptExperimentStrategy:
    strategy_id: str
    label: str
    hypothesis: str
    prompt_mode: str
    reference_mode: str


@dataclass(frozen=True)
class PromptExperimentCase:
    strategy_id: str
    label: str
    hypothesis: str
    prompt_mode: str
    requested_reference_mode: str
    effective_reference_mode: str
    uses_reference_images: bool
    page_no: int
    title: str
    prompt: str


EXPERIMENT_STRATEGIES: tuple[PromptExperimentStrategy, ...] = (
    PromptExperimentStrategy(
        strategy_id="baseline_generation",
        label="现状基线-纯文本",
        hypothesis="复现当前主流程，确认问题是否来自提示词过长与参考图未真正入模。",
        prompt_mode="baseline",
        reference_mode="generation",
    ),
    PromptExperimentStrategy(
        strategy_id="baseline_edit_refs",
        label="现状基线-带参考图",
        hypothesis="保持原有长 prompt 不变，只切到 edit_with_refs，隔离“真实参考图输入”带来的影响。",
        prompt_mode="baseline",
        reference_mode="edit_with_refs",
    ),
    PromptExperimentStrategy(
        strategy_id="compact_generation",
        label="精简提示-纯文本",
        hypothesis="减少硬性编排，观察更短的提示词是否能让模型生成更自然的同风格页面。",
        prompt_mode="compact",
        reference_mode="generation",
    ),
    PromptExperimentStrategy(
        strategy_id="compact_edit_refs",
        label="精简提示-带参考图",
        hypothesis="同时缩短提示词并真正传入参考图，测试“弱约束 + 强参考”是否更接近参考图。",
        prompt_mode="compact",
        reference_mode="edit_with_refs",
    ),
    PromptExperimentStrategy(
        strategy_id="slot_brief_edit_refs",
        label="语义骨架-带参考图",
        hypothesis="只保留语义分区，不规定具体卡片和箭头，验证轻量规划是否已经足够。",
        prompt_mode="slot_brief",
        reference_mode="edit_with_refs",
    ),
)


def list_prompt_experiment_strategies() -> list[PromptExperimentStrategy]:
    return list(EXPERIMENT_STRATEGIES)


def build_prompt_experiment_case(
    page: dict[str, Any],
    style_guide: dict[str, Any] | None,
    image_width: int,
    image_height: int,
    strategy_id: str,
    style_reference_count: int = 0,
) -> PromptExperimentCase:
    strategy = _find_strategy(strategy_id)
    effective_reference_mode = strategy.reference_mode
    uses_reference_images = strategy.reference_mode == "edit_with_refs" and style_reference_count > 0
    if strategy.reference_mode == "edit_with_refs" and not uses_reference_images:
        effective_reference_mode = "generation"

    prompt = build_reference_prompt_by_mode(
        page,
        "",
        image_width,
        image_height,
        prompt_mode=strategy.prompt_mode,
        style_guide=style_guide,
        has_reference_images=uses_reference_images,
    )

    return PromptExperimentCase(
        strategy_id=strategy.strategy_id,
        label=strategy.label,
        hypothesis=strategy.hypothesis,
        prompt_mode=strategy.prompt_mode,
        requested_reference_mode=strategy.reference_mode,
        effective_reference_mode=effective_reference_mode,
        uses_reference_images=uses_reference_images,
        page_no=int(page.get("page_no", 0)),
        title=str(page.get("title", "")).strip(),
        prompt=prompt,
    )


def _find_strategy(strategy_id: str) -> PromptExperimentStrategy:
    for strategy in EXPERIMENT_STRATEGIES:
        if strategy.strategy_id == strategy_id:
            return strategy
    available = ", ".join(item.strategy_id for item in EXPERIMENT_STRATEGIES)
    raise ValueError(f"未知实验策略：{strategy_id}。可选：{available}")
