from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from ppt_system.export.direct_page_script import prepare_direct_page_assets  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="基于现成透明元素图重跑资产切分。")
    parser.add_argument("--project", required=True, help="项目 JSON 路径，用于读取页面顺序和画布尺寸。")
    parser.add_argument("--transparent-root", required=True, help="透明元素图目录。")
    parser.add_argument("--output-root", required=True, help="新的切分输出目录。")
    parser.add_argument("--pages", nargs="*", type=int, default=None, help="可选，显式指定页号。")
    parser.add_argument("--merge-distance", type=int, default=6, help="组件合并距离。")
    parser.add_argument("--alpha-threshold", type=int, default=8, help="alpha 阈值。")
    return parser.parse_args()


def resolve_pages(project_payload: dict, requested_pages: list[int] | None) -> list[dict]:
    project_pages = list(project_payload.get("pages", []))
    if requested_pages:
        requested = {int(page_no) for page_no in requested_pages}
        return [page for page in project_pages if int(page.get("page_no", 0)) in requested]
    return [page for page in project_pages if int(page.get("page_no", 0)) > 0]


def main() -> None:
    args = parse_args()
    project_path = Path(args.project)
    project_payload = json.loads(project_path.read_text(encoding="utf-8"))
    transparent_root = Path(args.transparent_root)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    summaries: list[dict[str, int | str]] = []
    for page in resolve_pages(project_payload, list(args.pages) if args.pages else None):
        page_no = int(page.get("page_no", 0))
        transparent_path = transparent_root / f"page_{page_no:02d}_elements_transparent.png"
        if not transparent_path.exists():
            raise FileNotFoundError(f"第 {page_no} 页透明图不存在：{transparent_path}")

        result = prepare_direct_page_assets(
            work_dir=output_root,
            page_no=page_no,
            elements_image=transparent_path,
            reference_image=None,
            image_width=int(project_payload.get("image_width", 0)),
            image_height=int(project_payload.get("image_height", 0)),
            alpha_threshold=int(args.alpha_threshold),
            merge_distance=int(args.merge_distance),
            cleanup_intermediate_images=False,
        )
        summaries.append(
            {
                "page_no": page_no,
                "asset_count": int(result.manifest.get("count", 0)),
                "raw_component_count": int(result.manifest.get("raw_component_count", 0)),
                "merged_component_count": int(result.manifest.get("merged_component_count", 0)),
                "manifest_path": str(result.manifest_path),
            }
        )

    print(json.dumps({"pages": summaries}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
