from __future__ import annotations

from typing import Any

__all__ = ["create_app"]


def create_app(*args: Any, **kwargs: Any):
    """延迟加载 Flask 应用，避免服务子模块导入时触发循环依赖。"""
    from .app import create_app as build_app

    return build_app(*args, **kwargs)
