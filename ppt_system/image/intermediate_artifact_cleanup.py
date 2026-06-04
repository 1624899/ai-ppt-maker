from __future__ import annotations

from pathlib import Path


def cleanup_split_intermediate_images(page_dir: Path, *, page_no: int) -> list[str]:
    """清理切分阶段的过渡图片，减少无必要的中间产物落盘。"""
    resolved_page_no = int(page_no)
    candidates = [
        page_dir / f"page_{resolved_page_no:02d}_enhanced.png",
        page_dir / f"page_{resolved_page_no:02d}_transparent.png",
    ]
    removed: list[str] = []
    for candidate in candidates:
        if not candidate.exists() or not candidate.is_file():
            continue
        candidate.unlink()
        removed.append(str(candidate))
    return removed
