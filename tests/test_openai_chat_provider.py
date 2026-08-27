from __future__ import annotations

import json
import unittest
from http.client import RemoteDisconnected
from typing import Any
from unittest.mock import patch

from requests.exceptions import ConnectTimeout, ConnectionError, ReadTimeout

from ppt_system.integrations.model_config import sanitize_model_config
from ppt_system.integrations.openai_chat_provider import OpenAIChatProvider


class _FakeResponse:
    def __init__(self, payload: dict[str, Any] | None = None, *, status_code: int = 200) -> None:
        self.ok = 200 <= int(status_code) < 400
        self.status_code = int(status_code)
        self._payload = payload or {
            "id": "resp_test",
            "object": "response",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"page_script":"add_text(slide, \\"标题\\", 0, 0, 100, 40)"}',
                        }
                    ],
                }
            ],
        }
        self.headers: dict[str, str] = {}
        self.text = ""
        self.content = json.dumps(self._payload, ensure_ascii=False).encode("utf-8")

    def json(self) -> dict[str, Any]:
        return self._payload


class _BrokenJsonResponse(_FakeResponse):
    def __init__(self, *, text: str = "", content: bytes = b"") -> None:
        super().__init__({})
        self.text = text
        self.content = content

    def json(self) -> dict[str, Any]:
        raise json.JSONDecodeError("Expecting value", self.text or "", 0)


class OpenAIChatProviderTests(unittest.TestCase):
    def test_sanitize_model_config_keeps_reasoning_effort(self) -> None:
        item = sanitize_model_config(
            "chat",
            {
                "name": "gpt-5.5",
                "base_url": "https://example.com/v1",
                "api_key": "sk-test",
                "model": "gpt-5.5",
                "reasoning_effort": "medium",
            },
        )

        self.assertEqual(item["reasoning_effort"], "medium")

    def test_sanitize_model_config_discards_invalid_reasoning_effort(self) -> None:
        item = sanitize_model_config(
            "chat",
            {
                "name": "gpt-5.5",
                "base_url": "https://example.com/v1",
                "api_key": "sk-test",
                "model": "gpt-5.5",
                "reasoning_effort": "extreme",
            },
        )

        self.assertEqual(item["reasoning_effort"], "")

    def test_sanitize_model_config_ignores_obsolete_sampling_fields(self) -> None:
        item = sanitize_model_config(
            "chat",
            {
                "name": "gpt-5.5",
                "base_url": "https://example.com/v1",
                "api_key": "sk-test",
                "model": "gpt-5.5",
                "temperature": 0.7,
                "max_tokens": 9999,
                "reasoning_effort": "medium",
            },
        )

        self.assertNotIn("temperature", item)
        self.assertNotIn("max_tokens", item)
        self.assertEqual(item["reasoning_effort"], "medium")

    def test_sanitize_model_config_normalizes_base_url_path(self) -> None:
        item = sanitize_model_config(
            "chat",
            {
                "name": "gpt-5.5",
                "base_url": "https://example.com//gateway//v1/",
                "api_key": "sk-test",
                "model": "gpt-5.5",
            },
        )

        self.assertEqual(item["base_url"], "https://example.com/gateway/v1")

    def test_complete_json_builds_responses_payload_with_reasoning_when_configured(self) -> None:
        config = {
            "chat_api_base_url": "https://example.com/v1",
            "chat_model": "gpt-5.5",
            "chat_reasoning_effort": "high",
        }
        profile = {
            "api_key": "sk-test",
            "base_url": "https://example.com/v1",
            "model": "gpt-5.5",
        }
        provider = OpenAIChatProvider(config, profile)

        captured_payload: dict[str, Any] = {}

        def fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: int):
            captured_payload.update(json)
            return _FakeResponse()

        with patch("ppt_system.integrations.openai_chat_provider.requests.post", side_effect=fake_post):
            result = provider.complete_json([{"role": "user", "content": "test"}])

        self.assertEqual(captured_payload["reasoning"], {"effort": "high"})
        self.assertEqual(captured_payload["text"], {"format": {"type": "json_object"}})
        self.assertEqual(captured_payload["stream"], True)
        self.assertEqual(captured_payload["store"], False)
        self.assertNotIn("messages", captured_payload)
        self.assertNotIn("max_tokens", captured_payload)
        self.assertNotIn("max_output_tokens", captured_payload)
        self.assertNotIn("temperature", captured_payload)
        self.assertNotIn("response_format", captured_payload)
        self.assertEqual(result["page_script"], 'add_text(slide, "标题", 0, 0, 100, 40)')

    def test_complete_json_normalizes_profile_base_url_before_request(self) -> None:
        config = {
            "chat_api_base_url": "https://example.com/v1",
        }
        profile = {
            "api_key": "sk-test",
            "base_url": "https://example.com//gateway//v1/",
            "model": "gpt-5.5",
        }
        provider = OpenAIChatProvider(config, profile)

        captured_url = ""

        def fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: int):
            nonlocal captured_url
            captured_url = url
            return _FakeResponse()

        with patch("ppt_system.integrations.openai_chat_provider.requests.post", side_effect=fake_post):
            provider.complete_json([{"role": "user", "content": "test"}])

        self.assertEqual(captured_url, "https://example.com/gateway/v1/responses")

    def test_complete_json_uses_profile_reasoning_effort_over_global_default(self) -> None:
        config = {
            "chat_api_base_url": "https://example.com/v1",
            "chat_reasoning_effort": "low",
        }
        profile = {
            "api_key": "sk-test",
            "base_url": "https://example.com/v1",
            "model": "gpt-5.5",
            "reasoning_effort": "medium",
        }
        provider = OpenAIChatProvider(config, profile)

        captured_payload: dict[str, Any] = {}

        def fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: int):
            captured_payload.update(json)
            return _FakeResponse()

        with patch("ppt_system.integrations.openai_chat_provider.requests.post", side_effect=fake_post):
            provider.complete_json([{"role": "user", "content": "test"}])

        self.assertEqual(captured_payload["reasoning"], {"effort": "medium"})

    def test_complete_json_prefers_utf8_response_body_when_text_decoding_is_garbled(self) -> None:
        config = {
            "chat_api_base_url": "https://example.com/v1",
        }
        profile = {
            "api_key": "sk-test",
            "base_url": "https://example.com/v1",
            "model": "gpt-5.5",
        }
        provider = OpenAIChatProvider(config, profile)

        payload = {
            "id": "resp_utf8",
            "object": "response",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"page_script":"add_text(slide, \\"提问即竞争力\\", 0, 0, 100, 40)"}',
                        }
                    ],
                }
            ],
        }
        response = _FakeResponse(payload)
        response.text = '{"page_script":"add_text(slide, \\"æé®å³ç«äºå\\", 0, 0, 100, 40)"}'

        with patch("ppt_system.integrations.openai_chat_provider.requests.post", return_value=response):
            result = provider.complete_json([{"role": "user", "content": "test"}])

        self.assertEqual(result["page_script"], 'add_text(slide, "提问即竞争力", 0, 0, 100, 40)')

    def test_complete_json_wraps_non_json_http_200_response(self) -> None:
        config = {
            "chat_api_base_url": "https://example.com/v1",
        }
        profile = {
            "api_key": "sk-test",
            "base_url": "https://example.com/v1",
            "model": "gpt-5.5",
        }
        provider = OpenAIChatProvider(config, profile)
        response = _BrokenJsonResponse(text="<html>upstream error</html>", content=b"<html>upstream error</html>")

        with patch("ppt_system.integrations.openai_chat_provider.requests.post", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "非 JSON 响应"):
                provider.complete_json([{"role": "user", "content": "test"}])

    def test_complete_json_rejects_empty_message_content(self) -> None:
        config = {
            "chat_api_base_url": "https://example.com/v1",
        }
        profile = {
            "api_key": "sk-test",
            "base_url": "https://example.com/v1",
            "model": "gpt-5.5",
        }
        provider = OpenAIChatProvider(
            config,
            profile,
        )
        response = _FakeResponse(
            {
                "id": "resp_empty",
                "object": "response",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [],
                    }
                ],
            }
        )

        with patch("ppt_system.integrations.openai_chat_provider.requests.post", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "未返回可用文本内容"):
                provider.complete_json([{"role": "user", "content": "test"}])

    def test_complete_json_accepts_segmented_message_content(self) -> None:
        config = {
            "chat_api_base_url": "https://example.com/v1",
        }
        profile = {
            "api_key": "sk-test",
            "base_url": "https://example.com/v1",
            "model": "gpt-5.5",
        }
        provider = OpenAIChatProvider(config, profile)
        response = _FakeResponse(
            {
                "id": "resp_segmented",
                "object": "response",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": '{"page_script":"add_text(slide, \\"标题\\", '},
                            {"type": "output_text", "text": '0, 0, 100, 40)"}'},
                        ],
                    }
                ],
            }
        )

        with patch("ppt_system.integrations.openai_chat_provider.requests.post", return_value=response):
            result = provider.complete_json([{"role": "user", "content": "test"}])

        self.assertEqual(result["page_script"], 'add_text(slide, "标题", 0, 0, 100, 40)')

    def test_complete_json_accepts_top_level_output_text(self) -> None:
        config = {
            "chat_api_base_url": "https://example.com/v1",
        }
        profile = {
            "api_key": "sk-test",
            "base_url": "https://example.com/v1",
            "model": "gpt-5.5",
        }
        provider = OpenAIChatProvider(config, profile)
        response = _FakeResponse(
            {
                "output_text": '{"page_script":"add_text(slide, \\"标题\\", 0, 0, 100, 40)"}',
            }
        )

        with patch("ppt_system.integrations.openai_chat_provider.requests.post", return_value=response):
            result = provider.complete_json([{"role": "user", "content": "test"}])

        self.assertEqual(result["page_script"], 'add_text(slide, "标题", 0, 0, 100, 40)')

    def test_complete_json_accepts_sse_response_api_events(self) -> None:
        config = {
            "chat_api_base_url": "https://example.com/v1",
        }
        profile = {
            "api_key": "sk-test",
            "base_url": "https://example.com/v1",
            "model": "gpt-5.5",
        }
        provider = OpenAIChatProvider(config, profile)
        events = [
            {
                "type": "response.output_text.delta",
                "delta": '{"page_script":"add_text(slide, \\"标题\\", ',
            },
            {
                "type": "response.output_text.delta",
                "delta": '0, 0, 100, 40)"}',
            },
            {
                "type": "response.completed",
                "response": {
                    "id": "resp_stream",
                    "object": "response",
                    "status": "completed",
                    "usage": {"total_tokens": 12},
                },
            },
        ]
        sse_text = "\n\n".join(f"data: {json.dumps(event, ensure_ascii=False)}" for event in events)
        sse_text = f"{sse_text}\n\ndata: [DONE]\n\n"
        response = _BrokenJsonResponse(text=sse_text, content=sse_text.encode("utf-8"))

        with patch("ppt_system.integrations.openai_chat_provider.requests.post", return_value=response):
            result = provider.complete_json([{"role": "user", "content": "test"}])

        self.assertEqual(result["page_script"], 'add_text(slide, "标题", 0, 0, 100, 40)')

    def test_complete_json_retries_ambiguous_empty_response_once(self) -> None:
        config = {
            "chat_api_base_url": "https://example.com/v1",
            "request_retry_initial_delay_seconds": 0,
        }
        profile = {
            "api_key": "sk-test",
            "base_url": "https://example.com/v1",
            "model": "gpt-5.5",
        }
        provider = OpenAIChatProvider(config, profile)
        responses = [
            _FakeResponse(
                {
                    "id": "resp_empty",
                    "object": "response",
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "status": "completed",
                            "content": [],
                        }
                    ],
                }
            ),
            _FakeResponse(),
        ]

        with patch("ppt_system.integrations.openai_chat_provider.time.sleep", return_value=None):
            with patch("ppt_system.integrations.openai_chat_provider.requests.post", side_effect=responses) as mock_post:
                result = provider.complete_json([{"role": "user", "content": "test"}])

        self.assertEqual(result["page_script"], 'add_text(slide, "标题", 0, 0, 100, 40)')
        self.assertEqual(mock_post.call_count, 2)

    def test_complete_json_logs_ambiguous_empty_response_reason_before_retry(self) -> None:
        config = {
            "chat_api_base_url": "https://example.com/v1",
            "request_retry_initial_delay_seconds": 0,
        }
        profile = {
            "api_key": "sk-test",
            "base_url": "https://example.com/v1",
            "model": "gpt-5.5",
        }
        provider = OpenAIChatProvider(config, profile)
        responses = [
            _FakeResponse(
                {
                    "id": "resp_empty",
                    "object": "response",
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "status": "completed",
                            "content": [],
                        }
                    ],
                }
            ),
            _FakeResponse(),
        ]

        with patch("ppt_system.integrations.openai_chat_provider.time.sleep", return_value=None):
            with patch("ppt_system.integrations.openai_chat_provider.print") as mock_print:
                with patch("ppt_system.integrations.openai_chat_provider.requests.post", side_effect=responses):
                    provider.complete_json([{"role": "user", "content": "test"}])

        log_text = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("检测到歧义空响应", log_text)
        self.assertIn("status=completed", log_text)
        self.assertIn("resp_empty", log_text)

    def test_complete_json_does_not_retry_billable_empty_response(self) -> None:
        config = {
            "chat_api_base_url": "https://example.com/v1",
            "request_retry_initial_delay_seconds": 0,
        }
        profile = {
            "api_key": "sk-test",
            "base_url": "https://example.com/v1",
            "model": "gpt-5.5",
        }
        provider = OpenAIChatProvider(config, profile)
        response = _FakeResponse(
            {
                "id": "resp_billable_empty",
                "object": "response",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [],
                    }
                ],
                "usage": {
                    "input_tokens": 10486,
                    "output_tokens": 4625,
                    "total_tokens": 15111,
                },
            }
        )

        with patch("ppt_system.integrations.openai_chat_provider.time.sleep", return_value=None):
            with patch("ppt_system.integrations.openai_chat_provider.print") as mock_print:
                with patch("ppt_system.integrations.openai_chat_provider.requests.post", return_value=response) as mock_post:
                    with self.assertRaisesRegex(RuntimeError, "避免重复扣费"):
                        provider.complete_json([{"role": "user", "content": "test"}])

        log_text = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("可能已计费的歧义空响应", log_text)
        self.assertIn("resp_billable_empty", log_text)
        self.assertIn("output_tokens=4625", log_text)
        self.assertEqual(mock_post.call_count, 1)

    def test_complete_json_retries_http_502_with_chat_retry_budget(self) -> None:
        config = {
            "chat_api_base_url": "https://example.com/v1",
            "chat_retry_count": 1,
            "request_retry_initial_delay_seconds": 0,
        }
        profile = {
            "api_key": "sk-test",
            "base_url": "https://example.com/v1",
            "model": "gpt-5.5",
        }
        provider = OpenAIChatProvider(config, profile)

        with patch("ppt_system.integrations.openai_chat_provider.time.sleep", return_value=None):
            with patch(
                "ppt_system.integrations.openai_chat_provider.requests.post",
                side_effect=[_FakeResponse(status_code=502), _FakeResponse()],
            ) as mock_post:
                result = provider.complete_json([{"role": "user", "content": "test"}])

        self.assertEqual(result["page_script"], 'add_text(slide, "标题", 0, 0, 100, 40)')
        self.assertEqual(mock_post.call_count, 2)

    def test_complete_json_retries_connection_setup_error_once(self) -> None:
        config = {
            "chat_api_base_url": "https://example.com/v1",
            "chat_retry_count": 0,
            "chat_transport_retry_count": 1,
            "chat_ambiguous_transport_retry_count": 0,
            "request_retry_initial_delay_seconds": 0,
        }
        profile = {
            "api_key": "sk-test",
            "base_url": "https://example.com/v1",
            "model": "gpt-5.5",
        }
        provider = OpenAIChatProvider(config, profile)

        with patch("ppt_system.integrations.openai_chat_provider.time.sleep", return_value=None):
            with patch(
                "ppt_system.integrations.openai_chat_provider.requests.post",
                side_effect=[ConnectTimeout("connect timeout"), _FakeResponse()],
            ) as mock_post:
                result = provider.complete_json([{"role": "user", "content": "test"}])

        self.assertEqual(result["page_script"], 'add_text(slide, "标题", 0, 0, 100, 40)')
        self.assertEqual(mock_post.call_count, 2)

    def test_complete_json_does_not_blindly_retry_read_timeout_by_default(self) -> None:
        config = {
            "chat_api_base_url": "https://example.com/v1",
            "chat_retry_count": 3,
            "chat_transport_retry_count": 1,
            "chat_ambiguous_transport_retry_count": 0,
            "request_retry_initial_delay_seconds": 0,
        }
        profile = {
            "api_key": "sk-test",
            "base_url": "https://example.com/v1",
            "model": "gpt-5.5",
        }
        provider = OpenAIChatProvider(config, profile)

        with patch("ppt_system.integrations.openai_chat_provider.time.sleep", return_value=None):
            with patch(
                "ppt_system.integrations.openai_chat_provider.requests.post",
                side_effect=ReadTimeout("read timeout"),
            ) as mock_post:
                with self.assertRaisesRegex(RuntimeError, "已停止自动重试"):
                    provider.complete_json([{"role": "user", "content": "test"}])

        self.assertEqual(mock_post.call_count, 1)

    def test_complete_json_does_not_blindly_retry_remote_disconnect_by_default(self) -> None:
        config = {
            "chat_api_base_url": "https://example.com/v1",
            "chat_retry_count": 3,
            "chat_transport_retry_count": 1,
            "chat_ambiguous_transport_retry_count": 0,
            "request_retry_initial_delay_seconds": 0,
        }
        profile = {
            "api_key": "sk-test",
            "base_url": "https://example.com/v1",
            "model": "gpt-5.5",
        }
        provider = OpenAIChatProvider(config, profile)

        with patch("ppt_system.integrations.openai_chat_provider.time.sleep", return_value=None):
            with patch(
                "ppt_system.integrations.openai_chat_provider.requests.post",
                side_effect=ConnectionError(
                    "Connection aborted.",
                    RemoteDisconnected("Remote end closed connection without response"),
                ),
            ) as mock_post:
                with self.assertRaisesRegex(RuntimeError, "已停止自动重试"):
                    provider.complete_json([{"role": "user", "content": "test"}])

        self.assertEqual(mock_post.call_count, 1)

    def test_complete_json_logs_transport_error_details_before_stopping_retry(self) -> None:
        config = {
            "chat_api_base_url": "https://example.com/v1",
            "chat_retry_count": 3,
            "chat_transport_retry_count": 1,
            "chat_ambiguous_transport_retry_count": 0,
            "request_retry_initial_delay_seconds": 0,
        }
        profile = {
            "api_key": "sk-test",
            "base_url": "https://example.com/v1",
            "model": "gpt-5.5",
        }
        provider = OpenAIChatProvider(config, profile)

        with patch("ppt_system.integrations.openai_chat_provider.time.sleep", return_value=None):
            with patch("ppt_system.integrations.openai_chat_provider.print") as mock_print:
                with patch(
                    "ppt_system.integrations.openai_chat_provider.requests.post",
                    side_effect=ConnectionError(
                        "Connection aborted.",
                        RemoteDisconnected("Remote end closed connection without response"),
                    ),
                ):
                    with self.assertRaisesRegex(RuntimeError, "已停止自动重试"):
                        provider.complete_json([{"role": "user", "content": "test"}])

        log_text = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("ConnectionError", log_text)
        self.assertIn("RemoteDisconnected", log_text)
        self.assertIn("请求异常已停止自动重试", log_text)


if __name__ == "__main__":
    unittest.main()
