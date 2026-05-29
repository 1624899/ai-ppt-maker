from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import requests
from requests import RequestException

from ppt_system.api_url import normalize_api_base_url
from ppt_system.http_retry_policy import (
    build_transport_error_message,
    is_retryable_status_code,
    transport_retry_budget,
)
from ppt_system.image_response import save_image_from_response_payload


class OpenAIImageProvider:
    def __init__(self, config: dict[str, Any], profile: dict[str, Any] | None = None) -> None:
        profile = profile or {}
        self.api_key = str(profile.get("api_key", "")).strip()
        self.api_base_url = normalize_api_base_url(
            str(profile.get("base_url", config.get("api_base_url", "https://api.openai.com/v1")))
        )
        self.model = str(profile.get("model", config.get("image_model", "gpt-image-2")))
        self.size = str(config.get("active_image_size", config.get("image_size", "2048x1152")))
        self.pixel_size = f"{int(config.get('image_width', 2048))}x{int(config.get('image_height', 1152))}"
        self.resolution = str(config.get("active_image_resolution", config.get("image_resolution", "2k"))).lower()
        self.quality = str(config.get("image_quality", "high"))
        self.background = str(config.get("image_background", "opaque"))
        self.output_format = str(profile.get("output_format", config.get("image_output_format", "png")))
        self.response_format = str(config.get("image_response_format", "url")).strip()
        self.moderation = str(config.get("image_moderation", "low")).strip()
        self.n = int(config.get("image_n", 1))
        self.timeout = int(config.get("request_timeout_seconds", 600))
        self.total_timeout = int(config.get("request_total_timeout_seconds", 180))
        self.retry_count = int(config.get("request_retry_count", 3))
        self.transport_retry_count = int(config.get("request_transport_retry_count", 1))
        self.ambiguous_transport_retry_count = int(config.get("request_ambiguous_retry_count", 0))
        self.retry_initial_delay = float(config.get("request_retry_initial_delay_seconds", 5))

        if not self.api_key:
            raise RuntimeError("未在模型配置中填写生图模型 API Key。")

    @property
    def images_generations_url(self) -> str:
        return f"{self.api_base_url}/images/generations"

    @property
    def images_edits_url(self) -> str:
        return f"{self.api_base_url}/images/edits"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def generate_reference_page(
        self,
        prompt: str,
        output_path: Path,
        style_reference_paths: list[Path],
        reference_mode: str = "generation",
    ) -> dict[str, Any]:
        if reference_mode == "edit_with_refs" and style_reference_paths:
            prompt = prompt.rstrip() + "只继承视觉语言与风格，不复用原图的具体构图和布局。"
            return self._edit_with_references(
                prompt=prompt,
                output_path=output_path,
                image_paths=style_reference_paths,
                purpose="reference_page",
            )

        response = self._post_with_retry(
            self.images_generations_url,
            headers={**self._headers(), "Content-Type": "application/json"},
            json=self._image_payload(prompt, mode="generation"),
        )
        self._raise_for_image_error(response)
        result = self._save_response_image(response.json(), output_path)
        result["purpose"] = "reference_page"
        return result

    def generate_elements_page(
        self,
        prompt: str,
        reference_page_path: Path,
        output_path: Path,
    ) -> dict[str, Any]:
        return self._edit_with_references(
            prompt=prompt,
            output_path=output_path,
            image_paths=[reference_page_path],
            purpose="elements_page",
        )

    def _edit_with_references(
        self,
        prompt: str,
        output_path: Path,
        image_paths: list[Path],
        purpose: str,
    ) -> dict[str, Any]:
        files = []
        opened_files = []
        try:
            for image_path in image_paths:
                handle = image_path.open("rb")
                opened_files.append(handle)
                # 官方 Images Edits API 使用 image 字段；多图时重复该字段。
                files.append(("image", (image_path.name, handle, image_mime_type(image_path))))

            response = self._post_with_retry(
                self.images_edits_url,
                headers=self._headers(),
                data=self._image_payload(prompt, mode="edit"),
                files=files,
            )
            self._raise_for_image_error(response)
            result = self._save_response_image(response.json(), output_path)
            result["purpose"] = purpose
            result["input_images"] = [str(path) for path in image_paths]
            return result
        finally:
            for handle in opened_files:
                handle.close()

    def _image_payload(self, prompt: str, mode: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "size": self._resolve_size(),
            "n": self.n,
        }
        if mode == "edit":
            payload["background"] = self.background
            payload["response_format"] = self.response_format
            payload["moderation"] = self.moderation
            if self.quality:
                payload["quality"] = self.quality
        else:
            if self.quality:
                payload["quality"] = self.quality
        if mode == "generation" and self._supports_extended_options():
            payload["resolution"] = self.resolution
            payload["background"] = self.background
            payload["output_format"] = self.output_format
        return {key: value for key, value in payload.items() if value not in {"", None}}

    def _resolve_size(self) -> str:
        size = self.size.strip().lower()
        if "x" in size:
            return self.size
        if ":" in size:
            return self.pixel_size
        return self.size

    def _supports_extended_options(self) -> bool:
        base = self.api_base_url.lower()
        model = self.model.lower()
        if "anyaigc.com" in base:
            return False
        if model.endswith("-all"):
            return False
        return True

    def _post_with_retry(self, url: str, **kwargs: Any) -> requests.Response:
        last_response: requests.Response | None = None
        response_attempt = 0
        transport_attempt = 0
        deadline = time.monotonic() + max(1, self.total_timeout)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"图像接口请求超时：单次生图流程超过 {self.total_timeout} 秒，已停止自动重试")

            self._rewind_files(kwargs.get("files"))
            try:
                request_timeout = max(1.0, min(float(self.timeout), remaining))
                response = requests.post(url, timeout=request_timeout, **kwargs)
                last_response = response
                if not self._should_retry(response) or response_attempt >= self.retry_count:
                    return response

                retry_after = response.headers.get("Retry-After", "").strip()
                if retry_after.isdigit():
                    delay = float(retry_after)
                else:
                    delay = self.retry_initial_delay * (2**response_attempt)
                response_attempt += 1
                self._sleep_with_deadline(delay, deadline)
            except RequestException as exc:
                retry_budget = transport_retry_budget(
                    exc,
                    transport_retry_count=self.transport_retry_count,
                    ambiguous_transport_retry_count=self.ambiguous_transport_retry_count,
                )
                if transport_attempt >= retry_budget:
                    raise RuntimeError(build_transport_error_message(exc)) from exc
                delay = self.retry_initial_delay * (2**transport_attempt)
                transport_attempt += 1
                self._sleep_with_deadline(delay, deadline)
                continue

        return last_response

    @staticmethod
    def _rewind_files(files: Any) -> None:
        if not files:
            return
        for item in files:
            try:
                item[1][1].seek(0)
            except (AttributeError, IndexError, TypeError):
                continue

    @staticmethod
    def _should_retry(response: requests.Response) -> bool:
        return is_retryable_status_code(response.status_code)

    def _save_response_image(self, response_json: dict[str, Any], output_path: Path) -> dict[str, Any]:
        image = save_image_from_response_payload(
            response_json,
            output_path,
            timeout=min(self.timeout, self.total_timeout),
        )

        return {
            "provider": "openai_compatible",
            "model": self.model,
            "base_url": self.api_base_url,
            "size": self._resolve_size(),
            "resolution": self.resolution,
            "quality": self.quality,
            "background": self.background,
            "output_format": self.output_format,
            "revised_prompt": image.get("revised_prompt", ""),
        }

    @staticmethod
    def _raise_for_image_error(response: requests.Response) -> None:
        if response.ok:
            return
        try:
            body = response.json()
        except ValueError:
            body = response.text
        raise RuntimeError(f"图像接口请求失败：HTTP {response.status_code}，{body}")

    def _sleep_with_deadline(self, delay: float, deadline: float) -> None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(f"图像接口请求超时：单次生图流程超过 {self.total_timeout} 秒，已停止自动重试")
        time.sleep(min(delay, remaining))


def image_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"
