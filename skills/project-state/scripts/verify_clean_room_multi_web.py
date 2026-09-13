#!/usr/bin/env python3
"""Verify clean-room bundle feeds the real Ask multi-web roundtable compile path."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

REQUIRED_HANDLERS = {"webgpt", "webkimi", "webgemini"}


def load_json_from_mixed_stdout(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    start = text.find("{")
    if start < 0:
        raise AssertionError(f"no JSON object in {path}")
    return json.loads(text[start:])


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if len(args) != 2:
        raise SystemExit("usage: verify_clean_room_multi_web.py <manifest.json> <ask-compile.json>")
    manifest_path = Path(args[0])
    ask_path = Path(args[1])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ask = load_json_from_mixed_stdout(ask_path)

    assert manifest["schema"] == "clean_room.loop_receipt.v1"
    assert manifest["status"] == "needs_webgpt"
    assert set(manifest["review_handlers"]) == REQUIRED_HANDLERS
    assert manifest["review_mode"] == "ask_tau_roundtable"
    assert manifest["ticket_count"] == 0
    assert "ticket_previews.md" not in manifest.get("bundle_files", [])
    shell = manifest["ask_roundtable_shell"]
    for handler in REQUIRED_HANDLERS:
        assert f"--handler {handler}" in shell
    assert "--dag-template roundtable" in shell
    assert "--topology concurrent" in shell

    zip_path = Path(manifest["zip_path"])
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        assert len(names) <= 5
        assert {"project_state.json", "review_context.md", "source_excerpts.md", "manifest.json", "prompt.md"} <= names
        excerpts = zf.read("source_excerpts.md").decode("utf-8")
    assert "# Source excerpts" in excerpts
    assert "## `run.sh`" in excerpts or "## `SKILL.md`" in excerpts

    dag = ask.get("dag") or ask.get("contract") or ask
    dag_text = json.dumps(dag, sort_keys=True)
    for handler in REQUIRED_HANDLERS:
        assert handler in dag_text
    assert "roundtable" in dag_text.lower()

    print("CLEAN_ROOM_MULTI_WEB_ASK_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
