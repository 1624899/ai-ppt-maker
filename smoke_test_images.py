from __future__ import annotations

import base64
import json
from datetime import datetime
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parent
TEST_IMAGE = ROOT / "ChatGPT Image5.png"
OUTPUT_ROOT = ROOT / "output"


def save_image_from_response(payload: dict, output_path: Path) -> None:
    data = payload.get("data", [])
    if not data:
        raise RuntimeError(f"接口没有返回 data：{payload}")
    image = data[0]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if image.get("b64_json"):
        output_path.write_bytes(base64.b64decode(image["b64_json"]))
        return
    if image.get("url"):
        response = requests.get(image["url"], timeout=360)
        response.raise_for_status()
        output_path.write_bytes(response.content)
        return
    raise RuntimeError(f"接口没有返回 b64_json 或 url：{payload}")


def print_response(label: str, response: requests.Response) -> dict:
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw_text": response.text}
    print(f"\n[{label}] HTTP {response.status_code}")
    print(json.dumps(payload, ensure_ascii=False, indent=2)[:4000])
    if not response.ok:
        raise RuntimeError(f"{label} 请求失败")
    return payload


def run_generation(base_url: str, api_key: str, output_dir: Path) -> None:
    payload = {
        "model": "gpt-image-2",
        "prompt": "一张极简商务科技风 PPT 单页背景视觉图，蓝白配色，几何线条，留出标题区域，无文字。",
        "size": "1024x1024",
        "quality": "low",
        "n": 1,
    }
    response = requests.post(
        f"{base_url.rstrip('/')}/images/generations",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=360,
    )
    body = print_response("generations", response)
    save_image_from_response(body, output_dir / "generation_test.png")
    print(f"已保存生成测试图片：{output_dir / 'generation_test.png'}")


def run_edit(base_url: str, api_key: str, output_dir: Path) -> None:
    if not TEST_IMAGE.exists():
        raise FileNotFoundError(f"找不到测试图片：{TEST_IMAGE}")
    payload = {
        "model": "gpt-image-2",
        "prompt": "在保留整体版式的前提下，增强蓝色科技感，并加一些更清晰的发光线条元素。",
        "size": "1024x1024",
        "quality": "low",
        "n": 1,
        "response_format": "url",
    }
    with TEST_IMAGE.open("rb") as handle:
        response = requests.post(

            f"{base_url.rstrip('/')}/images/edits",
            headers={"Authorization": f"Bearer {api_key}"},
            data=payload,
            files={"image": (TEST_IMAGE.name, handle, "image/png")},
            timeout=360,
        )
    body = print_response("edits", response)
    save_image_from_response(body, output_dir / "edit_test.png")
    print(f"已保存编辑测试图片：{output_dir / 'edit_test.png'}")


def main() -> None:
    print("图像接口最小成本测试")
    base_url = input("Base URL（直接回车默认 https://anyaigc.com/v1）: ").strip() or "https://anyaigc.com/v1"
    api_key = input("API Key: ").strip()
    if not api_key:
        raise RuntimeError("API Key 不能为空")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = OUTPUT_ROOT / f"smoke_test_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n测试输出目录：{output_dir}")
    run_generation(base_url, api_key, output_dir)
    run_edit(base_url, api_key, output_dir)
    print("\n两个接口都调用完成。")


if __name__ == "__main__":
    main()
