from __future__ import annotations

from pathlib import Path

from ppt_system.export.text_script_runtime_modules import TEXT_SCRIPT_RUNTIME_MODULES


def test_windows_build_script_includes_text_script_runtime_hidden_imports() -> None:
    script_source = Path("scripts/build_windows_desktop.ps1").read_text(encoding="utf-8")

    assert "TEXT_SCRIPT_RUNTIME_MODULES" in script_source
    assert "--hidden-import" in script_source
    assert "print('\\n'.join(TEXT_SCRIPT_RUNTIME_MODULES))" in script_source


def test_text_script_runtime_hidden_imports_are_separate_module_names() -> None:
    assert set(TEXT_SCRIPT_RUNTIME_MODULES) == {
        "ppt_system.export.export_artifact_policy",
        "ppt_system.export.text_style_runtime",
        "ppt_system.export.editable_charts",
    }
    assert all(" " not in module_name for module_name in TEXT_SCRIPT_RUNTIME_MODULES)
