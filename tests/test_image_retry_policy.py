from __future__ import annotations

import unittest
from http.client import RemoteDisconnected
from unittest.mock import patch

from requests import Response
from requests.exceptions import ConnectTimeout, ConnectionError

from ppt_system.integrations.openai_image_provider import OpenAIImageProvider


def build_response(status_code: int) -> Response:
    response = Response()
    response.status_code = status_code
    response._content = b'{"data":[]}'
    return response


class ImageRetryPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = OpenAIImageProvider(
            {
                "api_base_url": "https://example.com/v1",
                "image_model": "gpt-image-2",
                "request_timeout_seconds": 30,
                "request_total_timeout_seconds": 180,
                "request_retry_count": 1,
                "request_transport_retry_count": 1,
                "request_ambiguous_retry_count": 0,
                "request_retry_initial_delay_seconds": 0,
            },
            {"api_key": "test-key"},
        )

    @patch("ppt_system.integrations.openai_image_provider.time.sleep", return_value=None)
    @patch("ppt_system.integrations.openai_image_provider.requests.post")
    def test_remote_disconnected_does_not_blindly_retry(self, mock_post, _mock_sleep) -> None:
        mock_post.side_effect = ConnectionError(
            "Connection aborted.",
            RemoteDisconnected("Remote end closed connection without response"),
        )

        with self.assertRaises(RuntimeError) as ctx:
            self.provider._post_with_retry("https://example.com/v1/images/generations")

        self.assertEqual(mock_post.call_count, 1)
        self.assertIn("已停止自动重试", str(ctx.exception))

    @patch("ppt_system.integrations.openai_image_provider.time.sleep", return_value=None)
    @patch("ppt_system.integrations.openai_image_provider.requests.post")
    def test_connection_setup_error_can_retry_once(self, mock_post, _mock_sleep) -> None:
        mock_post.side_effect = [
            ConnectTimeout("connect timeout"),
            build_response(200),
        ]

        response = self.provider._post_with_retry("https://example.com/v1/images/generations")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_post.call_count, 2)

    @patch("ppt_system.integrations.openai_image_provider.time.sleep", return_value=None)
    @patch("ppt_system.integrations.openai_image_provider.requests.post")
    def test_http_retry_still_respects_retryable_status_codes(self, mock_post, _mock_sleep) -> None:
        mock_post.side_effect = [
            build_response(503),
            build_response(200),
        ]

        response = self.provider._post_with_retry("https://example.com/v1/images/generations")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_post.call_count, 2)

    def test_provider_normalizes_profile_base_url(self) -> None:
        provider = OpenAIImageProvider(
            {
                "api_base_url": "https://example.com/v1",
                "image_model": "gpt-image-2",
            },
            {
                "api_key": "test-key",
                "base_url": "https://example.com//gateway//v1/",
            },
        )

        self.assertEqual(provider.api_base_url, "https://example.com/gateway/v1")
        self.assertEqual(provider.images_generations_url, "https://example.com/gateway/v1/images/generations")

    def test_provider_caps_image_timeouts_to_180_seconds(self) -> None:
        provider = OpenAIImageProvider(
            {
                "api_base_url": "https://example.com/v1",
                "image_model": "gpt-image-2",
                "request_timeout_seconds": 600,
                "request_total_timeout_seconds": 600,
                "image_download_timeout_seconds": 600,
            },
            {"api_key": "test-key"},
        )

        self.assertEqual(provider.timeout, 180)
        self.assertEqual(provider.total_timeout, 180)
        self.assertEqual(provider.image_download_timeout, 180)

    def test_extended_generation_options_are_config_driven(self) -> None:
        provider = OpenAIImageProvider(
            {
                "api_base_url": "https://example.com/v1",
                "image_model": "gpt-image-2",
                "image_supports_extended_options": False,
            },
            {"api_key": "test-key"},
        )

        payload = provider._image_payload("测试提示词", mode="generation")

        self.assertNotIn("resolution", payload)
        self.assertNotIn("background", payload)
        self.assertNotIn("output_format", payload)

    def test_profile_can_enable_extended_generation_options(self) -> None:
        provider = OpenAIImageProvider(
            {
                "api_base_url": "https://example.com/v1",
                "image_model": "gpt-image-2-all",
                "image_supports_extended_options": False,
                "image_resolution": "2k",
            },
            {
                "api_key": "test-key",
                "supports_extended_options": True,
            },
        )

        payload = provider._image_payload("测试提示词", mode="generation")

        self.assertEqual(payload["resolution"], "2k")
        self.assertEqual(payload["background"], "opaque")
        self.assertEqual(payload["output_format"], "png")


if __name__ == "__main__":
    unittest.main()
