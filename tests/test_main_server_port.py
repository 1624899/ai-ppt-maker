from __future__ import annotations

import os
import socket
import unittest
from unittest.mock import patch

import main


class MainServerPortTests(unittest.TestCase):
    def test_uses_configured_available_port(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            available_port = probe.getsockname()[1]

        with patch.dict(os.environ, {"PPT_SYSTEM_PORT": str(available_port)}, clear=False):
            self.assertEqual(main.resolve_server_port(), available_port)

    def test_skips_occupied_preferred_port(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
            occupied.bind(("127.0.0.1", 0))
            preferred_port = occupied.getsockname()[1]
            with patch.dict(os.environ, {"PPT_SYSTEM_PORT": str(preferred_port)}, clear=False):
                selected = main.resolve_server_port()

        self.assertGreater(selected, preferred_port)
        self.assertLessEqual(selected, preferred_port + 20)


if __name__ == "__main__":
    unittest.main()
