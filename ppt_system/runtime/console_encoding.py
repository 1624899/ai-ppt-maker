from __future__ import annotations

import os
import sys


def configure_utf8_console() -> None:
    if os.name != "nt":
        return
    _reconfigure_stream(sys.stdout)
    _reconfigure_stream(sys.stderr)


def _reconfigure_stream(stream: object) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if not callable(reconfigure):
        return
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except ValueError:
        # 已关闭的流无需处理。
        return
