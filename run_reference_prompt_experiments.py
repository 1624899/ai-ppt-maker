from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ppt_system.model_config import get_active_model_config, read_config
from ppt_system.openai_image_provider import OpenAIImageProvider
from ppt_system.reference_prompt_experiments import (
    build_prompt_experiment_case,
    list_prompt_experiment_strategies,
)


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
OUTPUT_ROOT = ROOT / "output"


def main() -> None:
    args = parse_args()
    config = read_config(CONFIG_PATH)
    job = load_job(args.job_id)
    pages = select_pages(job, parse_page_numbers(args.pages))
    strategy_ids = parse_strategy_ids(args.strategies)

    job_dir = OUTPUT_ROOT / args.job_id
    refs_dir = job_dir / "style_refs"
    style_reference_paths = sorted(path for path in refs_dir.iterdir() if path.is_file())[: args.max_style_refs] if refs_dir.exists() else []
    image_width = int(config.get("image_width", 2048))
    image_height = int(config.get("image_height", 1152))
    style_guide = job.get("plan", {}).get("style_guide", {})

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = job_dir / "prompt_experiments" / f"{timestamp}_{args.tag}".rstrip("_")
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "job_id": args.job_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "pages": [int(page["page_no"]) for page in pages],
        "style_reference_count": len(style_reference_paths),
        "strategies": [],
        "dry_run": bool(args.dry_run),
    }

    image_provider: OpenAIImageProvider | None = None
    if not args.dry_run:
        image_profile = get_active_model_config(config, "image")
        image_provider = OpenAIImageProvider(config, image_profile)

    for strategy_id in strategy_ids:
        strategy_dir = run_dir / strategy_id
        strategy_dir.mkdir(parents=True, exist_ok=True)
        strategy_record: dict[str, Any] = {
            "strategy_id": strategy_id,
            "pages": [],
        }
        for page in pages:
            case = build_prompt_experiment_case(
                page=page,
                style_guide=style_guide,
                image_width=image_width,
                image_height=image_height,
                strategy_id=strategy_id,
                style_reference_count=len(style_reference_paths),
            )
            page_no = int(page["page_no"])
            prompt_path = strategy_dir / f"page_{page_no:02d}_prompt.txt"
            prompt_path.write_text(case.prompt, encoding="utf-8")

            page_record: dict[str, Any] = {
                "page_no": page_no,
                "title": case.title,
                "label": case.label,
                "hypothesis": case.hypothesis,
                "prompt_mode": case.prompt_mode,
                "requested_reference_mode": case.requested_reference_mode,
                "effective_reference_mode": case.effective_reference_mode,
                "uses_reference_images": case.uses_reference_images,
                "prompt_path": str(prompt_path),
                "prompt": case.prompt,
            }

            if image_provider is not None:
                image_path = strategy_dir / f"page_{page_no:02d}.png"
                generation_meta = image_provider.generate_reference_page(
                    prompt=case.prompt,
                    output_path=image_path,
                    style_reference_paths=style_reference_paths if case.uses_reference_images else [],
                    reference_mode=case.effective_reference_mode,
                )
                page_record["image_path"] = str(image_path)
                page_record["generation"] = generation_meta

            strategy_record["pages"].append(page_record)

        manifest["strategies"].append(strategy_record)

    save_manifest(run_dir, manifest)
    save_summary(run_dir, manifest)
    print(f"实验已输出到：{run_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="针对单个任务运行多策略参考图实验")
    parser.add_argument("--job-id", required=True, help="output/<job_id> 对应的任务 ID")
    parser.add_argument(
        "--pages",
        default="1",
        help="要测试的页码，使用逗号分隔，例如 1,3,5；默认仅测试第 1 页",
    )
    parser.add_argument(
        "--strategies",
        default="all",
        help="实验策略列表，逗号分隔；默认 all。可选值见脚本输出的 summary.md",
    )
    parser.add_argument(
        "--max-style-refs",
        type=int,
        default=3,
        help="最多带入多少张 style_refs 作为参考图，默认 3",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只输出 prompt 和 manifest，不实际调用生图接口",
    )
    parser.add_argument(
        "--tag",
        default="",
        help="输出目录附加标签，便于多次实验区分",
    )
    return parser.parse_args()


def load_job(job_id: str) -> dict[str, Any]:
    job_path = OUTPUT_ROOT / job_id / "job.json"
    if not job_path.exists():
        raise FileNotFoundError(f"找不到任务文件：{job_path}")
    return json.loads(job_path.read_text(encoding="utf-8"))


def parse_page_numbers(raw_value: str) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for token in str(raw_value).split(","):
        token = token.strip()
        if not token:
            continue
        page_no = int(token)
        if page_no <= 0:
            raise ValueError("页码必须从 1 开始")
        if page_no not in seen:
            result.append(page_no)
            seen.add(page_no)
    if not result:
        raise ValueError("至少需要提供一个页码")
    return result


def parse_strategy_ids(raw_value: str) -> list[str]:
    available = [item.strategy_id for item in list_prompt_experiment_strategies()]
    if str(raw_value).strip().lower() == "all":
        return available

    result: list[str] = []
    seen: set[str] = set()
    for token in str(raw_value).split(","):
        strategy_id = token.strip()
        if not strategy_id:
            continue
        if strategy_id not in available:
            raise ValueError(f"未知策略：{strategy_id}。可选：{', '.join(available)}")
        if strategy_id not in seen:
            result.append(strategy_id)
            seen.add(strategy_id)
    if not result:
        raise ValueError("至少需要提供一个策略")
    return result


def select_pages(job: dict[str, Any], page_numbers: list[int]) -> list[dict[str, Any]]:
    pages = job.get("plan", {}).get("pages", [])
    if not isinstance(pages, list):
        raise ValueError("任务中缺少 plan.pages，无法运行实验")

    page_map = {}
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_map[int(page.get("page_no", 0))] = page

    result: list[dict[str, Any]] = []
    for page_no in page_numbers:
        page = page_map.get(page_no)
        if page is None:
            raise ValueError(f"任务中不存在第 {page_no} 页")
        result.append(page)
    return result


def save_manifest(run_dir: Path, manifest: dict[str, Any]) -> None:
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def save_summary(run_dir: Path, manifest: dict[str, Any]) -> None:
    lines = [
        f"# Prompt Experiments: {manifest['job_id']}",
        "",
        f"- 创建时间：{manifest['created_at']}",
        f"- 测试页码：{', '.join(str(item) for item in manifest['pages'])}",
        f"- 参考图数量：{manifest['style_reference_count']}",
        f"- dry_run：{manifest['dry_run']}",
        "",
        "## 策略说明",
    ]

    for strategy in manifest.get("strategies", []):
        pages = strategy.get("pages", [])
        if not pages:
            continue
        first_page = pages[0]
        lines.extend(
            [
                "",
                f"### {strategy['strategy_id']}",
                f"- 标签：{first_page.get('label', '')}",
                f"- 假设：{first_page.get('hypothesis', '')}",
                f"- 提示模式：{first_page.get('prompt_mode', '')}",
                f"- 请求模式：{first_page.get('requested_reference_mode', '')}",
                f"- 实际模式：{first_page.get('effective_reference_mode', '')}",
                f"- 是否带参考图：{first_page.get('uses_reference_images', False)}",
            ]
        )

    summary_path = run_dir / "summary.md"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
