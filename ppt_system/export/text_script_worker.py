from __future__ import annotations

import contextlib
import io
import json
import sys
import traceback
from pathlib import Path

import runpy


def _find_package_import_root(current_file: Path, package_name: str) -> Path:
    """从当前文件向上查找包含目标包的导入根目录。"""
    resolved_file = current_file.resolve()
    search_start = resolved_file if resolved_file.is_dir() else resolved_file.parent
    for candidate in (search_start, *search_start.parents):
        package_init = candidate / package_name / "__init__.py"
        if package_init.is_file():
            return candidate
    return search_start


def _prepend_sys_path_once(path: Path) -> None:
    """将路径加入 sys.path 头部，并避免重复加入同一个目录。"""
    resolved_path = path.resolve()
    resolved_path_text = str(resolved_path)
    for item in sys.path:
        if not item:
            continue
        try:
            if Path(item).resolve() == resolved_path:
                return
        except OSError:
            if item == resolved_path_text:
                return
    sys.path.insert(0, resolved_path_text)


def _configure_runtime_environment() -> None:
    """统一子进程编码与导入路径，避免 Windows 下执行脚本时丢失仓库根目录。"""
    repo_root = _find_package_import_root(Path(__file__), "ppt_system")
    _prepend_sys_path_once(repo_root)

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _configure_runtime_environment()
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print(json.dumps({"ok": False, "error": "usage: text_script_worker <script_path>"}, ensure_ascii=False), file=sys.stderr)
        return 2

    script_path = Path(args[0]).resolve()
    try:
        captured_stdout = io.StringIO()
        captured_stderr = io.StringIO()
        with contextlib.redirect_stdout(captured_stdout), contextlib.redirect_stderr(captured_stderr):
            namespace = runpy.run_path(str(script_path), run_name="__generated_text_script__")
            build_deck = namespace.get("build_deck")
            if not callable(build_deck):
                raise RuntimeError(f"生成脚本缺少 build_deck 函数：{script_path}")
            output_path = Path(build_deck())
        if not output_path.exists():
            raise RuntimeError(f"执行生成的文字脚本后未发现输出文件：{output_path}")
        print(
            json.dumps(
                {
                    "ok": True,
                    "output_path": str(output_path.resolve()),
                    "script_stdout": captured_stdout.getvalue(),
                    "script_stderr": captured_stderr.getvalue(),
                },
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                    "script_stdout": captured_stdout.getvalue() if "captured_stdout" in locals() else "",
                    "script_stderr": captured_stderr.getvalue() if "captured_stderr" in locals() else "",
                },
                ensure_ascii=False,
            ),
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
