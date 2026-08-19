from __future__ import annotations

import os
import sys
import threading
import webbrowser
import socket

from ppt_system.runtime.tls_runtime import configure_ca_bundle


configure_ca_bundle()

from ppt_system.export.text_script_worker_mode import get_text_script_worker_args, is_text_script_worker_mode


if is_text_script_worker_mode(sys.argv):
    from ppt_system.export.text_script_worker import main as text_script_worker_main

    raise SystemExit(text_script_worker_main(get_text_script_worker_args(sys.argv)))

from ppt_system.runtime import runtime_context
from ppt_system.web import create_app
from ppt_system.web.services.static_assets import build_static_asset_version


def static_asset_version() -> str:
    return build_static_asset_version(runtime_context.ROOT)


app = create_app(
    runtime_context.ROOT,
    access_log_mode=runtime_context.read_config().get("http_access_log_mode", "failures"),
    static_asset_version_provider=static_asset_version,
)


def should_open_browser() -> bool:
    return str(os.environ.get("PPT_SYSTEM_NO_BROWSER", "")).strip().lower() not in {"1", "true", "yes", "on"}


def resolve_server_port() -> int:
    """优先使用配置端口，冲突时自动选择本机可用端口。"""
    try:
        preferred = int(os.environ.get("PPT_SYSTEM_PORT", "7860"))
    except (TypeError, ValueError):
        preferred = 7860
    preferred = preferred if 1 <= preferred <= 65535 else 7860
    for port in [preferred, *range(preferred + 1, preferred + 21)]:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
        finally:
            probe.close()
    raise RuntimeError("找不到可用的本地服务端口，请关闭占用端口的程序后重试。")


if __name__ == "__main__":
    server_port = resolve_server_port()
    server_url = f"http://127.0.0.1:{server_port}"
    if should_open_browser():
        threading.Timer(1.0, lambda: webbrowser.open(server_url)).start()
    app.run(host="127.0.0.1", port=server_port, debug=False)
