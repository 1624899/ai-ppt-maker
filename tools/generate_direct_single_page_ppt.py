from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from ppt_system.direct_page_script import (  # noqa: E402
    DEFAULT_SLIDE_WIDTH_INCH,
    generate_direct_single_page_ppt,
    normalize_output_pptx_name,
)
from ppt_system.model_config import get_active_model_config, read_config  # noqa: E402
from ppt_system.openai_chat_provider import OpenAIChatProvider  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="只基于参考图生成文字层脚本，再把元素图加入 PPT。")
    parser.add_argument("--reference-image", required=True, help="完整参考图路径。")
    parser.add_argument("--elements-image", required=True, help="去文字后的元素图路径。")
    parser.add_argument("--output-dir", required=True, help="输出目录。")
    parser.add_argument("--output-name", default="result.pptx", help="输出 PPTX 文件名。")
    parser.add_argument("--config", default="config.json", help="模型配置文件。")
    parser.add_argument("--page-no", type=int, default=1, help="输出脚本中的页码。")
    parser.add_argument("--slide-width-inch", type=float, default=DEFAULT_SLIDE_WIDTH_INCH, help="幻灯片宽度，默认 13.333333。")
    parser.add_argument("--refine-rounds", type=int, default=1, help="真实 PPT 渲染回看轮数。默认 1，若本机不可用 Office 渲染则自动跳过。")
    parser.add_argument("--request-timeout-seconds", type=int, default=0, help="覆盖对话请求超时秒数，0 表示沿用配置。")
    parser.add_argument("--request-retry-count", type=int, default=-1, help="覆盖对话请求重试次数，-1 表示沿用配置。")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    config = read_config(config_path)
    if int(args.request_timeout_seconds) > 0:
        config["request_timeout_seconds"] = int(args.request_timeout_seconds)
    if int(args.request_retry_count) >= 0:
        config["request_retry_count"] = int(args.request_retry_count)

    chat_profile = get_active_model_config(config, "chat")
    provider = OpenAIChatProvider(config, chat_profile)

    output_pptx = output_dir / normalize_output_pptx_name(args.output_name)
    work_dir = output_dir / "work"
    result = generate_direct_single_page_ppt(
        provider,
        Path(args.reference_image),
        Path(args.elements_image),
        work_dir,
        output_pptx,
        slide_width_inch=float(args.slide_width_inch),
        page_no=int(args.page_no),
        refine_rounds=int(args.refine_rounds),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
