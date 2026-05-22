from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ppt_system.image_prompt import build_image_prompts
from ppt_system.planner import build_plan
from ppt_system.text_layout import build_text_layouts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="根据长文和页面视觉图生成 PPT 项目 JSON。")
    parser.add_argument("--content-file", required=True, help="输入长文 txt 文件，UTF-8 编码。")
    parser.add_argument("--visual-dir", default="", help="页面视觉图目录，按文件名排序匹配页码。")
    parser.add_argument("--visual-image", default="", help="单页测试用视觉图；多页时优先使用 visual-dir。")
    parser.add_argument("--output", default="project.generated.json", help="输出项目 JSON。")
    parser.add_argument("--title", default="自动生成 PPT", help="项目标题。")
    parser.add_argument("--page-count", type=int, default=0, help="指定页数；不填则自动估算。")
    parser.add_argument("--image-width", type=int, default=2000, help="页面视觉图宽度。")
    parser.add_argument("--image-height", type=int, default=1125, help="页面视觉图高度。")
    return parser.parse_args()


def collect_visuals(args: argparse.Namespace, page_count: int) -> list[str]:
    if args.visual_dir:
        visual_dir = Path(args.visual_dir)
        visuals = sorted(
            [
                path
                for path in visual_dir.iterdir()
                if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
            ]
        )
        if len(visuals) < page_count:
            raise ValueError(f"视觉图数量不足：需要 {page_count} 张，当前只有 {len(visuals)} 张。")
        return [str(path) for path in visuals[:page_count]]

    if args.visual_image:
        return [args.visual_image for _ in range(page_count)]

    raise ValueError("请提供 --visual-dir 或 --visual-image。")


def build_project(args: argparse.Namespace) -> dict[str, Any]:
    content = Path(args.content_file).read_text(encoding="utf-8")
    plan = build_plan(content)
    page_count = args.page_count or int(plan["page_count"])
    page_texts = build_text_layouts(
        content,
        page_count=page_count,
        image_width=args.image_width,
        image_height=args.image_height,
    )
    visuals = collect_visuals(args, page_count)

    pages: list[dict[str, Any]] = []
    for page, visual in zip(page_texts, visuals):
        pages.append(
            {
                "page_no": page["page_no"],
                "title": page["title"],
                "summary": page["summary"],
                "visual_image": visual,
                "texts": page["texts"],
            }
        )

    project = {
        "title": args.title,
        "content": content,
        "style_images": [],
        "slide_width_inch": 13.333333,
        "image_width": args.image_width,
        "image_height": args.image_height,
        "default_font": {
            "font_name": "Microsoft YaHei",
            "font_size": 24,
            "color": "FFFFFF",
            "bold": False,
            "italic": False,
            "align": "LEFT",
        },
        "pages": pages,
    }
    project["image_prompts"] = build_image_prompts(project, plan)
    return project


def main() -> None:
    args = parse_args()
    project = build_project(args)
    Path(args.output).write_text(
        json.dumps(project, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"已生成项目配置: {args.output}")
    print(f"页数: {len(project['pages'])}")
    print("每页 ChatGPT Image 提示词已写入 image_prompts 字段。")


if __name__ == "__main__":
    main()

