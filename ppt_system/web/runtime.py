from __future__ import annotations

from types import ModuleType

from ppt_system.runtime import runtime_context


def get_runtime_module() -> ModuleType:
    """兼容旧调用方的运行时上下文入口。"""
    return runtime_context
