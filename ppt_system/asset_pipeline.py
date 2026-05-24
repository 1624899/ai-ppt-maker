from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExternalStageConfig:
    mode: str
    command: str
    timeout_seconds: int


@dataclass(frozen=True)
class ExternalStageResult:
    output_path: Path
    strategy: str
    warning: str | None = None


def normalize_stage_mode(value: str, *, default: str = "builtin") -> str:
    mode = str(value or "").strip().lower()
    if mode in {"builtin", "external", "skip"}:
        return mode
    return default


def run_external_stage(
    *,
    stage_name: str,
    command_template: str,
    input_path: Path,
    output_path: Path,
    page_no: int,
    timeout_seconds: int,
) -> ExternalStageResult:
    command = render_command_template(
        command_template,
        input_path=input_path,
        output_path=output_path,
        page_no=page_no,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run_shell_command(command, timeout_seconds=timeout_seconds)
    if not output_path.exists():
        raise RuntimeError(f"{stage_name} 外部处理未生成目标文件：{output_path}")
    return ExternalStageResult(
        output_path=output_path,
        strategy=f"external:{stage_name}",
    )


def render_command_template(
    command_template: str,
    *,
    input_path: Path,
    output_path: Path,
    page_no: int,
) -> str:
    if not str(command_template or "").strip():
        raise ValueError("外部处理命令不能为空")

    values = {
        "input": _ps_quote(input_path.resolve()),
        "output": _ps_quote(output_path.resolve()),
        "input_dir": _ps_quote(input_path.resolve().parent),
        "output_dir": _ps_quote(output_path.resolve().parent),
        "input_stem": str(input_path.stem),
        "output_stem": str(output_path.stem),
        "page_no": str(page_no),
    }
    try:
        return str(command_template).format(**values)
    except KeyError as exc:
        raise ValueError(f"外部处理命令包含未知占位符：{exc}") from exc


def _run_shell_command(command: str, *, timeout_seconds: int) -> None:
    if os.name == "nt":
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    else:
        completed = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )

    if completed.returncode == 0:
        return

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    detail = stderr or stdout or f"退出码 {completed.returncode}"
    raise RuntimeError(f"外部命令执行失败：{detail}")


def _ps_quote(path: Path) -> str:
    # 用 PowerShell 单引号包裹路径，避免空格和中文路径导致命令解析出错。
    return "'" + str(path).replace("'", "''") + "'"
