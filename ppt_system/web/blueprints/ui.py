from __future__ import annotations

from flask import Blueprint, current_app, render_template, send_from_directory

bp = Blueprint("ui", __name__)


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/<path:filename>")
def public_asset(filename: str):
    # Vite 会把 public 目录文件构建到 dist 根目录，Flask 的静态目录只挂载 assets。
    allowed_assets = {"favicon.svg", "icons.svg"}
    if filename not in allowed_assets:
        return render_template("index.html")
    return send_from_directory(current_app.template_folder, filename)
