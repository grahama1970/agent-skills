#!/usr/bin/env python3
"""Cross-skill live proof: curate-client prep context is consumed by Live Evidence.

This is intentionally not a unit test. It runs the real curate-client CLI, starts
a real Live Evidence HTTP server, loads the prep-pack through the command emitted
by curate-client, posts DriveWealth transcript turns, and reads back server state
and journal receipts.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

FAILURES: list[str] = []
CHECKS: dict[str, bool] = {}
DETAILS: dict[str, Any] = {}


def check(name: str, ok: bool, detail: Any = None) -> None:
    CHECKS[name] = bool(ok)
    DETAILS[name] = detail
    print(f"{name}: {'PASS' if ok else 'FAIL'}{f' ({detail})' if detail is not None else ''}")
    if not ok:
        FAILURES.append(name)


def parse_json_from_stdout(text: str) -> dict[str, Any]:
    start = text.find("{")
    if start < 0:
        raise ValueError(f"stdout did not contain JSON: {text[:400]}")
    return json.loads(text[start:])


def clean_env() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("UV_PROJECT_ENVIRONMENT", None)
    env.pop("VIRTUAL_ENV", None)
    if env.get("MEMORY_SERVICE_URL", "").startswith("unix://"):
        env["MEMORY_SERVICE_URL"] = "http://127.0.0.1:8601"
    return env


def run_json(argv: list[str], *, cwd: Path, timeout_s: int) -> tuple[subprocess.CompletedProcess[str], dict[str, Any] | None]:
    proc = subprocess.run(argv, cwd=cwd, env=clean_env(), capture_output=True, text=True, timeout=timeout_s)
    payload = None
    if proc.stdout.strip():
        try:
            payload = parse_json_from_stdout(proc.stdout)
        except Exception:
            payload = None
    return proc, payload


def read_journal(data_dir: Path) -> list[dict[str, Any]]:
    path = next(data_dir.glob("*/session.jsonl"), None)
    if not path or not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def wait_for(predicate, *, timeout_s: float, interval_s: float = 0.5):
    deadline = time.monotonic() + timeout_s
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(interval_s)
    return last


def source_keys(cards: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for card in cards:
        for source in card.get("sources") or []:
            metadata = source.get("metadata") or {}
            key = metadata.get("_key") or source.get("source_id")
            if key:
                keys.add(str(key))
    return keys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("skill_root", nargs="?")
    parser.add_argument("--output", default="/tmp/live-evidence-curate-client-current.json")
    parser.add_argument("--memory-url", default=os.getenv("MEMORY_SERVICE_URL") or "http://127.0.0.1:8601")
    parser.add_argument("--timeout-s", type=int, default=240)
    args = parser.parse_args()

    root = Path(args.skill_root).resolve() if args.skill_root else Path(__file__).resolve().parents[1]
    repo_root = root.parents[1]
    curate_root = repo_root / "skills" / "curate-client"
    config_path = curate_root / "configs" / "drivewealth.yaml"
    output_path = Path(args.output).expanduser().resolve()
    memory_url = args.memory_url if args.memory_url.startswith(("http://", "https://")) else "http://127.0.0.1:8601"
    receipt: dict[str, Any] = {
        "schema": "live_evidence.curate_client_integration_receipt.v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "mocked": False,
        "fixture_backed": True,
        "live": True,
        "skill_root": str(root),
        "curate_client_config": str(config_path),
        "memory_url": memory_url,
        "commands": {},
        "checks": CHECKS,
        "details": DETAILS,
    }

    sys.path.insert(0, str(root / "scripts"))
    import run_g2i_campaign as campaign  # noqa: PLC0415

    campaign.ROOT = root
    campaign.PACK = root / "benchmarks" / "g2i-public-python-v1"

    build_proc, build_json = run_json(
        [str(curate_root / "run.sh"), "build", "--config", str(config_path)],
        cwd=curate_root,
        timeout_s=1900,
    )
    receipt["commands"]["curate_client_build"] = {
        "argv": [str(curate_root / "run.sh"), "build", "--config", str(config_path)],
        "exit_code": build_proc.returncode,
        "stdout_tail": build_proc.stdout[-2000:],
        "stderr_tail": build_proc.stderr[-2000:],
        "json": build_json,
    }
    check("curate-client build exits zero", build_proc.returncode == 0, build_proc.returncode)
    check("curate-client verify passed", bool(build_json and build_json.get("verify", {}).get("status") == "PASS"), (build_json or {}).get("verify"))
    check("curate-client emitted live-evidence load command", bool(build_json and "load-prep-pack" in (build_json.get("prep_pack", {}).get("live_evidence_load", {}).get("command") or [])), (build_json or {}).get("prep_pack", {}).get("live_evidence_load"))

    server = None
    try:
        default_kb_root = Path.home() / "workspace" / "experiments" / "dw-openapi"
        kb_root = str((build_json or {}).get("prep_pack", {}).get("prep_pack", {}).get("producer", {}).get("kb_root") or default_kb_root)
        server = campaign.Server(
            campaign.import_tmp("curate-client-live-evidence"),
            live_resolver=True,
            memory_url=memory_url,
            repos=f"{kb_root}:{root}",
        )
        receipt["server"] = {"url": server.url, "data_dir": str(server.data_dir)}

        load_command = list((build_json or {}).get("prep_pack", {}).get("live_evidence_load", {}).get("command") or [])
        if "--backend-url" in load_command:
            load_command[load_command.index("--backend-url") + 1] = server.url
        else:
            load_command.extend(["--backend-url", server.url])
        if "--memory-url" in load_command:
            load_command[load_command.index("--memory-url") + 1] = memory_url
        else:
            load_command.extend(["--memory-url", memory_url])
        load_receipt_path = output_path.with_name(output_path.stem + ".load-prep-pack.json")
        load_command.extend(["--output", str(load_receipt_path)])
        load_proc, load_json = run_json(load_command, cwd=root, timeout_s=args.timeout_s)
        if load_receipt_path.exists():
            load_json = json.loads(load_receipt_path.read_text(encoding="utf-8"))
        receipt["commands"]["live_evidence_load_prep_pack"] = {
            "argv": load_command,
            "exit_code": load_proc.returncode,
            "stdout_tail": load_proc.stdout[-2000:],
            "stderr_tail": load_proc.stderr[-2000:],
            "json": load_json,
        }
        check("live-evidence load-prep-pack exits zero", load_proc.returncode == 0, load_proc.returncode)
        check("prep-pack load receipt passed", bool(load_json and load_json.get("status") == "PASS"), load_json)
        check("prep-pack oracle recall verified", bool(load_json and load_json.get("oracle_recall", {}).get("ok") is True), (load_json or {}).get("oracle_recall"))

        briefing = campaign.http("GET", f"{server.url}/api/briefing")[1]
        check("briefing loaded in running HUD backend", briefing.get("loaded") is True and briefing.get("pack_id") == "drivewealth-ai-ml-2026-08-briefing", briefing)

        server.post_final(1, "DriveWealth partner updates can arrive through SQS out of order. Your agent sees an older KYC-approved event after a newer restricted event. How does it determine current state, preserve the conflicting evidence, and explain the result without inventing an event order?")
        surfaced = wait_for(
            lambda: campaign.http("GET", f"{server.url}/api/briefing")[1].get("surfaced") or None,
            timeout_s=20,
        ) or []
        point_ids = {hit.get("point_id") for hit in surfaced}
        check("DriveWealth briefing trigger surfaced from transcript", "kyc-state-machine" in point_ids, surfaced)

        cards_state = wait_for(
            lambda: (server.state().get("cards") or None),
            timeout_s=120,
        ) or []
        keys = source_keys(cards_state)
        card_text = json.dumps(cards_state).lower()
        source_paths = {
            str(source.get("path") or "")
            for card in cards_state
            for source in (card.get("sources") or [])
        }
        supported = any(card.get("status") == "supported" for card in cards_state)
        prep_pack_source_hit = any(path.endswith("fixtures/prep_pack_drivewealth.json") for path in source_paths)
        bridge_source_hit = any(path.endswith("fixtures/drivewealth_bridge.md") for path in source_paths)
        receipt["cards"] = cards_state[:5]
        receipt["source_keys"] = sorted(keys)
        receipt["source_paths"] = sorted(source_paths)
        check("DriveWealth transcript produced supported evidence card", supported, {"card_count": len(cards_state), "statuses": [c.get("status") for c in cards_state]})
        check("card cites DriveWealth prep pack and bridge files", prep_pack_source_hit and bridge_source_hit, {"source_paths": sorted(source_paths), "card_text_head": card_text[:600]})

        rows = read_journal(server.data_dir)
        kinds = [row.get("kind") for row in rows]
        receipt["journal_kinds"] = kinds
        check("journal records prep load and briefing surface", "briefing_pack_loaded" in kinds and "briefing_point_surfaced" in kinds, kinds[-20:])
        check("journal records visible publication decision", "card_publication_decision" in kinds, kinds[-20:])
    finally:
        if server is not None:
            server.close()

    receipt["checks"] = CHECKS
    receipt["details"] = DETAILS
    receipt["failures"] = list(FAILURES)
    receipt["status"] = "PASS" if not FAILURES else "FAIL"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"curate-client/live-evidence receipt: {output_path}")
    print(f"curate-client/live-evidence: {receipt['status']}")
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
