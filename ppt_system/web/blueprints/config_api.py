from __future__ import annotations

from flask import Blueprint

from ppt_system.web.services import config_api_service

bp = Blueprint("config_api", __name__)


@bp.get("/api/config")
def api_config():
    return config_api_service.api_config()


@bp.get("/api/model-configs")
def api_model_configs():
    return config_api_service.api_model_configs()


@bp.post("/api/model-configs/<model_type>")
def api_create_model_config(model_type: str):
    return config_api_service.api_create_model_config(model_type)


@bp.put("/api/model-configs/<model_type>/<config_id>")
def api_update_model_config(model_type: str, config_id: str):
    return config_api_service.api_update_model_config(model_type, config_id)


@bp.delete("/api/model-configs/<model_type>/<config_id>")
def api_delete_model_config(model_type: str, config_id: str):
    return config_api_service.api_delete_model_config(model_type, config_id)


@bp.post("/api/model-configs/<model_type>/<config_id>/active")
def api_activate_model_config(model_type: str, config_id: str):
    return config_api_service.api_activate_model_config(model_type, config_id)
