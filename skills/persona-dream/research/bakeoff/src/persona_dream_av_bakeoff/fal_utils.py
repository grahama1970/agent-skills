from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import fal_client


def ensure_fal_key() -> None:
    fal_key = os.getenv("FAL_KEY") or os.getenv("FAL_API_KEY")
    if not fal_key:
        raise RuntimeError("FAL_KEY or FAL_API_KEY is not set.")
    os.environ.setdefault("FAL_KEY", fal_key)


def on_queue_update(update: Any) -> None:
    if isinstance(update, fal_client.InProgress):
        for log in update.logs:
            if isinstance(log, dict):
                print(log.get("message", log))
            else:
                print(log)


def subscribe(model_id: str, arguments: dict[str, Any], *, with_logs: bool = True) -> dict[str, Any]:
    ensure_fal_key()
    return fal_client.subscribe(
        model_id,
        arguments=arguments,
        with_logs=with_logs,
        on_queue_update=on_queue_update if with_logs else None,
    )


def upload_file(path: str | Path) -> str:
    ensure_fal_key()
    return fal_client.upload_file(str(Path(path).resolve()))
