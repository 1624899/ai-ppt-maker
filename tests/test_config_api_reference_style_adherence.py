from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import main


class ConfigApiReferenceStyleAdherenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_root = Path(self.temp_dir.name)
        self.config = {
            "max_pages": 10,
            "default_pages": 4,
            "default_image_preset": "landscape_2k",
            "image_presets": {
                "landscape_2k": {
                    "label": "2048x1152 · 16:9 2K 横图",
                    "width": 2048,
                    "height": 1152,
                    "size": "2048x1152",
                    "resolution": "",
                }
            },
            "image_width": 2048,
            "image_height": 1152,
            "generation_mode": "openai",
            "api_base_url": "https://example.com/v1",
            "image_model": "gpt-image-2",
            "image_size": "2048x1152",
            "image_resolution": "",
            "image_quality": "medium",
            "image_background": "opaque",
            "image_output_format": "png",
            "default_reference_style_adherence": "strict",
            "output_dir": str(self.temp_root / "runs"),
            "active_chat_config_id": "",
            "active_image_config_id": "",
        }
        self.read_config_patch = patch.object(main, "read_config", return_value=self.config)
        self.read_config_patch.start()
        self.addCleanup(self.read_config_patch.stop)
        self.client = main.app.test_client()

    def test_config_api_exposes_reference_style_adherence_defaults(self) -> None:
        response = self.client.get("/api/config")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        self.assertEqual(payload["default_reference_style_adherence"], "strict")
        self.assertEqual(
            payload["reference_style_adherence_options"],
            [
                {"value": "loose", "label": "宽松"},
                {"value": "balanced", "label": "适度"},
                {"value": "strict", "label": "严格"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
