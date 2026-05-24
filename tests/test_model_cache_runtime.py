from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ppt_system.model_cache_runtime import configure_model_cache_environment, resolve_model_cache_root


class ModelCacheRuntimeTests(unittest.TestCase):
    def test_configured_relative_cache_root_resolves_under_project(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("U2NET_HOME", None)
                resolved = resolve_model_cache_root(
                    project_root,
                    {"model_cache_root": "output/model_cache"},
                )

            self.assertEqual(resolved, (project_root / "output" / "model_cache").resolve())

    def test_environment_override_keeps_parent_cache_root(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            env_home = project_root / "custom_cache" / "u2net"

            with patch.dict(os.environ, {"U2NET_HOME": str(env_home)}, clear=False):
                resolved = resolve_model_cache_root(project_root, {})

            self.assertEqual(resolved, env_home.parent.resolve())

    def test_configure_environment_exports_project_scoped_u2net_home(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("U2NET_HOME", None)
                u2net_home = configure_model_cache_environment(
                    project_root=project_root,
                    config={"model_cache_root": "output/model_cache"},
                )

                self.assertEqual(
                    u2net_home,
                    (project_root / "output" / "model_cache" / "u2net").resolve(),
                )
                self.assertEqual(os.environ["U2NET_HOME"], str(u2net_home))
                self.assertTrue(u2net_home.exists())


if __name__ == "__main__":
    unittest.main()
