from __future__ import annotations

import base64
import json
from datetime import datetime
from pathlib import Path

import requests
from requests import Session
from requests import Response
from requests.exceptions import SSLError

from network_diagnostics import build_ssl_hint, collect_tls_diagnostics, format_tls_diagnostics


ROOT = Path(__file__).resolve().parent
TEST_IMAGE = ROOT / "ChatGPT Image5.png"
OUTPUT_ROOT = ROOT / "output"


def create_session(direct_mode: bool) -> Session:
    session = requests.Session()
    if direct_mode:
        # 关闭 requests 对系统代理和环境代理变量的继承，尽量直连目标站点。
        session.trust_env = False
        session.proxies.clear()
    return session


def post_with_diagnostics(
    session: Session,
    url: str,
    *,
    headers: dict[str, str],
    timeout: int,
    **kwargs: object,
) -> Response:
    try:
        return session.post(url, headers=headers, timeout=timeout, **kwargs)
    except SSLError as exc:
        diagnostics = collect_tls_diagnostics(url)
        message = "\n".join(
            [
                f"请求发生 SSL 错误：{exc}",
                format_tls_diagnostics(diagnostics),
                f"排查建议：{build_ssl_hint(diagnostics)}",
            ]
        )
        raise RuntimeError(message) from exc


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


def resolve_edit_input_image(user_input: str, output_dir: Path) -> Path:
    raw = user_input.strip()
    candidates: list[Path] = []
    if raw:
        candidates.append(Path(raw).expanduser())

    candidates.extend(
        [
            TEST_IMAGE,
            output_dir / "generation_test.png",
        ]
    )

    for path in candidates:
        resolved = path if path.is_absolute() else (ROOT / path).resolve()
        if resolved.exists() and resolved.is_file():
            return resolved

    candidate_text = "、".join(str(path) for path in candidates)
    raise FileNotFoundError(
        f"找不到可用于编辑测试的图片。已尝试这些路径：{candidate_text}"
    )


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


def run_generation(session: Session, base_url: str, api_key: str, output_dir: Path) -> Path:
    url = f"{base_url.rstrip('/')}/images/generations"
    payload = {
        "model": "gpt-image-2-all",
        "prompt": "一张极简商务科技风 PPT 单页背景视觉图，蓝白配色，几何线条，留出标题区域，无文字。",
        "size": "1024x1024",
        "quality": "low",
        "n": 1,
    }
    response = post_with_diagnostics(
        session,
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=360,
    )
    body = print_response("generations", response)
    output_path = output_dir / "generation_test.png"
    save_image_from_response(body, output_path)
    print(f"已保存生成测试图片：{output_path}")
    return output_path


def run_edit(
    session: Session,
    base_url: str,
    api_key: str,
    output_dir: Path,
    input_image_path: Path,
) -> None:
    url = f"{base_url.rstrip('/')}/images/edits"
    payload = {
        "model": "gpt-image-2-all",
        "prompt": "在保留整体版式的前提下，增强蓝色科技感，并加一些更清晰的发光线条元素。",
        "size": "1024x1024",
        "quality": "low",
        "n": 1,
        "response_format": "url",
    }
    with input_image_path.open("rb") as handle:
        response = post_with_diagnostics(
            session,
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            data=payload,
            files={"image": (input_image_path.name, handle, "image/png")},
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
    direct_mode = input("是否禁用环境代理并尝试直连（y/N）: ").strip().lower() == "y"
    edit_image_input = input("编辑测试图片路径（直接回车则优先使用默认图，其次使用刚生成的图片）: ").strip()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = OUTPUT_ROOT / f"smoke_test_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    session = create_session(direct_mode)

    print(f"\n测试输出目录：{output_dir}")
    print(f"代理模式：{'直连（禁用环境代理）' if direct_mode else '默认'}")
    generation_image_path = run_generation(session, base_url, api_key, output_dir)
    input_image_path = resolve_edit_input_image(edit_image_input, output_dir)
    if input_image_path == generation_image_path:
        print("编辑测试图片：使用刚生成的图片继续测试")
    else:
        print(f"编辑测试图片：{input_image_path}")
    run_edit(session, base_url, api_key, output_dir, input_image_path)
    print("\n两个接口都调用完成。")


if __name__ == "__main__":
    main()
