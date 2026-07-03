from __future__ import annotations

import os
import sys
import threading
import webbrowser

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


if __name__ == "__main__":
    if should_open_browser():
        threading.Timer(1.0, lambda: webbrowser.open("http://127.0.0.1:7860")).start()
    app.run(host="127.0.0.1", port=7860, debug=False)
