from __future__ import annotations

import unittest

from ppt_system.integrations.responses_payload import build_responses_input


class ResponsesPayloadTests(unittest.TestCase):
    def test_build_responses_input_keeps_responses_content_items(self) -> None:
        result = build_responses_input(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "分析这张图"},
                        {"type": "input_image", "image_url": "data:image/png;base64,stub"},
                    ],
                }
            ]
        )

        self.assertEqual(
            result,
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "分析这张图"},
                        {"type": "input_image", "image_url": "data:image/png;base64,stub"},
                    ],
                }
            ],
        )

    def test_build_responses_input_rejects_legacy_content_item_types(self) -> None:
        legacy_messages = [
            {
                "role": "user",
                "content": [{"type": "text", "text": "旧格式"}],
            }
        ]

        with self.assertRaisesRegex(ValueError, "旧内容块类型"):
            build_responses_input(legacy_messages)


if __name__ == "__main__":
    unittest.main()
