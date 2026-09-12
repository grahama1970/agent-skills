#!/usr/bin/env python3
"""Regression: `$shame` advisory/read-only questions must stay plain.

The guard should require pi.agent_status.v1 for mutating turns, strict mode, task
budgets, active continuation, and format-only retries. A read-only question that
mentions/invokes $shame must not become strict just because the token appeared;
that was the visible retry friction seen on normal answers.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CHECKER = ROOT / "extensions" / "pi" / "lazy-report-shame-shame-shame" / "status-json-check.mjs"
INDEX = ROOT / "extensions" / "pi" / "lazy-report-shame-shame-shame" / "index.ts"


def run_checker(*, force: bool = False, mutating: bool = False, strict: bool = False) -> tuple[int, dict]:
    env = os.environ.copy()
    env.update(
        {
            "LRSSS_FORCE_STATUS": "1" if force else "0",
            "LRSSS_MUTATING_TURN": "1" if mutating else "0",
            "LRSSS_STRICT_STATUS": "1" if strict else "0",
        }
    )
    proc = subprocess.run(
        ["node", str(CHECKER)],
        input="Plain answer to a read-only shame ecosystem question.\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=20,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"checker did not emit JSON: {proc.stdout!r} stderr={proc.stderr!r}") from exc
    return proc.returncode, payload


def main() -> int:
    checks: list[dict[str, object]] = []

    def check(name: str, passed: bool, detail: object | None = None) -> None:
        row: dict[str, object] = {"name": name, "passed": bool(passed)}
        if detail is not None:
            row["detail"] = detail
        checks.append(row)

    index_text = INDEX.read_text(encoding="utf-8")
    check("source_strictness_is_retry_only", "const strictStatus = formatRepairTurn;" in index_text)
    check("source_does_not_make_shame_token_strict", "const strictStatus = shameSelfCorrectTurn;" not in index_text)

    code, payload = run_checker()
    check(
        "plain_non_mutating_answer_passes_without_status",
        code == 0 and payload.get("decision") == "pass" and "no_status_required_non_mutating_turn" in payload.get("reason_codes", []),
        {"code": code, "reason_codes": payload.get("reason_codes")},
    )

    code, payload = run_checker(mutating=True)
    check(
        "mutating_answer_still_requires_status",
        code != 0 and payload.get("decision") == "reject" and "missing_agent_status_json" in payload.get("reason_codes", []),
        {"code": code, "reason_codes": payload.get("reason_codes")},
    )

    code, payload = run_checker(strict=True)
    check(
        "format_retry_strictness_still_requires_status",
        code != 0 and payload.get("decision") == "reject" and "missing_agent_status_json" in payload.get("reason_codes", []),
        {"code": code, "reason_codes": payload.get("reason_codes")},
    )

    passed = all(bool(c["passed"]) for c in checks)
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/shame-advisory-question-scope.json")
    out.write_text(
        json.dumps(
            {
                "schema": "shame.advisory_question_scope_eval.v1",
                "mocked": False,
                "live": False,
                "passed": passed,
                "checks": checks,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"passed": passed, "failing": [c["name"] for c in checks if not c["passed"]]}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
