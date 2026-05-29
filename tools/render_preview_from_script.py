from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from ppt_system.direct_page_script import render_direct_comparison_image
from ppt_system.ppt_calibration_renderer import render_pptx_first_slide_to_png


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="复用已有页级脚本，替换资产目录后重新渲染预览。")
    parser.add_argument("--source-script", required=True, help="已有页级脚本路径。")
    parser.add_argument("--work-dir", required=True, help="新的资产工作目录。")
    parser.add_argument("--output-pptx", required=True, help="渲染出的 PPTX 路径。")
    parser.add_argument("--preview-image", required=True, help="导出的预览 PNG 路径。")
    parser.add_argument("--reference-image", required=True, help="参考图路径。")
    parser.add_argument("--comparison-image", required=True, help="对照图输出路径。")
    parser.add_argument("--image-width", type=int, default=2048, help="页面宽度。")
    parser.add_argument("--image-height", type=int, default=1152, help="页面高度。")
    return parser.parse_args()


def _replace_path_assignment(source: str, variable_name: str, path_value: Path) -> str:
    pattern = rf"^{variable_name}\s*=\s*Path\(r\".*?\"\)"
    replacement = f'{variable_name} = Path(r"{path_value.resolve()}")'
    updated, count = re.subn(
        pattern,
        lambda _: replacement,
        source,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise RuntimeError(f"脚本中找不到 {variable_name} 的路径定义。")
    return updated


def main() -> None:
    args = parse_args()
    source_script = Path(args.source_script)
    work_dir = Path(args.work_dir)
    output_pptx = Path(args.output_pptx)
    preview_image = Path(args.preview_image)
    reference_image = Path(args.reference_image)
    comparison_image = Path(args.comparison_image)

    source = source_script.read_text(encoding="utf-8")
    source = _replace_path_assignment(source, "WORK_DIR", work_dir)
    source = _replace_path_assignment(source, "OUTPUT_PPTX", output_pptx)

    namespace = {"__name__": "__render_preview__"}
    exec(compile(source, str(source_script), "exec"), namespace)

    build_deck = namespace.get("build_deck")
    if not callable(build_deck):
        raise RuntimeError("脚本中缺少 build_deck，无法复用渲染。")

    built_pptx = Path(build_deck())
    rendered_preview = render_pptx_first_slide_to_png(
        built_pptx,
        preview_image,
        image_width=int(args.image_width),
        image_height=int(args.image_height),
    )
    if rendered_preview is None:
        raise RuntimeError("PowerPoint 预览导出失败。")
    render_direct_comparison_image(
        reference_image=reference_image,
        preview_image=Path(rendered_preview),
        output_path=comparison_image,
    )
    print(f"pptx={built_pptx.resolve()}")
    print(f"preview={Path(rendered_preview).resolve()}")
    print(f"comparison={comparison_image.resolve()}")


if __name__ == "__main__":
    main()
