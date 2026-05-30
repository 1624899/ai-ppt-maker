from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ppt_system.integrations.image_response import decode_data_uri, resolve_image_bytes, save_image_from_response_payload


class _FakeHttpResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


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


if __name__ == "__main__":
    unittest.main()
