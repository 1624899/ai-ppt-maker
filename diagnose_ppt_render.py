from __future__ import annotations

import argparse
from pathlib import Path

from ppt_system.ppt_calibration_renderer import render_pptx_first_slide_to_png


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="诊断本机是否能用 PowerPoint 真渲染导出首张幻灯片 PNG。")
    parser.add_argument("--pptx", required=True, help="待导出的 PPTX 文件。")
    parser.add_argument("--output", required=True, help="导出的 PNG 路径。")
    parser.add_argument("--width", type=int, default=2048, help="导出宽度。")
    parser.add_argument("--height", type=int, default=1152, help="导出高度。")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pptx_path = Path(args.pptx)
    output_path = Path(args.output)
    result = render_pptx_first_slide_to_png(
        pptx_path,
        output_path,
        image_width=args.width,
        image_height=args.height,
    )
    if result is None:
        print("office_render: unavailable")
        return
    print(f"office_render: ok\noutput: {result.resolve()}")


if __name__ == "__main__":
    main()
