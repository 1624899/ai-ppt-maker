from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

import main
from ppt_system.integrations.model_connectivity import test_model_connectivity


class _FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict[str, Any] | None = None, text: str = "") -> None:
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self._payload = payload if payload is not None else {"ok": True}
        self.text = text

    def json(self) -> dict[str, Any]:
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class ModelConnectivityTests(unittest.TestCase):
    def test_chat_connectivity_posts_lightweight_completion(self) -> None:
        captured: dict[str, Any] = {}

        def fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: int):
            captured.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
            return _FakeResponse()

        profile = {
            "base_url": "https://example.com//v1/",
            "api_key": "sk-test",
            "model": "gpt-5.5",
            "reasoning_effort": "low",
        }
        with patch("ppt_system.integrations.model_connectivity.requests.post", side_effect=fake_post):
            result = test_model_connectivity("chat", profile, timeout=3)

        self.assertTrue(result.ok)
        self.assertEqual(captured["url"], "https://example.com/v1/chat/completions")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer sk-test")
        self.assertEqual(captured["json"]["model"], "gpt-5.5")
        self.assertEqual(captured["json"]["max_tokens"], 8)
        self.assertEqual(captured["json"]["reasoning_effort"], "low")
        self.assertEqual(captured["timeout"], 3)

    def test_image_connectivity_uses_models_endpoint_without_generation(self) -> None:
        captured: dict[str, Any] = {}

        def fake_get(url: str, *, headers: dict[str, str], timeout: int):
            captured.update({"url": url, "headers": headers, "timeout": timeout})
            return _FakeResponse()

        profile = {
            "base_url": "https://example.com/v1",
            "api_key": "sk-image",
            "model": "gpt-image-2",
        }
        with patch("ppt_system.integrations.model_connectivity.requests.get", side_effect=fake_get):
            result = test_model_connectivity("image", profile, timeout=5)

        self.assertTrue(result.ok)
        self.assertEqual(captured["url"], "https://example.com/v1/models")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer sk-image")
        self.assertEqual(captured["timeout"], 5)

    def test_connectivity_returns_readable_http_error(self) -> None:
        response = _FakeResponse(
            401,
            {
                "error": {
                    "message": "invalid api key",
                }
            },
        )
        with patch("ppt_system.integrations.model_connectivity.requests.post", return_value=response):
            result = test_model_connectivity(
                "chat",
                {
                    "base_url": "https://example.com/v1",
                    "api_key": "bad-key",
                    "model": "gpt-5.5",
                },
            )

        self.assertFalse(result.ok)
        self.assertEqual(result.status_code, 401)
        self.assertIn("invalid api key", result.message)


class ModelConnectivityApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = {
            "connectivity_test_timeout_seconds": 7,
            "model_configs": {
                "chat": [
                    {
                        "id": "chat_demo",
                        "name": "聊天模型",
                        "base_url": "https://example.com/v1",
                        "api_key": "sk-saved",
                        "model": "gpt-5.5",
                        "enabled": True,
                        "temperature": 0.3,
                        "max_tokens": 5000,
                        "reasoning_effort": "",
                    }
                ],
                "image": [],
            },
        }
        self.read_config_patch = patch.object(main, "read_config", return_value=self.config)
        self.read_config_patch.start()
        self.addCleanup(self.read_config_patch.stop)
        self.client = main.app.test_client()

    def test_api_tests_unsaved_form_payload(self) -> None:
        captured: dict[str, Any] = {}

        def fake_test(model_type: str, profile: dict[str, Any], *, timeout: int):
            captured.update({"model_type": model_type, "profile": profile, "timeout": timeout})

            class _Result:
                ok = True

                def to_dict(self):
                    return {"ok": True, "message": "ok", "elapsed_ms": 12}

            return _Result()

        with patch("ppt_system.web.services.config_api_service.test_model_connectivity", side_effect=fake_test):
            response = self.client.post(
                "/api/model-configs/chat/test",
                json={
                    "name": "临时模型",
                    "base_url": "https://example.com/v1",
                    "api_key": "sk-form",
                    "model": "gpt-5.5",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["model_type"], "chat")
        self.assertEqual(captured["profile"]["api_key"], "sk-form")
        self.assertEqual(captured["timeout"], 7)

    def test_api_reuses_saved_api_key_when_form_key_is_empty(self) -> None:
        captured: dict[str, Any] = {}

        def fake_test(model_type: str, profile: dict[str, Any], *, timeout: int):
            captured.update({"model_type": model_type, "profile": profile, "timeout": timeout})

            class _Result:
                ok = True

                def to_dict(self):
                    return {"ok": True, "message": "ok", "elapsed_ms": 8}

            return _Result()

        with patch("ppt_system.web.services.config_api_service.test_model_connectivity", side_effect=fake_test):
            response = self.client.post(
                "/api/model-configs/chat/test",
                json={
                    "id": "chat_demo",
                    "name": "聊天模型",
                    "base_url": "https://example.com/v1",
                    "api_key": "",
                    "model": "gpt-5.5",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["profile"]["api_key"], "sk-saved")


if __name__ == "__main__":
    unittest.main()
