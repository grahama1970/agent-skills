#!/usr/bin/env python3
"""Run the focused data-qid live fixture through test-interactions discover.

The script serves a real HTML fixture over local HTTP, invokes the production
test-interactions run.sh discover command, reads back discovery artifacts, and
asserts that stable dynamic-list controls are executable by QID while duplicate
and missing QID defects are reported without selector fallbacks.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import socket
import socketserver
import subprocess
import threading
from pathlib import Path


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def manifest_targets(manifest: dict) -> list[str]:
    targets: list[str] = []
    for surface in manifest.get("surfaces", []):
        for element in surface.get("elements", []):
            for interaction in element.get("interactions", []):
                target = interaction.get("target")
                if target:
                    targets.append(str(target))
    return targets


def contains_fallback_selector(values: list[str]) -> bool:
    fallback_tokens = ("nth-child", "#", ".", "xpath", "text=")
    for value in values:
        if not value:
            continue
        if value.startswith("[data-qid='") and value.endswith("']"):
            continue
        if any(token in value for token in fallback_tokens):
            return True
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="JSON result path")
    parser.add_argument("--work-dir", type=Path, default=Path("/tmp/best-practices-react-1628-live"), help="directory for live discovery artifacts")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    skill_dir = Path(__file__).resolve().parents[1]
    fixture_dir = skill_dir / "fixtures" / "data-qid" / "live"
    output_dir = args.work_dir / "discovery"
    manifest_path = args.work_dir / "manifest.generated.json"
    output_dir.mkdir(parents=True, exist_ok=True)

    port = free_port()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(fixture_dir))
    with socketserver.TCPServer(("127.0.0.1", port), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{port}/qid-live-fixture.html"
        command = [
            str(repo_root / "skills" / "test-interactions" / "run.sh"),
            "discover",
            "--url",
            url,
            "--output-dir",
            str(output_dir),
            "--manifest-output",
            str(manifest_path),
            "--max-depth",
            "1",
            "--max-states",
            "4",
            "--max-actions",
            "8",
        ]
        completed = subprocess.run(command, text=True, capture_output=True, check=False, timeout=90)
        server.shutdown()

    findings_path = output_dir / "discovery-findings.jsonl"
    inventory_path = output_dir / "discovery-inventory.json"
    findings = read_jsonl(findings_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    inventory = json.loads(inventory_path.read_text(encoding="utf-8")) if inventory_path.is_file() else {}

    targets = manifest_targets(manifest)
    finding_kinds = [str(item.get("finding_kind")) for item in findings]
    finding_selectors = [str(item.get("selector") or "") for item in findings]
    stable_target = "[data-qid='orders:item:open:order-101']"
    checks = {
        "discover_exit_zero": completed.returncode == 0,
        "stable_dynamic_control_manifest_target": stable_target in targets,
        "duplicate_qid_reported": "duplicate_qid" in finding_kinds,
        "missing_qid_reported": "missing_qid" in finding_kinds,
        "manifest_has_only_qid_targets": bool(targets) and all(target.startswith("[data-qid='") for target in targets),
        "no_fallback_selector_in_manifest": not contains_fallback_selector(targets),
        "no_fallback_selector_in_findings": not contains_fallback_selector(finding_selectors),
    }
    passed = all(checks.values())
    result = {
        "schema": "best_practices_react.data_qid_live_result.v1",
        "status": "PASS_DATA_QID_LIVE_FIXTURE" if passed else "FAIL_DATA_QID_LIVE_FIXTURE",
        "mocked": False,
        "live": True,
        "url": url,
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "artifacts": {
            "findings": str(findings_path),
            "inventory": str(inventory_path),
            "manifest": str(manifest_path),
        },
        "checks": checks,
        "finding_kinds": finding_kinds,
        "manifest_targets": targets,
        "states_seen": inventory.get("states_seen"),
        "actions_run": inventory.get("actions_run"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output)}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
