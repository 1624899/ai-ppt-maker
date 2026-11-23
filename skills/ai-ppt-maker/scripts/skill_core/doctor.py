from __future__ import annotations

import base64
import importlib
import json
import os
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


REQUIRED_MODULES = {
    "python-pptx": "pptx",
    "Pillow": "PIL",
    "numpy": "numpy",
    "opencv-python-headless": "cv2",
}
PROBE_TIMEOUT_SECONDS = 30


def diagnose_environment() -> dict[str, Any]:
    dependencies = {}
    for distribution, module in REQUIRED_MODULES.items():
        try:
            imported = importlib.import_module(module)
        except Exception as exc:
            dependencies[distribution] = {"available": False, "error": str(exc)}
        else:
            try:
                version = metadata.version(distribution)
            except metadata.PackageNotFoundError:
                version = getattr(imported, "__version__", None)
            dependencies[distribution] = {"available": True, "version": version}
    return {
        "ok": all(item["available"] for item in dependencies.values()),
        "python": sys.executable,
        "dependencies": dependencies,
        "powerpoint_com": _probe_powerpoint(),
        "fonts": _probe_fonts(),
    }


def _probe_powerpoint() -> dict[str, Any]:
    if os.name != "nt":
        return {"status": "unsupported", "reason": "PowerPoint COM 需要 Windows。"}
    from ppt_system.export.ppt_calibration_renderer import render_pptx_slides_to_png

    try:
        with TemporaryDirectory(prefix="ai-ppt-doctor-") as directory:
            render_pptx_slides_to_png(None, Path(directory), [1], timeout_seconds=PROBE_TIMEOUT_SECONDS)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        return {"status": "unavailable", "error": str(exc)}
    return {"status": "available", "check": "open_and_export_png"}


def _probe_fonts() -> dict[str, Any]:
    try:
        if os.name == "nt":
            powershell = shutil.which("powershell")
            if not powershell:
                return {"status": "unavailable", "reason": "找不到 Windows PowerShell。"}
            payload = _probe_windows_fonts(powershell)
        else:
            fontconfig = shutil.which("fc-list")
            if not fontconfig:
                return {"status": "unchecked", "reason": "找不到 Fontconfig 的 fc-list。"}
            languages = {"latin": "en", "chinese_simplified": "zh-cn", "chinese_traditional": "zh-tw"}
            payload = {
                key: sorted(set(_run_probe([fontconfig, f":lang={lang}", "--format=%{family}\\n"]).splitlines()))
                for key, lang in languages.items()
            }
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return {"status": "unavailable", "error": str(exc)}
    return {"status": "available", **payload}


def _probe_windows_fonts(powershell: str) -> dict[str, Any]:
    script = """
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
try {
    Add-Type -AssemblyName PresentationCore
    $samples = @{ latin = 'AaZz09'; chinese_simplified = '中文演示数据图表'; chinese_traditional = '繁體簡報數據圖表' }
    $matches = @{ latin = @(); chinese_simplified = @(); chinese_traditional = @() }
    foreach ($family in [Windows.Media.Fonts]::SystemFontFamilies) {
        $face = [Windows.Media.Typeface]::new($family, [Windows.FontStyles]::Normal, [Windows.FontWeights]::Normal, [Windows.FontStretches]::Normal)
        $glyphs = $null
        if (!$face.TryGetGlyphTypeface([ref]$glyphs) -or $glyphs.Symbol) { continue }
        foreach ($key in $samples.Keys) {
            $missing = $samples[$key].ToCharArray() | Where-Object { !$glyphs.CharacterToGlyphMap.ContainsKey([int]$_) }
            if (!$missing) { $matches[$key] += $family.Source }
        }
    }
    foreach ($key in $samples.Keys) { $matches[$key] = @($matches[$key] | Sort-Object -Unique) }
    ConvertTo-Json -InputObject $matches -Compress
} catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }
"""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return json.loads(_run_probe([powershell, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]))


def _run_probe(command: list[str]) -> str:
    result = subprocess.run(
        command,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=PROBE_TIMEOUT_SECONDS,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or f"探测命令退出码 {result.returncode}。")
    return result.stdout
