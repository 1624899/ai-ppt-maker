from __future__ import annotations

import base64
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from ppt_system.runtime.interruptible_execution import run_interruptible_process


def render_pptx_slides_to_png(
    pptx_path: Path | None,
    output_dir: Path,
    slide_numbers: list[int],
    *,
    timeout_seconds: float | None = None,
) -> list[Path]:
    powershell = shutil.which("powershell")
    if not powershell:
        raise RuntimeError("PowerPoint 渲染需要 Windows PowerShell。")
    output_dir.mkdir(parents=True, exist_ok=True)
    targets = [output_dir / f"slide_{number:02d}.png" for number in slide_numbers]
    with TemporaryDirectory(dir=output_dir, prefix=".render-") as stage:
        stage_dir = Path(stage)
        numbers = ", ".join(str(number) for number in slide_numbers)
        input_path = pptx_path or stage_dir / "probe.pptx"
        probe_commands = []
        if pptx_path is None:
            probe_commands = [
                "  $presentation = $ppt.Presentations.Add(0)",
                "  $blankLayout = 12 # PowerPoint 的 ppLayoutBlank",
                "  $null = $presentation.Slides.Add(1, $blankLayout)",
                f"  $presentation.SaveAs('{_ps_path(input_path)}')",
                "  $presentation.Close()",
                "  $presentation = $null",
            ]
        script = "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                "[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)",
                "$ppt = $null",
                "$presentation = $null",
                "$started = $false",
                "try {",
                "  try { $ppt = [Runtime.InteropServices.Marshal]::GetActiveObject('PowerPoint.Application') }",
                "  catch { $ppt = New-Object -ComObject PowerPoint.Application; $started = $true }",
                *probe_commands,
                f"  $presentation = $ppt.Presentations.Open('{_ps_path(input_path)}', $true, $true, $false)",
                "  $width = 1600",
                "  $height = [int]($width * $presentation.PageSetup.SlideHeight / $presentation.PageSetup.SlideWidth)",
                f"  foreach ($number in @({numbers})) {{",
                f"    $target = Join-Path '{_ps_path(stage_dir)}' ('slide_{{0:D2}}.png' -f $number)",
                "    $presentation.Slides.Item($number).Export($target, 'PNG', $width, $height)",
                "  }",
                "}",
                "catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }",
                "finally {",
                "  if ($presentation -ne $null) { $presentation.Close() }",
                "  if ($started -and $ppt.Presentations.Count -eq 0) { $ppt.Quit() }",
                "}",
            ]
        )
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        result = run_interruptible_process(
            [powershell, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            timeout_seconds=timeout_seconds,
            interruption_message=f"PowerPoint 渲染已中断：{input_path}",
            popen_kwargs={
                "creationflags": subprocess.CREATE_NO_WINDOW,
                "stderr": subprocess.PIPE,
                "encoding": "utf-8",
                "errors": "replace",
            },
        )
        if result.returncode != 0:
            raise RuntimeError(f"本机 PowerPoint 渲染失败：{result.stderr.strip()}")
        if any(not (stage_dir / path.name).is_file() for path in targets):
            raise RuntimeError(f"本机 PowerPoint 未能渲染指定的幻灯片：{input_path}")
        for path in targets:
            (stage_dir / path.name).replace(path)
    return targets


def _ps_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")
