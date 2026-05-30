from __future__ import annotations

import importlib
import sys
from types import ModuleType


def get_runtime_module() -> ModuleType:
    """统一从 main 入口读取运行时对象，便于服务层共享后端状态。"""
    module = sys.modules.get("main")
    if module is not None:
        return module
    return importlib.import_module("main")
