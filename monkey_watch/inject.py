"""JavaScript injection helpers."""

from __future__ import annotations

from pathlib import Path


def _js_dir() -> Path:
    return Path(__file__).resolve().parent / "js"


def load_inject_script(snapshot_limit: int, max_queue_size: int) -> str:
    template = (_js_dir() / "inject.js").read_text(encoding="utf-8")
    return (
        template.replace("__SNAPSHOT_LIMIT__", str(snapshot_limit))
        .replace("__MAX_QUEUE_SIZE__", str(max_queue_size))
    )


def load_debug_script() -> str:
    return (_js_dir() / "debug.js").read_text(encoding="utf-8")
