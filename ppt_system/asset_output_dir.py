from __future__ import annotations

from pathlib import Path


def prepare_asset_output_dir(out_dir: Path) -> None:
    """清理旧的切图产物，避免重复运行后目录里残留历史资产。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    for asset_path in out_dir.glob("asset_*.png"):
        if asset_path.is_file():
            asset_path.unlink()
