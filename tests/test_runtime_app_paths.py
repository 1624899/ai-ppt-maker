from __future__ import annotations

from pathlib import Path

from ppt_system.runtime.app_paths import (
    DATA_DIR_ENV,
    DATA_MODE_ENV,
    resolve_configured_job_dir,
    resolve_configured_output_root,
    resolve_runtime_paths,
)


def test_frozen_runtime_uses_user_data_dir_for_mutable_files() -> None:
    app_root = Path("C:/Program Files/AI PPT Maker")
    paths = resolve_runtime_paths(
        app_root,
        frozen=True,
        env={"APPDATA": "C:/Users/demo/AppData/Roaming"},
        platform_name="nt",
    )

    assert paths.app_root == app_root.resolve()
    assert paths.data_dir == Path("C:/Users/demo/AppData/Roaming/AI PPT Maker").resolve()
    assert paths.config_path == app_root.resolve() / "config.json"
    assert paths.local_config_path == paths.data_dir / "config.local.json"
    assert paths.env_path == paths.data_dir / ".env"
    assert paths.default_output_dir == paths.data_dir / "output"
    assert paths.data_mode == "appdata"


def test_project_mode_keeps_development_files_next_to_source() -> None:
    app_root = Path("D:/dev/ai-ppt-maker")
    paths = resolve_runtime_paths(app_root, frozen=False, env={}, platform_name="nt")

    assert paths.data_dir == app_root.resolve()
    assert paths.local_config_path == app_root.resolve() / "config.local.json"
    assert paths.env_path == app_root.resolve() / ".env"
    assert paths.default_output_dir == app_root.resolve() / "output"
    assert paths.data_mode == "project"


def test_env_overrides_data_dir_and_output_root_resolution() -> None:
    app_root = Path("D:/dev/ai-ppt-maker")
    paths = resolve_runtime_paths(
        app_root,
        frozen=False,
        env={DATA_DIR_ENV: "D:/AI PPT Data"},
        platform_name="nt",
    )

    assert paths.data_dir == Path("D:/AI PPT Data").resolve()
    assert resolve_configured_output_root(paths, {"output_dir": "runs"}) == paths.data_dir / "runs"
    assert resolve_configured_job_dir(paths, {"output_dir": "runs"}, "job-demo") == paths.data_dir / "runs" / "job-demo"


def test_portable_mode_uses_data_folder_inside_app_root() -> None:
    app_root = Path("D:/apps/ai-ppt-maker")
    paths = resolve_runtime_paths(
        app_root,
        frozen=True,
        executable_path="D:/apps/AI PPT Maker/AI PPT Maker.exe",
        env={DATA_MODE_ENV: "portable"},
        platform_name="nt",
    )

    assert paths.data_dir == Path("D:/apps/AI PPT Maker/data").resolve()
    assert paths.default_output_dir == Path("D:/apps/AI PPT Maker/data/output").resolve()
    assert paths.data_mode == "portable"


def test_project_mode_uses_exe_directory_when_frozen() -> None:
    paths = resolve_runtime_paths(
        Path("C:/Users/demo/AppData/Local/Temp/_MEI12345"),
        frozen=True,
        executable_path="D:/apps/AI PPT Maker/AI PPT Maker.exe",
        env={DATA_MODE_ENV: "project"},
        platform_name="nt",
    )

    assert paths.data_dir == Path("D:/apps/AI PPT Maker").resolve()
    assert paths.config_path == Path("C:/Users/demo/AppData/Local/Temp/_MEI12345/config.json").resolve()
