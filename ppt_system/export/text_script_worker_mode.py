from __future__ import annotations


TEXT_SCRIPT_WORKER_ARG = "--text-script-worker"


def is_text_script_worker_mode(argv: list[str]) -> bool:
    """判断当前进程是否应作为文字脚本 worker 运行。"""
    return len(argv) >= 2 and str(argv[1]) == TEXT_SCRIPT_WORKER_ARG


def get_text_script_worker_args(argv: list[str]) -> list[str]:
    """提取传给文字脚本 worker 的参数。"""
    return list(argv[2:]) if is_text_script_worker_mode(argv) else []
