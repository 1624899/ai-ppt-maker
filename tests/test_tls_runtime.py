from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ppt_system.runtime.tls_runtime import configure_ca_bundle


class TlsRuntimeTests(unittest.TestCase):
    def test_preserves_explicit_requests_ca_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            configured = str(Path(directory) / "company-ca.pem")
            with patch.dict(os.environ, {"REQUESTS_CA_BUNDLE": configured, "SSL_CERT_FILE": ""}, clear=False):
                resolved = configure_ca_bundle()

            self.assertEqual(resolved, configured)

    def test_uses_certifi_when_no_ca_is_configured(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            resolved = configure_ca_bundle()

            self.assertTrue(resolved)
            self.assertEqual(os.environ["REQUESTS_CA_BUNDLE"], resolved)
            self.assertEqual(os.environ["SSL_CERT_FILE"], resolved)
            self.assertTrue(Path(resolved).is_file())


if __name__ == "__main__":
    unittest.main()
