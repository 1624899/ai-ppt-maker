from __future__ import annotations

from pathlib import Path

from flask import Flask

from ppt_system.web.blueprints.artifacts_api import bp as artifacts_api_bp
from ppt_system.web.blueprints.config_api import bp as config_api_bp
from ppt_system.web.blueprints.jobs_api import bp as jobs_api_bp
from ppt_system.web.blueprints.ui import bp as ui_bp


def create_app(
    root: Path,
    *,
    static_asset_version_provider: Callable[[], str] | None = None,
) -> Flask:
    web_ui_dist_dir = root / "web_ui" / "dist"
    web_ui_assets_dir = web_ui_dist_dir / "assets"
    template_dir = web_ui_dist_dir if web_ui_dist_dir.exists() else root / "front" / "templates"
    static_dir = web_ui_assets_dir if web_ui_assets_dir.exists() else root / "front" / "static"
    static_url_path = "/assets" if web_ui_assets_dir.exists() else "/static"
    app = Flask(
        __name__,
        template_folder=str(template_dir),
        static_folder=str(static_dir),
        static_url_path=static_url_path,
    )
    app.register_blueprint(ui_bp)
    app.register_blueprint(config_api_bp)
    app.register_blueprint(jobs_api_bp)
    app.register_blueprint(artifacts_api_bp)

    if static_asset_version_provider is not None:
        app.add_template_global(static_asset_version_provider, name="static_asset_version")

    @app.after_request
    def disable_browser_cache(response):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    return app
