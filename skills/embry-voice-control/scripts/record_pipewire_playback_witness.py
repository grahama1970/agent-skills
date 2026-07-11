#!/usr/bin/env python3
"""Bind an explicit human audible witness to a machine playback receipt."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import typer


def main(machine_receipt: Path = typer.Option(...), human_reply_file: Path = typer.Option(...), verdict: str = typer.Option(...), output: Path = typer.Option(...)) -> None:
    machine = json.loads(machine_receipt.read_text(encoding="utf-8"))
    reply = human_reply_file.read_text(encoding="utf-8")
    if machine.get("status") != "MACHINE_PASS_HUMAN_PENDING" or not reply.strip():
        raise typer.BadParameter("machine receipt or human reply invalid")
    if verdict not in {"heard_exactly", "not_heard", "heard_different"}:
        raise typer.BadParameter("verdict invalid")
    passed = verdict == "heard_exactly"
    receipt = {
        "schema": "embry.voice.pipewire_playback_authority_receipt.v1",
        "status": "PASS" if passed else "FAIL", "ok": passed, "live": True, "mocked": False,
        "machine_receipt": {"path": str(machine_receipt), "sha256": "sha256:" + hashlib.sha256(machine_receipt.read_bytes()).hexdigest()},
        "human_audible_witness": {"status": "confirmed_exact" if passed else verdict, "source": "explicit_human_response", "response_path": str(human_reply_file), "response_sha256": "sha256:" + hashlib.sha256(reply.encode()).hexdigest(), "heard_exactly": passed, "recorded_at": datetime.now(timezone.utc).isoformat()},
        "failed_gates": [] if passed else ["human_audible_witness"],
    }
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    typer.echo(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    typer.run(main)
