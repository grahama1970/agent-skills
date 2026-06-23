#!/usr/bin/env python3
"""Blocking drift check: HTML progress report vs repo proof artifacts."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _collect_pytest_nodes(repo: Path, test_file: Path) -> set[str]:
    if not test_file.exists():
        return set()
    proc = subprocess.run(
        ["uv", "run", "pytest", str(test_file), "--collect-only", "-q"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    nodes: set[str] = set()
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if "::" in line and "test_" in line:
            nodes.add(line.split("::")[-1])
        elif line.startswith("test_"):
            nodes.add(line.split()[0])
    return nodes


def _parse_sanity_table(html: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for match in re.finditer(
        r"<tr>\s*<td>(.*?)</td>\s*<td><code>(.*?)</code></td>\s*<td>(.*?)</td>\s*<td class=\"([^\"]+)\">(.*?)</td>\s*</tr>",
        html,
        re.S | re.I,
    ):
        check, command, lane, status_class, status_text = match.groups()
        rows.append(
            {
                "check": re.sub(r"<[^>]+>", "", check).strip(),
                "command": command.strip(),
                "status_class": status_class.strip(),
                "status_text": re.sub(r"<[^>]+>", "", status_text).strip(),
            }
        )
    return rows


def _parse_gaps_table(html: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    section = html
    m = re.search(r'id="gaps".*?(id="sanity"|</body>)', html, re.S | re.I)
    if m:
        section = m.group(0)
    for match in re.finditer(
        r"<tr><td>(.*?)</td><td class=\"([^\"]+)\">(.*?)</td><td>(.*?)</td></tr>",
        section,
        re.S,
    ):
        area, status_class, status_text, _impact = match.groups()
        rows.append(
            {
                "area": re.sub(r"<[^>]+>", "", area).strip(),
                "status_class": status_class.strip(),
                "status_text": re.sub(r"<[^>]+>", "", status_text).strip(),
            }
        )
    return rows


def verify(*, html_path: Path, repo: Path, gates_path: Path | None) -> list[str]:
    errors: list[str] = []
    html = _read(html_path)
    sanity_rows = _parse_sanity_table(html)
    live_sanity = [
        r
        for r in sanity_rows
        if ("yes" in r["status_class"] or "LIVE" in r["status_text"].upper())
        and "UNIT" not in r["status_text"].upper()
    ]
    default_test_file = repo / "tests/health/test_domain_recall_live_sanity.py"
    pytest_nodes = _collect_pytest_nodes(repo, default_test_file)

    for row in live_sanity:
        cmd = row["command"]
        if cmd.startswith("test_"):
            if cmd not in pytest_nodes:
                errors.append(f"sanity LIVE claims missing pytest: {cmd} ({row['check']})")
        elif cmd.startswith("scripts/"):
            script_path = cmd.split()[0]
            script = repo / script_path
            if not script.exists():
                errors.append(f"sanity LIVE claims missing script: {script_path} ({row['check']})")
        elif "test_" in cmd:
            for token in re.findall(r"test_[a-zA-Z0-9_]+", cmd):
                if token not in pytest_nodes:
                    errors.append(f"sanity LIVE references missing pytest token: {token}")

    if gates_path and gates_path.exists():
        try:
            import yaml
        except ImportError:
            errors.append("PyYAML required for --gates (pip install pyyaml)")
        else:
            data = yaml.safe_load(gates_path.read_text())
            for gate in data.get("gates") or []:
                if gate.get("status") != "LIVE":
                    continue
                proof = gate.get("proof") or {}
                if proof.get("type") == "pytest":
                    node = proof.get("node", "")
                    if node and node not in pytest_nodes:
                        errors.append(f"ACCEPTANCE_GATES LIVE gate missing pytest: {node} ({gate.get('id')})")
                if proof.get("type") == "script":
                    script = repo / proof.get("path", "")
                    if not script.exists():
                        errors.append(f"ACCEPTANCE_GATES LIVE gate missing script: {proof.get('path')} ({gate.get('id')})")

    if html.count("<h3>3.1 Roadmap priorities") > 1:
        errors.append("HTML contains duplicate §3.1 roadmap blocks")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", required=True)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--gates")
    args = parser.parse_args()
    html_path = Path(args.html).resolve()
    repo = Path(args.repo).resolve()
    gates = Path(args.gates).resolve() if args.gates else None
    if not html_path.exists():
        print(f"ERROR: HTML not found: {html_path}", file=sys.stderr)
        return 1
    errors = verify(html_path=html_path, repo=repo, gates_path=gates)
    if errors:
        print("DRIFT DETECTED — round not closable:\n", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(f"OK: {html_path} matches repo proof artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
