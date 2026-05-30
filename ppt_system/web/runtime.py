from __future__ import annotations

import importlib
import sys
from types import ModuleType


def get_runtime_module() -> ModuleType:
    """统一从兼容入口读取运行时对象，便于逐步拆分 web_app。"""
    module = sys.modules.get("web_app")
    if module is not None:
        return module
    return importlib.import_module("web_app")
