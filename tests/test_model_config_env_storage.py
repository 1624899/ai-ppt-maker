from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from ppt_system.integrations.model_config import (
    delete_model_api_key,
    list_model_configs,
    read_config,
    resolve_writable_config_path,
    resolve_model_api_key_env_name,
    save_model_api_key,
    upsert_model_config,
    write_config,
)


class ModelConfigEnvStorageTests(unittest.TestCase):
    def test_write_config_strips_api_key_and_read_config_hydrates_from_env(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config.json"
            env_path = root / ".env"
            config = {
                "model_configs": {
                    "chat": [
                        {
                            "id": "chat_demo",
                            "name": "聊天模型",
                            "base_url": "https://example.com/v1",
                            "api_key": "sk-chat",
                            "model": "gpt-5.5",
                            "enabled": True,
                            "temperature": 0.3,
                            "max_tokens": 5000,
                            "reasoning_effort": "",
                        }
                    ],
                    "image": [],
                }
            }

            save_model_api_key(env_path, "chat", config["model_configs"]["chat"][0])
            write_config(config_path, config)

            self.assertIn("PPT_SYSTEM_CHAT_CHAT_DEMO_API_KEY=sk-chat", env_path.read_text(encoding="utf-8"))
            self.assertIn('"api_key": "__ENV__"', config_path.read_text(encoding="utf-8"))

            hydrated = read_config(config_path)
            self.assertEqual(hydrated["model_configs"]["chat"][0]["api_key"], "sk-chat")

    def test_list_model_configs_hides_plaintext_api_key(self) -> None:
        config = {
            "model_configs": {
                "chat": [
                    {
                        "id": "chat_demo",
                        "name": "聊天模型",
                        "base_url": "https://example.com/v1",
                        "api_key": "sk-chat",
                        "model": "gpt-5.5",
                        "enabled": True,
                        "temperature": 0.3,
                        "max_tokens": 5000,
                        "reasoning_effort": "",
                    }
                ],
                "image": [],
            }
        }

        listed = list_model_configs(config)
        self.assertEqual(listed["chat"][0]["api_key"], "sk-chat")
        self.assertTrue(listed["chat"][0]["api_key_configured"])
        self.assertEqual(listed["chat"][0]["api_key_preview"], "sk***at")

    def test_delete_model_api_key_removes_env_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            item = {
                "id": "image_demo",
                "name": "生图模型",
                "api_key": "sk-image",
            }
            save_model_api_key(env_path, "image", item)
            env_name = resolve_model_api_key_env_name("image", item)
            self.assertEqual(os.environ.get(env_name), "sk-image")

            delete_model_api_key(env_path, "image", item)

            self.assertNotIn(env_name, os.environ)
            self.assertEqual(env_path.read_text(encoding="utf-8"), "")

    def test_update_image_model_config_keeps_existing_capability_flag_when_omitted(self) -> None:
        config = {
            "model_configs": {
                "chat": [],
                "image": [
                    {
                        "id": "image_demo",
                        "name": "生图模型",
                        "base_url": "https://example.com/v1",
                        "api_key": "sk-image",
                        "model": "gpt-image-2",
                        "enabled": True,
                        "output_format": "png",
                        "supports_extended_options": False,
                    }
                ],
            }
        }

        updated = upsert_model_config(
            config,
            "image",
            {
                "name": "生图模型",
                "base_url": "https://example.com/v1",
                "api_key": "",
                "model": "gpt-image-2",
                "enabled": True,
                "output_format": "png",
            },
            config_id="image_demo",
        )

        self.assertFalse(updated["supports_extended_options"])

    def test_read_config_merges_local_override_without_losing_template_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config.json"
            local_config_path = root / "config.local.json"
            config_path.write_text(
                """
{
  "max_pages": 10,
  "default_pages": 4,
  "active_chat_config_id": "chat_template",
  "model_configs": {
    "chat": [
      {
        "id": "chat_template",
        "name": "模板模型",
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "model": "gpt-5.5",
        "enabled": true,
        "temperature": 0.3,
        "max_tokens": 5000,
        "reasoning_effort": ""
      }
    ],
    "image": []
  }
}
""".strip(),
                encoding="utf-8",
            )
            local_config_path.write_text(
                """
{
  "default_pages": 6,
  "active_chat_config_id": "chat_local",
  "model_configs": {
    "chat": [
      {
        "id": "chat_local",
        "name": "本地模型",
        "base_url": "https://example.test/v1",
        "api_key": "",
        "model": "local-chat",
        "enabled": true,
        "temperature": 0.2,
        "max_tokens": 3000,
        "reasoning_effort": ""
      }
    ],
    "image": []
  }
}
""".strip(),
                encoding="utf-8",
            )

            config = read_config(config_path)

            self.assertEqual(config["max_pages"], 10)
            self.assertEqual(config["default_pages"], 6)
            self.assertEqual(config["active_chat_config_id"], "chat_local")
            self.assertEqual(config["model_configs"]["chat"][0]["base_url"], "https://example.test/v1")

    def test_write_config_prefers_existing_local_override_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config.json"
            local_config_path = root / "config.local.json"
            config_path.write_text('{"default_pages": 4, "model_configs": {"chat": [], "image": []}}', encoding="utf-8")
            local_config_path.write_text('{"default_pages": 6, "model_configs": {"chat": [], "image": []}}', encoding="utf-8")

            self.assertEqual(resolve_writable_config_path(config_path), local_config_path)
            write_config(config_path, {"default_pages": 8, "model_configs": {"chat": [], "image": []}})

            self.assertIn('"default_pages": 4', config_path.read_text(encoding="utf-8"))
            self.assertIn('"default_pages": 8', local_config_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
