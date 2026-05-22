from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ppt_system.export_pipeline import export_project_to_pptx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PPT 自动制作系统 MVP 流水线。")
    parser.add_argument("--project", required=True, help="项目 JSON 配置文件。")
    parser.add_argument("--work-dir", default="ppt_build", help="中间产物目录。")
    parser.add_argument("--output", default="auto_ppt_output.pptx", help="输出 PPTX。")
    parser.add_argument("--alpha-threshold", type=int, default=8, help="元素分割 alpha 阈值。")
    parser.add_argument("--min-area", type=int, default=8, help="元素分割最小面积。")
    parser.add_argument("--padding", type=int, default=0, help="元素裁剪透明边距。")
    parser.add_argument("--skip-enhance", action="store_true", help="跳过图像增强。")
    parser.add_argument("--skip-transparent", action="store_true", help="跳过透明化/rembg 阶段。")
    return parser.parse_args()


def load_project(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    args = parse_args()
    project = load_project(Path(args.project))
    work_dir = Path(args.work_dir)
    export_project_to_pptx(
        project,
        work_dir,
        Path(args.output),
        alpha_threshold=args.alpha_threshold,
        min_area=args.min_area,
        padding=args.padding,
        skip_enhance=args.skip_enhance,
        skip_transparent=args.skip_transparent,
    )
    print(f"已生成 PPT: {args.output}")
    print(f"中间产物目录: {work_dir}")


if __name__ == "__main__":
    main()
