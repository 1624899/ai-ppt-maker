from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from skill_core.images import normalize_references, prepare_images
from skill_core.project import (
    build_prompts,
    collect_anchors,
    read_project,
    read_source,
    resolve_project_path,
    validate_project,
)
from skill_core.slides import DELIVERY_MODES, build_presentation, render_page_previews


def _write_result(payload: Any, output_path: Path | None = None) -> None:
    value = json.dumps(payload, ensure_ascii=False, indent=2)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(value + "\n", encoding="utf-8")
    print(value)


def _add_project(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True, type=Path, help="UTF-8 项目 JSON 路径。")
    parser.add_argument("--source", type=Path, help="原始长文路径；优先于项目中的 source_file。")


def _add_pages(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pages", nargs="+", type=int, help="仅处理指定页；省略时处理整套。")


def _load(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    project = read_project(args.project)
    source_path = args.source
    if source_path is None and project.get("source_file"):
        source_path = resolve_project_path(args.project, str(project["source_file"]))
    source = read_source(source_path)
    return project, source


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Codex AI PPT Skill 的本地执行入口；不调用项目服务或模型 API。")
    commands = parser.add_subparsers(dest="command", required=True)

    anchors = commands.add_parser("anchors", help="从原文提取事实锚点。")
    anchors.add_argument("--source", required=True, type=Path)
    anchors.add_argument("--pages", required=True, type=int)
    anchors.add_argument("--output", type=Path)

    validate = commands.add_parser("validate", help="校验规划、事实与文字层。")
    _add_project(validate)
    validate.add_argument("--require-text-boxes", action="store_true")
    _add_pages(validate)

    prompts = commands.add_parser("prompts", help="输出压缩后的两阶段生图提示。")
    _add_project(prompts)
    prompts.add_argument("--output", type=Path)

    normalize = commands.add_parser("normalize", help="把已有或新生成的原稿图统一到目标画布。")
    _add_project(normalize)
    normalize.add_argument("--work-dir", required=True, type=Path)
    _add_pages(normalize)

    prepare = commands.add_parser("prepare", help="检测文字区域并对元素图增强、透明化、切分。")
    _add_project(prepare)
    prepare.add_argument("--work-dir", required=True, type=Path)
    prepare.add_argument("--workers", type=int, default=1)
    prepare.add_argument("--min-asset-area", type=int, default=8)
    _add_pages(prepare)

    preview = commands.add_parser("preview", help="用本机 PowerPoint 真实渲染逐页预览。")
    _add_project(preview)
    preview.add_argument("--work-dir", required=True, type=Path)
    preview.add_argument("--output-dir", required=True, type=Path)
    _add_pages(preview)

    export = commands.add_parser("export", help="导出图片版或可编辑分层 PPTX。")
    _add_project(export)
    export.add_argument("--work-dir", required=True, type=Path)
    export.add_argument("--output", required=True, type=Path)
    export.add_argument("--mode", choices=sorted(DELIVERY_MODES), default="separate_slides")
    _add_pages(export)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "anchors":
        source = read_source(args.source)
        if not source.strip() or args.pages < 1:
            raise ValueError("原文不能为空，页数必须大于 0。")
        _write_result({"anchors": collect_anchors(source, args.pages)}, args.output)
        return 0

    project, source = _load(args)
    if args.command == "validate":
        errors = validate_project(
            project,
            source=source,
            require_text_boxes=args.require_text_boxes,
            text_page_numbers=args.pages,
        )
        _write_result({"ok": not errors, "errors": errors})
        return 0 if not errors else 1
    require_boxes = args.command == "preview" or (args.command == "export" and args.mode != "image_only")
    errors = validate_project(project, source=source, require_text_boxes=require_boxes, text_page_numbers=getattr(args, "pages", None))
    if errors:
        raise ValueError("项目校验失败：\n- " + "\n- ".join(errors))

    if args.command == "prompts":
        _write_result({"prompts": build_prompts(project)}, args.output)
    elif args.command == "normalize":
        _write_result({"pages": normalize_references(project, args.project, args.work_dir, args.pages)})
    elif args.command == "prepare":
        _write_result(
            {
                "pages": prepare_images(
                    project,
                    args.project,
                    args.work_dir,
                    page_numbers=args.pages,
                    workers=args.workers,
                    min_asset_area=args.min_asset_area,
                )
            }
        )
    elif args.command == "preview":
        _write_result({"pages": render_page_previews(project, args.work_dir, args.output_dir, page_numbers=args.pages)})
    elif args.command == "export":
        _write_result(build_presentation(project, args.work_dir, args.output, mode=args.mode, page_numbers=args.pages))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
