from __future__ import annotations

import base64
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from ppt_system.integrations.openai_image_provider import OpenAIImageProvider
from ppt_system.integrations.image_response import decode_data_uri, resolve_image_bytes, save_image_from_response_payload


class _FakeHttpResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


def _png_bytes(size: tuple[int, int], color: tuple[int, int, int, int] = (64, 128, 192, 255)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


class ImageResponseTests(unittest.TestCase):
    def test_decode_data_uri_supports_base64_payload(self) -> None:
        raw = b"fake-png-bytes"
        data_uri = f"data:image/png;base64,{base64.b64encode(raw).decode('ascii')}"

        self.assertEqual(decode_data_uri(data_uri), raw)

    def test_decode_data_uri_supports_percent_encoded_payload(self) -> None:
        data_uri = "data:text/plain,hello%20world"

        self.assertEqual(decode_data_uri(data_uri), b"hello world")

    def test_resolve_image_bytes_reads_data_uri_from_url_field(self) -> None:
        raw = b"image-from-data-uri"
        payload = {
            "url": f"data:image/png;base64,{base64.b64encode(raw).decode('ascii')}",
        }

        self.assertEqual(resolve_image_bytes(payload, timeout=5), raw)

    def test_resolve_image_bytes_downloads_http_url(self) -> None:
        raw = b"image-from-http"
        with patch("ppt_system.integrations.image_response.requests.get", return_value=_FakeHttpResponse(raw)) as mock_get:
            result = resolve_image_bytes({"url": "https://example.com/test.png"}, timeout=5)

        self.assertEqual(result, raw)
        mock_get.assert_called_once_with("https://example.com/test.png", timeout=5)

    def test_save_image_from_response_payload_writes_file(self) -> None:
        raw = b"saved-image"
        response_json = {
            "data": [
                {
                    "url": f"data:image/png;base64,{base64.b64encode(raw).decode('ascii')}",
                    "revised_prompt": "test",
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "page.png"
            image = save_image_from_response_payload(response_json, output_path, timeout=5)

            self.assertEqual(output_path.read_bytes(), raw)
            self.assertEqual(image["revised_prompt"], "test")

    def test_provider_download_uses_independent_download_timeout(self) -> None:
        provider = OpenAIImageProvider(
            {
                "api_base_url": "https://example.com/v1",
                "image_model": "gpt-image-2",
                "request_timeout_seconds": 180,
                "request_total_timeout_seconds": 180,
                "image_download_timeout_seconds": 30,
            },
            {"api_key": "test-key"},
        )
        response_json = {"data": [{"url": "https://example.com/test.png"}]}

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "page.png"
            def fake_save(_response_json, saved_path, *, timeout):
                saved_path.write_bytes(_png_bytes((2048, 1152)))
                return response_json["data"][0]

            with patch(
                "ppt_system.integrations.openai_image_provider.save_image_from_response_payload",
                side_effect=fake_save,
            ) as mock_save:
                provider._save_response_image(response_json, output_path)

        self.assertEqual(mock_save.call_args.kwargs["timeout"], 30)

    def test_provider_normalizes_saved_image_to_config_canvas(self) -> None:
        provider = OpenAIImageProvider(
            {
                "api_base_url": "https://example.com/v1",
                "image_model": "gpt-image-2",
                "image_width": 64,
                "image_height": 36,
                "image_size": "64x36",
                "image_response_format": "b64_json",
            },
            {"api_key": "test-key"},
        )
        response_json = {
            "data": [
                {
                    "b64_json": base64.b64encode(_png_bytes((32, 32))).decode("ascii"),
                    "revised_prompt": "test",
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "page.png"
            result = provider._save_response_image(response_json, output_path)

            with Image.open(output_path) as image:
                self.assertEqual(image.size, (64, 36))

        self.assertEqual(result["canvas"], {"width": 64, "height": 36})
        self.assertTrue(result["canvas_normalization"]["normalized"])
        self.assertEqual(result["canvas_normalization"]["source_size"], {"width": 32, "height": 32})


if __name__ == "__main__":
    unittest.main()
