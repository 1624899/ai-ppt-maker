from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
OUTPUT_ROOT = ROOT / "output"


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def get_active_image_profile(config: dict[str, Any]) -> dict[str, Any]:
    active_id = str(config.get("active_image_config_id", "")).strip()
    profiles = list(config.get("model_configs", {}).get("image", []))
    for profile in profiles:
        if str(profile.get("id", "")).strip() == active_id:
            return profile
    for profile in profiles:
        if profile.get("enabled"):
            return profile
    raise RuntimeError("未找到可用的生图模型配置")


def build_generation_payload() -> dict[str, Any]:
    return {
        "model": "gpt-image-2",
        "prompt": "一张极简商务科技风幻灯片背景，蓝白配色，轻几何线条，留出标题区域，无文字。",
        "size": "1024x1024",
        "quality": "low",
        "n": 1,
    }


def build_output_dir() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = OUTPUT_ROOT / f"transport_diag_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def summarize_exception(exc: BaseException) -> dict[str, Any]:
    chain = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        chain.append(
            {
                "type": type(current).__name__,
                "message": str(current),
            }
        )
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return {
        "type": type(exc).__name__,
        "message": str(exc),
        "chain": chain,
    }


def maybe_fetch_image(image_url: str, timeout_seconds: int) -> dict[str, Any]:
    started = time.time()
    response = requests.get(image_url, timeout=timeout_seconds)
    elapsed = round(time.time() - started, 3)
    response.raise_for_status()
    return {
        "status_code": response.status_code,
        "elapsed_seconds": elapsed,
        "content_length": len(response.content),
    }


def run_once(
    *,
    base_url: str,
    api_key: str,
    timeout_seconds: int,
    fetch_image: bool,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/images/generations"
    payload = build_generation_payload()
    record: dict[str, Any] = {
        "request_url": url,
        "request_timeout_seconds": timeout_seconds,
        "payload": payload,
        "post_started_at": datetime.now().isoformat(timespec="seconds"),
    }
    started = time.time()
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout_seconds,
        )
        record["post_elapsed_seconds"] = round(time.time() - started, 3)
        record["post_status_code"] = response.status_code
        record["response_headers"] = dict(response.headers)
        try:
            body = response.json()
            record["response_json_keys"] = list(body.keys())
        except ValueError:
            body = {"raw_text": response.text[:2000]}
            record["response_json_keys"] = []
        record["response_preview"] = body
        response.raise_for_status()
        record["post_ok"] = True

        data = body.get("data", [])
        first_item = data[0] if data else {}
        if fetch_image and first_item.get("url"):
            record["image_fetch"] = maybe_fetch_image(str(first_item["url"]), timeout_seconds)
        return record
    except Exception as exc:
        record["post_elapsed_seconds"] = round(time.time() - started, 3)
        record["post_ok"] = False
        record["error"] = summarize_exception(exc)
        return record


def main() -> None:
    parser = argparse.ArgumentParser(description="验证图像接口的传输稳定性")
    parser.add_argument("--count", type=int, default=3, help="请求次数，默认 3")
    parser.add_argument("--timeout", type=int, default=180, help="单次请求超时秒数，默认 180")
    parser.add_argument("--fetch-image", action="store_true", help="额外验证返回的图片 URL 是否可下载")
    args = parser.parse_args()

    config = load_config()
    profile = get_active_image_profile(config)
    base_url = str(profile.get("base_url", config.get("api_base_url", ""))).strip()
    api_key = str(profile.get("api_key", "")).strip()
    if not base_url or not api_key:
        raise RuntimeError("当前启用的生图配置缺少 base_url 或 api_key")

    output_dir = build_output_dir()
    report_path = output_dir / "transport_report.json"
    report: dict[str, Any] = {
        "base_url": base_url,
        "model": str(profile.get("model", config.get("image_model", ""))),
        "count": args.count,
        "timeout": args.timeout,
        "fetch_image": bool(args.fetch_image),
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "results": [],
    }

    for index in range(args.count):
        result = run_once(
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=args.timeout,
            fetch_image=bool(args.fetch_image),
        )
        result["attempt_no"] = index + 1
        report["results"].append(result)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        status = "成功" if result.get("post_ok") else "失败"
        print(f"第 {index + 1} 次请求：{status}，耗时 {result.get('post_elapsed_seconds', 0)} 秒")
        if not result.get("post_ok"):
            error = result.get("error", {})
            print(f"  异常：{error.get('type', '')} - {error.get('message', '')}")

    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"诊断报告已保存：{report_path}")


if __name__ == "__main__":
    main()
