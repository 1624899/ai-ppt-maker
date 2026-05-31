from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从资产清单还原整页透明元素图。")
    parser.add_argument("--assets-root", required=True, help="按页资产根目录。")
    parser.add_argument("--output-root", required=True, help="还原后的透明页面输出目录。")
    parser.add_argument("--pages", nargs="*", type=int, default=None, help="可选，显式指定页号。")
    return parser.parse_args()


def resolve_page_numbers(assets_root: Path, requested_pages: list[int] | None) -> list[int]:
    if requested_pages:
        return [int(page_no) for page_no in requested_pages if int(page_no) > 0]

    page_numbers: list[int] = []
    for page_dir in sorted(assets_root.glob("page_*")):
        if not page_dir.is_dir():
            continue
        try:
            page_no = int(page_dir.name.split("_", 1)[1])
        except (IndexError, ValueError):
            continue
        if (page_dir / "assets" / "assets.json").exists():
            page_numbers.append(page_no)
    return page_numbers


def reconstruct_page(manifest_path: Path, output_path: Path) -> dict[str, int | str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    image_width = max(1, int(manifest.get("image_width", 1)))
    image_height = max(1, int(manifest.get("image_height", 1)))
    assets_dir = manifest_path.parent
    canvas = Image.new("RGBA", (image_width, image_height), (0, 0, 0, 0))

    pasted = 0
    for asset in manifest.get("assets", []):
        asset_path = assets_dir / str(asset.get("file", "")).strip()
        if not asset_path.exists():
            continue
        left = int(asset.get("left", 0) or 0)
        top = int(asset.get("top", 0) or 0)
        with Image.open(asset_path) as asset_image:
            canvas.alpha_composite(asset_image.convert("RGBA"), (left, top))
        pasted += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)
    return {
        "output": str(output_path),
        "asset_count": pasted,
        "image_width": image_width,
        "image_height": image_height,
    }


def main() -> None:
    args = parse_args()
    assets_root = Path(args.assets_root)
    output_root = Path(args.output_root)
    pages = resolve_page_numbers(assets_root, list(args.pages) if args.pages else None)
    if not pages:
        raise ValueError("没有找到可还原的页面。")

    results: list[dict[str, int | str]] = []
    for page_no in pages:
        manifest_path = assets_root / f"page_{page_no:02d}" / "assets" / "assets.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"第 {page_no} 页资产清单不存在：{manifest_path}")
        output_path = output_root / f"page_{page_no:02d}_elements_transparent.png"
        result = reconstruct_page(manifest_path, output_path)
        result["page_no"] = int(page_no)
        results.append(result)

    print(json.dumps({"pages": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
