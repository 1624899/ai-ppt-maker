from __future__ import annotations

import argparse
import json
from pathlib import Path

from ppt_system.direct_page_script import generate_direct_single_page_ppt
from ppt_system.model_cache_runtime import configure_model_cache_environment
from ppt_system.model_config import get_active_model_config, read_config
from ppt_system.openai_chat_provider import OpenAIChatProvider
from ppt_system.direct_page_script import normalize_output_pptx_name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="单页直出文字层：首轮参考图+元素图，随后真实 PPT 导出回看。")
    parser.add_argument("--project", required=True, help="项目 JSON 路径。")
    parser.add_argument("--page-no", type=int, required=True, help="只保留并导出这一页。")
    parser.add_argument("--output-dir", required=True, help="输出目录。")
    parser.add_argument("--output-name", default="result.pptx", help="输出 PPTX 文件名。")
    parser.add_argument("--refine-rounds", type=int, default=1, help="真实 PPT 导出回看轮数，默认 1。")
    parser.add_argument("--config", default="config.json", help="模型配置文件。")
    parser.add_argument("--request-timeout-seconds", type=int, default=0, help="覆盖对话请求超时秒数，0 表示沿用配置。")
    parser.add_argument("--request-retry-count", type=int, default=-1, help="覆盖对话请求重试次数，-1 表示沿用配置。")
    return parser.parse_args()


def load_project(path: Path, page_no: int) -> dict[str, object]:
    project = json.loads(path.read_text(encoding="utf-8"))
    pages = [page for page in project.get("pages", []) if int(page.get("page_no", 0)) == int(page_no)]
    if not pages:
        raise RuntimeError(f"项目中找不到第 {page_no} 页")
    for page in pages:
        reference_image = str(page.get("reference_image", "")).strip()
        if reference_image:
            continue
        candidate = path.parent / "01_reference_pages" / f"page_{int(page_no):02d}_reference.png"
        if candidate.exists():
            page["reference_image"] = str(candidate.resolve())
    project["pages"] = pages
    return project


def main() -> None:
    args = parse_args()
    project_path = Path(args.project)
    config_path = Path(args.config)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    config = read_config(config_path)
    if int(args.request_timeout_seconds) > 0:
        config["request_timeout_seconds"] = int(args.request_timeout_seconds)
    if int(args.request_retry_count) >= 0:
        config["request_retry_count"] = int(args.request_retry_count)
    configure_model_cache_environment(project_root=Path(__file__).resolve().parent, config=config)
    chat_profile = get_active_model_config(config, "chat")
    provider = OpenAIChatProvider(config, chat_profile)

    project = load_project(project_path, args.page_no)
    work_dir = output_dir / "work"
    output_pptx = output_dir / normalize_output_pptx_name(args.output_name)
    project_snapshot = output_dir / "project.single_page.json"
    project_snapshot.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    page = project["pages"][0]
    result = generate_direct_single_page_ppt(
        provider,
        Path(str(page["reference_image"])),
        Path(str(page["visual_image"])),
        work_dir,
        output_pptx,
        slide_width_inch=float(project.get("slide_width_inch", 13.333333)),
        page_no=int(page.get("page_no", 1)),
        refine_rounds=int(args.refine_rounds),
    )
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
