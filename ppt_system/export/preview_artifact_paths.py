from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class RoundPreviewArtifacts:
    script_path: Path
    pptx_path: Path
    image_path: Path
    comparison_path: Path


def build_round_preview_artifacts(page_dir: Path, round_number: int) -> RoundPreviewArtifacts:
    """生成单轮真实渲染回看的中间产物路径。"""
    resolved_round = int(round_number)
    if resolved_round <= 0:
        raise ValueError("预览轮次必须大于 0。")

    round_stem = f"round_{resolved_round:02d}"
    return RoundPreviewArtifacts(
        script_path=page_dir / f"generated_text_layout_preview_{round_stem}.py",
        pptx_path=_build_unique_preview_pptx_path(page_dir, round_stem),
        image_path=page_dir / f"office_preview_{round_stem}.png",
        comparison_path=page_dir / f"comparison_{round_stem}.png",
    )


def _build_unique_preview_pptx_path(page_dir: Path, round_stem: str) -> Path:
    token = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    unique_part = f"{token}_{os.getpid()}_{uuid.uuid4().hex[:10]}"
    return page_dir / "preview_pptx" / f"render_preview_{round_stem}_{unique_part}.pptx"
