from __future__ import annotations

import os
import threading
import webbrowser

from ppt_system.runtime import runtime_context
from ppt_system.web.services.static_assets import build_static_asset_version
from ppt_system.web import create_app


def static_asset_version() -> str:
    return build_static_asset_version(runtime_context.ROOT)


app = create_app(
    runtime_context.ROOT,
    static_asset_version_provider=static_asset_version,
)


def should_open_browser() -> bool:
    return str(os.environ.get("PPT_SYSTEM_NO_BROWSER", "")).strip().lower() not in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    if should_open_browser():
        threading.Timer(1.0, lambda: webbrowser.open("http://127.0.0.1:7860")).start()
    app.run(host="127.0.0.1", port=7860, debug=False)
