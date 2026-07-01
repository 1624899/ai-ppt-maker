from __future__ import annotations

import ast
from pathlib import Path


WEB_IMPORT_PREFIXES = (
    "flask",
    "werkzeug",
    "waitress",
    "gunicorn",
    "uvicorn",
    "ppt_system.web",
)
WEB_IMPORT_NAMES = {"main"}
SERVER_RECEIVER_NAMES = {"app", "application", "server", "flask_app"}
SERVER_CALL_NAMES = {"run_simple", "serve"}
SERVER_METHOD_NAMES = {"run", "serve_forever"}


class GeneratedTextScriptValidationError(RuntimeError):
    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


def validate_generated_text_script(script_path: Path) -> None:
    """在执行前校验生成脚本，避免错误脚本启动常驻服务。"""
    path = Path(script_path)
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GeneratedTextScriptValidationError(f"无法读取生成脚本：{path}。") from exc

    try:
        module = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise GeneratedTextScriptValidationError(f"生成脚本存在语法错误：{path}，第 {exc.lineno or 0} 行。") from exc

    if not _defines_build_deck(module):
        raise GeneratedTextScriptValidationError(
            f"生成脚本不是 PPT 文字布局脚本：{path}\n"
            "未找到 build_deck 函数。该文件可能被写成了 Web 应用入口或其他脚本，请重新生成文字布局脚本。"
        )

    web_import = _find_web_import(module)
    if web_import is not None:
        name, lineno = web_import
        raise GeneratedTextScriptValidationError(
            f"生成脚本包含 Web 服务相关导入：{name}，第 {lineno} 行。\n"
            "文字布局脚本只能生成 PPT 文件，不能导入或启动本地 Web 服务。请重新生成该页文字脚本。"
        )

    server_call = _find_server_launch_call(module)
    if server_call is not None:
        name, lineno = server_call
        raise GeneratedTextScriptValidationError(
            f"生成脚本包含 Web 服务启动调用：{name}，第 {lineno} 行。\n"
            "文字布局脚本执行后必须自然退出，不能启动 Flask、Werkzeug 或其他常驻服务。"
        )


def _defines_build_deck(module: ast.Module) -> bool:
    return any(isinstance(node, ast.FunctionDef) and node.name == "build_deck" for node in module.body)


def _find_web_import(module: ast.Module) -> tuple[str, int] | None:
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = str(alias.name)
                if _is_web_import_name(name):
                    return name, int(getattr(node, "lineno", 0) or 0)
        elif isinstance(node, ast.ImportFrom):
            module_name = str(node.module or "")
            if _is_web_import_name(module_name):
                return module_name, int(getattr(node, "lineno", 0) or 0)
    return None


def _is_web_import_name(name: str) -> bool:
    normalized = str(name).strip()
    if normalized in WEB_IMPORT_NAMES:
        return True
    return any(normalized == prefix or normalized.startswith(f"{prefix}.") for prefix in WEB_IMPORT_PREFIXES)


def _find_server_launch_call(module: ast.Module) -> tuple[str, int] | None:
    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        call_name = _describe_call(node.func)
        if _is_server_launch_call(node.func):
            return call_name, int(getattr(node, "lineno", 0) or 0)
    return None


def _is_server_launch_call(func: ast.AST) -> bool:
    if isinstance(func, ast.Name):
        return func.id in SERVER_CALL_NAMES
    if not isinstance(func, ast.Attribute):
        return False

    if func.attr in SERVER_CALL_NAMES:
        return True
    if func.attr not in SERVER_METHOD_NAMES:
        return False
    return _is_server_receiver(func.value)


def _is_server_receiver(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id in SERVER_RECEIVER_NAMES
    if isinstance(node, ast.Call):
        return _describe_call(node.func) in {"Flask", "flask.Flask"}
    return False


def _describe_call(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        base = _describe_call(func.value)
        return f"{base}.{func.attr}" if base else func.attr
    if isinstance(func, ast.Call):
        return _describe_call(func.func)
    return type(func).__name__
