from __future__ import annotations

import json
import unittest
from typing import Any
from unittest.mock import patch

from ppt_system.model_config import sanitize_model_config
from ppt_system.openai_chat_provider import OpenAIChatProvider


class _FakeResponse:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.ok = True
        self.status_code = 200
        self._payload = payload or {
            "choices": [
                {
                    "message": {
                        "content": '{"page_script":"add_text(slide, \\"标题\\", 0, 0, 100, 40)"}'
                    }
                }
            ]
        }
        self.headers: dict[str, str] = {}
        self.text = ""
        self.content = json.dumps(self._payload, ensure_ascii=False).encode("utf-8")

    def json(self) -> dict[str, Any]:
        return self._payload


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

    def test_complete_json_includes_reasoning_effort_when_configured(self) -> None:
        config = {
            "chat_api_base_url": "https://example.com/v1",
            "chat_model": "gpt-5.5",
            "chat_temperature": 0.3,
            "chat_max_tokens": 2048,
            "chat_reasoning_effort": "high",
        }
        profile = {
            "api_key": "sk-test",
            "base_url": "https://example.com/v1",
            "model": "gpt-5.5",
            "temperature": 0.3,
            "max_tokens": 2048,
        }
        provider = OpenAIChatProvider(config, profile)

        captured_payload: dict[str, Any] = {}

        def fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: int):
            captured_payload.update(json)
            return _FakeResponse()

        with patch("ppt_system.openai_chat_provider.requests.post", side_effect=fake_post):
            result = provider.complete_json([{"role": "user", "content": "test"}])

        self.assertEqual(captured_payload["reasoning_effort"], "high")
        self.assertEqual(result["page_script"], 'add_text(slide, "标题", 0, 0, 100, 40)')

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

        with patch("ppt_system.openai_chat_provider.requests.post", side_effect=fake_post):
            provider.complete_json([{"role": "user", "content": "test"}])

        self.assertEqual(captured_payload["reasoning_effort"], "medium")

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
            "choices": [
                {
                    "message": {
                        "content": '{"page_script":"add_text(slide, \\"提问即竞争力\\", 0, 0, 100, 40)"}'
                    }
                }
            ]
        }
        response = _FakeResponse(payload)
        response.text = '{"page_script":"add_text(slide, \\"æé®å³ç«äºå\\", 0, 0, 100, 40)"}'

        with patch("ppt_system.openai_chat_provider.requests.post", return_value=response):
            result = provider.complete_json([{"role": "user", "content": "test"}])

        self.assertEqual(result["page_script"], 'add_text(slide, "提问即竞争力", 0, 0, 100, 40)')


if __name__ == "__main__":
    unittest.main()
