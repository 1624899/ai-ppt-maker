from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ppt_system.export_pipeline import export_project_to_pptx
from ppt_system.model_config import get_active_model_config, read_config
from ppt_system.openai_chat_provider import OpenAIChatProvider


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PPT 自动制作系统 MVP 流水线。")
    parser.add_argument("--project", required=True, help="项目 JSON 配置文件。")
    parser.add_argument("--work-dir", default="ppt_build", help="中间产物目录。")
    parser.add_argument("--output", default="auto_ppt_output.pptx", help="输出 PPTX。")
    parser.add_argument("--config", default="config.json", help="模型配置文件。")
    parser.add_argument("--alpha-threshold", type=int, default=8, help="元素分割 alpha 阈值。")
    parser.add_argument("--min-area", type=int, default=8, help="元素分割最小面积。")
    parser.add_argument("--min-width", type=int, default=0, help="元素切分最小宽度，小于该值的资产会被过滤。")
    parser.add_argument("--min-height", type=int, default=0, help="元素切分最小高度，小于该值的资产会被过滤。")
    parser.add_argument("--padding", type=int, default=0, help="元素裁剪透明边距。")
    parser.add_argument("--merge-distance", type=int, default=6, help="邻近碎片合并距离，单位为像素。")
    parser.add_argument("--disable-fragment-filter", action="store_true", help="关闭贴边装饰碎片过滤。")
    parser.add_argument("--split-mode", default="classic", choices=["classic", "semantic"], help="元素切分模式：classic 更接近 split_image_to_ppt.py 的干净切图；semantic 会尝试更细粒度拆分。")
    parser.add_argument("--skip-enhance", action="store_true", help="跳过图像增强。")
    parser.add_argument("--skip-transparent", action="store_true", help="跳过透明化阶段。")
    parser.add_argument(
        "--enhance-mode",
        default="builtin",
        choices=["builtin", "external", "skip"],
        help="图像增强模式：builtin/external/skip。",
    )
    parser.add_argument(
        "--enhance-command",
        default="",
        help="外部增强命令模板，支持 {input} {output} {page_no} 等占位符。",
    )
    parser.add_argument(
        "--background-mode",
        default="builtin",
        choices=["builtin", "external", "skip"],
        help="去背景模式：builtin/external/skip。",
    )
    parser.add_argument(
        "--background-command",
        default="",
        help="外部去背景命令模板，支持 {input} {output} {page_no} 等占位符。",
    )
    parser.add_argument(
        "--external-command-timeout-seconds",
        type=int,
        default=1800,
        help="外部增强/去背景命令超时时间，默认 1800 秒。",
    )
    parser.add_argument(
        "--script-refine-rounds",
        type=int,
        default=1,
        help="真实 PPT 导出回看轮数，默认 1。",
    )
    parser.add_argument("--request-timeout-seconds", type=int, default=0, help="覆盖对话请求超时秒数，0 表示沿用配置。")
    parser.add_argument("--request-retry-count", type=int, default=-1, help="覆盖对话请求重试次数，-1 表示沿用配置。")
    return parser.parse_args()


def load_project(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    args = parse_args()
    project = load_project(Path(args.project))
    config_path = Path(args.config)
    config = read_config(config_path)
    if int(args.request_timeout_seconds) > 0:
        config["request_timeout_seconds"] = int(args.request_timeout_seconds)
    if int(args.request_retry_count) >= 0:
        config["request_retry_count"] = int(args.request_retry_count)
    chat_profile = get_active_model_config(config, "chat")
    chat_provider = OpenAIChatProvider(config, chat_profile)
    work_dir = Path(args.work_dir)
    export_project_to_pptx(
        project,
        work_dir,
        Path(args.output),
        alpha_threshold=args.alpha_threshold,
        min_area=args.min_area,
        min_width=args.min_width,
        min_height=args.min_height,
        padding=args.padding,
        merge_distance=args.merge_distance,
        filter_decorative_fragments=not args.disable_fragment_filter,
        split_mode=args.split_mode,
        skip_enhance=args.skip_enhance,
        skip_transparent=args.skip_transparent,
        enhance_mode=args.enhance_mode,
        enhance_command=args.enhance_command,
        background_mode=args.background_mode,
        background_command=args.background_command,
        external_command_timeout_seconds=args.external_command_timeout_seconds,
        script_refine_rounds=args.script_refine_rounds,
        chat_provider=chat_provider,
    )
    print(f"已生成 PPT: {args.output}")
    print(f"中间产物目录: {work_dir}")


if __name__ == "__main__":
    main()
