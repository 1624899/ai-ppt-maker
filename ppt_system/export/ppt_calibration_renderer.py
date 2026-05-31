from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def render_pptx_first_slide_to_png(
    pptx_path: Path,
    output_path: Path,
    *,
    image_width: int,
    image_height: int,
) -> Path | None:
    # 优先使用本机 PowerPoint 真渲染导出，避免 PIL 与 Office 字体度量不一致。
    exported = _render_with_powershell_com(
        pptx_path,
        output_path,
        image_width=image_width,
        image_height=image_height,
    )
    if exported is not None and exported.exists():
        return exported
    return None


def _render_with_powershell_com(
    pptx_path: Path,
    output_path: Path,
    *,
    image_width: int,
    image_height: int,
) -> Path | None:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        return None

    output_dir = output_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = output_path.stem
    exported_candidate = output_dir / f"{stem}.PNG"
    script = "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            "$ppt = $null",
            "$presentation = $null",
            "try {",
            "  $ppt = New-Object -ComObject PowerPoint.Application",
            f"  $presentation = $ppt.Presentations.Open('{_ps_path(pptx_path)}', $false, $false, $false)",
            f"  $presentation.Slides.Item(1).Export('{_ps_path(exported_candidate)}', 'PNG', {int(image_width)}, {int(image_height)})",
            "}",
            "finally {",
            "  if ($presentation -ne $null) { $presentation.Close() }",
            "  if ($ppt -ne $null) { $ppt.Quit() }",
            "  [GC]::Collect()",
            "  [GC]::WaitForPendingFinalizers()",
            "}",
        ]
    )

    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    result = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        creationflags=creation_flags,
        startupinfo=startupinfo,
    )
    if result.returncode != 0:
        return None
    if not exported_candidate.exists():
        return None
    if exported_candidate != output_path:
        exported_candidate.replace(output_path)
    return output_path


def _ps_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")
