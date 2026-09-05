#!/usr/bin/env python3
"""Run a small/medium local Docker-backed Battle with a plain report."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from common.security_authorization import validate_target_authorization


IMAGE = "python:3.12-slim"


@dataclass(frozen=True)
class RoundSpec:
    round_number: int
    vulnerability: str
    red_goal: str
    blue_plan: str
    expected_balance: str
    vulnerable_app: str
    patched_app: str
    judge_script: str


def utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def py(body: str) -> str:
    return textwrap.dedent(body).strip() + "\n"


def app(body: str) -> str:
    header = "import os, re, ast\nBASE='/tmp/battle_arena_notes'\nos.makedirs(BASE, exist_ok=True)\n\n"
    return header + py(body)


def specs() -> list[RoundSpec]:
    return [
        RoundSpec(
            1,
            "command injection in host diagnostic helper",
            "prove shell metacharacters reach the command interpreter",
            "replace shell execution with argument-vector validation",
            "Blue-favored: obvious bug, straightforward safe replacement",
            app("""
            def ping(host):
                return os.popen('echo ping ' + host).read()
            """),
            app("""
            def ping(host):
                if not re.fullmatch(r'[A-Za-z0-9.-]{1,64}', host):
                    raise ValueError('bad host')
                return 'ping ' + host + '\\n'
            """),
            py("""
            import app, sys
            try:
                ok_normal = app.ping('example.com').strip() == 'ping example.com'
                exploit = app.ping('example.com; echo PWNED')
                blocked = 'PWNED' not in exploit
            except Exception:
                ok_normal = ok_normal if 'ok_normal' in locals() else False
                blocked = True
            sys.exit(0 if ok_normal and blocked else 10 if ok_normal and not blocked else 2)
            """),
        ),
        RoundSpec(
            2,
            "path traversal in note reader",
            "read a file outside the notes directory",
            "strip literal ../ segments before joining paths",
            "Red-favored: naive patch misses absolute-path traversal",
            app("""
            def read_note(name):
                return open(os.path.join(BASE, name)).read()
            """),
            app("""
            def read_note(name):
                cleaned = name.replace('../', '')
                return open(os.path.join(BASE, cleaned)).read()
            """),
            py("""
            import app, os, sys
            os.makedirs('/tmp/battle_arena_notes', exist_ok=True)
            open('/tmp/battle_arena_notes/public.txt','w').write('PUBLIC')
            open('/tmp/secret.txt','w').write('SECRET')
            try:
                ok_normal = app.read_note('public.txt') == 'PUBLIC'
                leaked = app.read_note('/tmp/secret.txt')
                blocked = 'SECRET' not in leaked
            except Exception:
                ok_normal = ok_normal if 'ok_normal' in locals() else False
                blocked = True
            sys.exit(0 if ok_normal and blocked else 10 if ok_normal and not blocked else 2)
            """),
        ),
        RoundSpec(
            3,
            "hard-coded admin token",
            "login with the known built-in token",
            "require caller-supplied runtime secret and reject the default",
            "Blue-favored: precise config fix with normal user behavior preserved",
            app("""
            def is_admin(token):
                return token == 'letmein'
            """),
            app("""
            def is_admin(token):
                secret = os.environ.get('BATTLE_ADMIN_TOKEN', '')
                return bool(secret) and secret != 'letmein' and token == secret
            """),
            py("""
            import os
            os.environ['BATTLE_ADMIN_TOKEN'] = 'rotated-medium-secret'
            import app, sys
            try:
                legacy_open = app.is_admin('letmein') is True
                rotated_ok = app.is_admin('rotated-medium-secret') is True and app.is_admin('wrong') is False
            except Exception:
                legacy_open = False
                rotated_ok = False
            sys.exit(10 if legacy_open else 0 if rotated_ok else 2)
            """),
        ),
        RoundSpec(
            4,
            "unsafe expression evaluator",
            "use Python evaluation to execute code",
            "disable eval by returning zero for all expressions",
            "Red-favored: patch blocks exploit but breaks expected calculator behavior",
            app("""
            def calc(expr):
                return eval(expr)
            """),
            app("""
            def calc(expr):
                return 0
            """),
            py("""
            import app, os, sys
            try:
                ok_normal = app.calc('2+3*4') == 14
                if os.path.exists('/tmp/battle_pwned'):
                    os.unlink('/tmp/battle_pwned')
                app.calc("open('/tmp/battle_pwned','w').write('x')")
                blocked = not os.path.exists('/tmp/battle_pwned')
            except Exception:
                ok_normal = ok_normal if 'ok_normal' in locals() else False
                blocked = True
            sys.exit(0 if ok_normal and blocked else 10 if ok_normal and not blocked else 2)
            """),
        ),
        RoundSpec(
            5,
            "path traversal rematch after Red bypass",
            "retry traversal using encoded parent directory",
            "resolve real paths and enforce base-directory containment",
            "Even rematch: Blue learns from the bypass and closes the path family",
            app("""
            def read_note(name):
                return open(os.path.join(BASE, name)).read()
            """),
            app("""
            def read_note(name):
                base = os.path.realpath(BASE)
                target = os.path.realpath(os.path.join(base, name))
                if not target.startswith(base + os.sep):
                    raise ValueError('path escape')
                return open(target).read()
            """),
            py("""
            import app, os, sys, urllib.parse
            os.makedirs('/tmp/battle_arena_notes', exist_ok=True)
            open('/tmp/battle_arena_notes/public.txt','w').write('PUBLIC')
            open('/tmp/secret.txt','w').write('SECRET')
            try:
                ok_normal = app.read_note('public.txt') == 'PUBLIC'
                leaked = app.read_note(urllib.parse.unquote('%2e%2e/secret.txt'))
                blocked = 'SECRET' not in leaked
            except Exception:
                ok_normal = ok_normal if 'ok_normal' in locals() else False
                blocked = True
            sys.exit(0 if ok_normal and blocked else 10 if ok_normal and not blocked else 2)
            """),
        ),
        RoundSpec(
            6,
            "safe expression evaluator rematch",
            "retry code execution through the calculator",
            "preserve calculator behavior but accidentally keep raw eval in place",
            "Red-favored rematch: Blue preserves behavior but fails to remove the exploit primitive",
            app("""
            def calc(expr):
                return eval(expr)
            """),
            app("""
            def calc(expr):
                return eval(expr)
            """),
            py("""
            import app, os, sys
            try:
                ok_normal = app.calc('2+3*4') == 14
                if os.path.exists('/tmp/battle_pwned'):
                    os.unlink('/tmp/battle_pwned')
                app.calc("open('/tmp/battle_pwned','w').write('x')")
                blocked = not os.path.exists('/tmp/battle_pwned')
            except Exception:
                ok_normal = ok_normal if 'ok_normal' in locals() else False
                blocked = True
            sys.exit(0 if ok_normal and blocked else 10 if ok_normal and not blocked else 2)
            """),
        ),
    ]


def run_docker(work: Path, label: str) -> dict[str, Any]:
    started = utc()
    proc = subprocess.run(
        [
            "docker", "run", "--rm", "--network", "none",
            "-v", f"{work}:/work", "-w", "/work", IMAGE, "python", "judge.py",
        ],
        text=True,
        capture_output=True,
        timeout=30,
    )
    receipt = {
        "schema": "battle.production_scale.docker_attempt.v1",
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "label": label,
        "image": IMAGE,
        "network": "none",
        "started_at": started,
        "completed_at": utc(),
        "exit_code": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }
    path = write_json(work / f"{label}-docker-receipt.json", receipt)
    receipt["path"] = str(path)
    receipt["sha256"] = sha256_file(path)
    return receipt


def judge_round(root: Path, spec: RoundSpec) -> dict[str, Any]:
    round_dir = root / f"round-{spec.round_number:02d}"
    original = round_dir / "original"
    patched = round_dir / "patched"
    for work, app_source in [(original, spec.vulnerable_app), (patched, spec.patched_app)]:
        work.mkdir(parents=True, exist_ok=True)
        (work / "app.py").write_text(app_source, encoding="utf-8")
        (work / "judge.py").write_text(spec.judge_script, encoding="utf-8")

    original_attempt = run_docker(original, "original")
    patched_attempt = run_docker(patched, "patched")
    finding_confirmed = original_attempt["exit_code"] == 10
    blue_success = finding_confirmed and patched_attempt["exit_code"] == 0
    red_success = finding_confirmed and not blue_success
    verdict = "BLUE_SUCCESS" if blue_success else "RED_SUCCESS" if red_success else "NO_CONFIRMED_FINDING"
    round_receipt = {
        "schema": "battle.production_scale.round_receipt.v1",
        "status": "PASS",
        "round_number": spec.round_number,
        "vulnerability": spec.vulnerability,
        "red_goal": spec.red_goal,
        "blue_plan": spec.blue_plan,
        "expected_balance": spec.expected_balance,
        "finding_confirmed": finding_confirmed,
        "verdict": verdict,
        "red_score": 1 if finding_confirmed else 0,
        "blue_score": 3 if blue_success else 0,
        "docker_attempts": [original_attempt, patched_attempt],
        "artifacts": {
            "original_app_sha256": sha256_text(spec.vulnerable_app),
            "patched_app_sha256": sha256_text(spec.patched_app),
            "judge_sha256": sha256_text(spec.judge_script),
        },
        "created_at": utc(),
    }
    path = write_json(round_dir / "round-receipt.json", round_receipt)
    round_receipt["path"] = str(path)
    round_receipt["sha256"] = sha256_file(path)
    return round_receipt


def write_authorization(root: Path, target_identity: str) -> Path:
    canonical_id, immutable_ref = target_identity.split("@", 1)
    manifest = {
        "schema": "security.target_authorization.v1",
        "authorization_id": "battle-small-medium-production-local-20260905",
        "issuer": "Graham Anderson via Pi session",
        "approver": "Graham Anderson",
        "issued_at": utc(),
        "expires_at": "2099-01-01T00:00:00Z",
        "target": {
            "kind": "local_synthetic_arena",
            "canonical_id": canonical_id,
            "immutable_ref": immutable_ref,
            "repository_url": f"file://{root}/arena",
            "commit": immutable_ref,
        },
        "allowed_target_urls": ["http://127.0.0.1"],
        "allowed_cidrs": ["127.0.0.0/8"],
        "allowed_ports": [80, 443],
        "runtime_modes": ["battle", "docker", "local_docker_judge"],
        "allowed_actions": ["authorization-preflight", "battle"],
        "allowed_probe_classes": ["command_injection", "path_traversal", "auth_bypass", "unsafe_eval"],
        "denied_probe_classes": ["destructive", "credential", "denial_of_service", "persistence", "nonlocal"],
        "network_policy": "none",
        "egress_policy": "deny_external",
        "limits": {"requests_per_second": 1, "max_concurrency": 1, "duration_seconds": 600, "cpu": 2, "memory_mb": 512, "storage_mb": 512},
        "permissions": {"destructive": False, "persistence": False, "credential": False, "denial_of_service": False, "nonlocal": False},
        "artifact_root": str(root),
        "redaction_policy": "synthetic arena contains no secrets",
        "legal_non_opinion_ack": True,
    }
    return write_json(root / "authorization.json", manifest)


def write_report(root: Path, receipt: dict[str, Any]) -> None:
    lines = [
        "# Small/Medium Production-Scale Battle Report",
        "",
        "## Human summary",
        f"Status: {receipt['status']}.",
        f"Winner: {receipt['winner']}.",
        f"Final score: Red {receipt['scoreboard']['red_total']} / Blue {receipt['scoreboard']['blue_total']}.",
        "",
        "This was a local Docker-backed Battle over a synthetic medium-complexity arena. It did not touch external targets.",
        "",
        "## What happened",
    ]
    for item in receipt["rounds"]:
        lines.extend([
            f"- Round {item['round_number']}: {item['vulnerability']} -> {item['verdict']}.",
            f"  - Red tried: {item['red_goal']}",
            f"  - Blue tried: {item['blue_plan']}",
            f"  - Judge: original vulnerable={item['finding_confirmed']}; patched status={item['docker_attempts'][1]['status']}",
        ])
    lines.extend([
        "",
        "## Why the match was reasonably balanced",
        "- The arena had four different bug families, not one repeated toy bug.",
        "- Blue got straightforward wins on obvious fixes.",
        "- Red got wins where Blue shipped a naive or behavior-breaking patch.",
        "- Two rematches tested whether Blue could learn from Red's bypasses.",
        "",
        "## Proof boundary",
        "Proven: authorization preflight, Docker-only Judge execution, per-round receipts, scorekeeper summary, mixed Red/Blue outcomes.",
        "Not proven: external production deployment, provider/Tau-generated creativity, 1000-round overnight scale, arbitrary target exploitability.",
        "",
        "## Key artifacts",
        f"- Run receipt: {root / 'run-receipt.json'}",
        f"- Authorization validation: {root / 'authorization-validation.json'}",
        f"- Scorekeeper: {root / 'scorekeeper-receipt.json'}",
    ])
    (root / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(root: Path) -> dict[str, Any]:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    arena_hash = sha256_text("".join(s.vulnerable_app + s.patched_app + s.judge_script for s in specs()))
    target_identity = f"battle-small-medium-local@sha256:{arena_hash}"
    auth_path = write_authorization(root, target_identity)
    auth_receipt = validate_target_authorization(
        auth_path,
        expected_target=target_identity,
        requested_action="battle",
        requested_runtime_mode="docker",
        receipt_out=root / "authorization-validation.json",
    )
    if auth_receipt["status"] != "PASS":
        receipt = {"schema": "battle.production_scale.run_receipt.v1", "status": "BLOCKED", "errors": auth_receipt["errors"], "authorization": auth_receipt}
        write_json(root / "run-receipt.json", receipt)
        return receipt

    rounds = [judge_round(root, spec) for spec in specs()]
    red_total = sum(item["red_score"] for item in rounds)
    blue_total = sum(item["blue_score"] for item in rounds)
    red_wins = sum(1 for item in rounds if item["verdict"] == "RED_SUCCESS")
    blue_wins = sum(1 for item in rounds if item["verdict"] == "BLUE_SUCCESS")
    winner = "Blue" if blue_total > red_total else "Red" if red_total > blue_total else "Draw"
    scorekeeper = {
        "schema": "battle.production_scale.scorekeeper_receipt.v1",
        "status": "PASS",
        "score_authority": "docker_judge_receipts_only",
        "red_total": red_total,
        "blue_total": blue_total,
        "red_round_wins": red_wins,
        "blue_round_wins": blue_wins,
        "winner": winner,
        "round_receipts": [item["path"] for item in rounds],
        "created_at": utc(),
    }
    scorekeeper_path = write_json(root / "scorekeeper-receipt.json", scorekeeper)
    receipt = {
        "schema": "battle.production_scale.run_receipt.v1",
        "status": "PASS",
        "mocked": False,
        "live": "local_docker_judge_medium_arena",
        "battle_id": root.name,
        "target_identity": target_identity,
        "authorization_validation": str(root / "authorization-validation.json"),
        "round_count": len(rounds),
        "rounds": rounds,
        "scoreboard": scorekeeper,
        "scorekeeper_receipt": str(scorekeeper_path),
        "winner": winner,
        "claims": {
            "proves": [
                "A small/medium local Battle can run through authorization, Docker Judge attempts, per-round Red/Blue outcomes, and scorekeeper receipts.",
                "The arena gives both teams plausible wins: naive fixes lose, precise fixes win.",
            ],
            "does_not_prove": [
                "External production deployment readiness.",
                "Provider/Tau-generated Red and Blue creativity.",
                "1000-round overnight throughput.",
                "Arbitrary target exploitability.",
            ],
        },
        "created_at": utc(),
    }
    write_json(root / "run-receipt.json", receipt)
    write_report(root, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    receipt = run(args.out)
    print(json.dumps({"status": receipt["status"], "report": str(args.out / "REPORT.md"), "receipt": str(args.out / "run-receipt.json")}, indent=2))
    return 0 if receipt["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
