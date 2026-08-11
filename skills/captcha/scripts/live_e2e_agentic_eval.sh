#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

if [[ "${CAPTCHA_LIVE_E2E:-}" != "1" ]]; then
  printf 'CAPTCHA_LIVE_E2E_NOT_CONFIGURED: set CAPTCHA_LIVE_E2E=1 after starting the authorized loopback ReCAP dynamic target, loopback OpenAI-compatible model endpoint, Surf transport, and pinned ReCAP runtime.\n' >&2
  exit 2
fi

python - "$SKILL_DIR" "$TMP_DIR" <<'PY'
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import uuid
from pathlib import Path

SKILL_DIR = Path(sys.argv[1])
TMP_DIR = Path(sys.argv[2])
RECAP_COMMIT = "577c7728ed159756a6cb6cbd1a58897fe288f73e"
DEFAULT_TYPES = [
    "text",
    "compact_text",
    "icon_selection",
    "icon_match",
    "slider",
    "image_grid",
    "paged",
]


def run_json(command: list[str], output_path: Path) -> dict[str, object]:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=int(os.environ.get("CAPTCHA_LIVE_COMMAND_TIMEOUT_SECONDS", "4200")),
    )
    output_path.write_text(result.stdout, encoding="utf-8")
    (output_path.with_suffix(output_path.suffix + ".stderr")).write_text(
        result.stderr,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise SystemExit(
            json.dumps(
                {
                    "schema_version": "captcha.nondeterministic_live_agentic_eval.v1",
                    "status": "BLOCKED",
                    "failure_code": "live_command_failed",
                    "command": command,
                    "exit_code": result.returncode,
                    "stdout_path": str(output_path),
                    "stderr_path": str(output_path.with_suffix(output_path.suffix + ".stderr")),
                    "stdout": result.stdout[-4000:],
                    "stderr": result.stderr[-4000:],
                },
                indent=2,
                sort_keys=True,
            )
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            json.dumps(
                {
                    "schema_version": "captcha.nondeterministic_live_agentic_eval.v1",
                    "status": "BLOCKED",
                    "failure_code": "live_command_invalid_json",
                    "command": command,
                    "error": str(exc),
                    "stdout_path": str(output_path),
                    "stderr_path": str(output_path.with_suffix(output_path.suffix + ".stderr")),
                },
                indent=2,
                sort_keys=True,
            )
        ) from exc


def positive_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise SystemExit(f"{name} must be between {minimum} and {maximum}")
    return value


rounds = positive_int_env("CAPTCHA_LIVE_NONDETERMINISTIC_ROUNDS", 3, 2, 12)
test_size_min = positive_int_env("CAPTCHA_LIVE_TEST_SIZE_MIN", 1, 1, 10)
test_size_max = positive_int_env("CAPTCHA_LIVE_TEST_SIZE_MAX", 3, test_size_min, 10)
captcha_types = [
    item.strip()
    for item in os.environ.get("CAPTCHA_LIVE_CAPTCHA_TYPES", ",".join(DEFAULT_TYPES)).split(",")
    if item.strip()
]
if not captcha_types:
    raise SystemExit("CAPTCHA_LIVE_CAPTCHA_TYPES must include at least one type")
unknown_types = sorted(set(captcha_types) - set(DEFAULT_TYPES))
if unknown_types:
    raise SystemExit(f"unsupported CAPTCHA_LIVE_CAPTCHA_TYPES: {unknown_types}")

rng = random.SystemRandom()
nonce = uuid.uuid4().hex
selected: list[dict[str, object]] = []
receipts: list[dict[str, object]] = []
used_seeds: set[int] = set()

for index in range(rounds):
    captcha_name = rng.choice(captcha_types)
    seed = rng.randrange(0, 2_147_483_647)
    while seed in used_seeds:
        seed = rng.randrange(0, 2_147_483_647)
    used_seeds.add(seed)
    test_size = rng.randint(test_size_min, test_size_max)
    max_tasks = max(test_size, int(os.environ.get("CAPTCHA_LIVE_MAX_TASKS", str(test_size))))
    manifest = {
        "schema_version": "captcha.target_authorization.v1",
        "authorization_id": f"recap-live-agentic-eval-{nonce[:10]}-{index + 1}",
        "project": os.environ.get("CAPTCHA_LIVE_PROJECT", "captcha-live-agentic-eval"),
        "operator": os.environ.get("CAPTCHA_LIVE_OPERATOR", "agent-skills-maintainer"),
        "purpose": (
            "Run a nondeterministic opt-in live local ReCAP synthetic CAPTCHA "
            "benchmark campaign for agentic evaluation evidence."
        ),
        "target_url": os.environ.get("CAPTCHA_LIVE_TARGET_URL", "http://127.0.0.1:5000"),
        "model_base_url": os.environ.get("CAPTCHA_LIVE_MODEL_BASE_URL", "http://127.0.0.1:8000/v1"),
        "model_id": os.environ.get("CAPTCHA_LIVE_MODEL_ID", "ReCAP-Agent/ReCAP-8B"),
        "model_family": "qwen3",
        "provider": "dynamic",
        "test_mode": "custom",
        "captcha_name": captcha_name,
        "test_size": test_size,
        "seed": seed,
        "workers": int(os.environ.get("CAPTCHA_LIVE_WORKERS", "1")),
        "max_calls": int(os.environ.get("CAPTCHA_LIVE_MAX_CALLS", "4")),
        "max_tasks": max_tasks,
        "timeout_seconds": int(os.environ.get("CAPTCHA_LIVE_TIMEOUT_SECONDS", "900")),
        "allowed_actions": ["evaluate", "verify"],
        "allowed_captcha_types": [captcha_name],
        "recap_commit": RECAP_COMMIT,
        "expires_at": os.environ.get("CAPTCHA_LIVE_EXPIRES_AT", "2030-01-01T00:00:00Z"),
        "acknowledgements": {
            "owns_or_controls_target": True,
            "local_synthetic_only": True,
            "no_third_party_bypass": True,
            "defensive_or_research_use": True,
        },
    }
    manifest_path = TMP_DIR / f"captcha-live-authorization-{index + 1}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    run_json(
        [
            str(SKILL_DIR / "run.sh"),
            "authorization-preflight",
            "--manifest",
            str(manifest_path),
            "--action",
            "evaluate",
            "--json",
        ],
        TMP_DIR / f"authorization-{index + 1}.json",
    )
    evaluate = run_json(
        [
            str(SKILL_DIR / "run.sh"),
            "evaluate",
            "--manifest",
            str(manifest_path),
            "--recap-root",
            os.environ.get(
                "CAPTCHA_LIVE_RECAP_ROOT",
                "/mnt/storage12tb/skills/captcha/vendor/ReCAP-Agent",
            ),
            "--recap-python",
            os.environ.get(
                "CAPTCHA_LIVE_RECAP_PYTHON",
                "/mnt/storage12tb/skills/captcha/vendor/ReCAP-Agent/.venv/bin/python",
            ),
            "--output-root",
            os.environ.get("CAPTCHA_LIVE_OUTPUT_ROOT", "/mnt/storage12tb/skills/captcha/outputs"),
            "--execute",
            "--json",
        ],
        TMP_DIR / f"evaluate-{index + 1}.json",
    )
    run_dir = evaluate.get("run_dir")
    if not isinstance(run_dir, str) or not run_dir:
        raise SystemExit("evaluate output did not include run_dir")
    verify = run_json(
        [str(SKILL_DIR / "run.sh"), "verify", "--run-dir", run_dir, "--json"],
        TMP_DIR / f"verify-{index + 1}.json",
    )
    if evaluate.get("schema_version") != "captcha.run_receipt.v1":
        raise SystemExit("evaluate receipt schema mismatch")
    if evaluate.get("status") != "PASS":
        raise SystemExit("evaluate did not PASS")
    if evaluate.get("bounded_judgment") != "CAPABILITY_MEASURED":
        raise SystemExit("live capability was not measured")
    if verify.get("status") != "PASS":
        raise SystemExit("verify did not PASS")
    selected.append(
        {
            "round": index + 1,
            "captcha_name": captcha_name,
            "seed": seed,
            "test_size": test_size,
            "run_dir": run_dir,
        }
    )
    receipts.append(evaluate)

unique_seed_count = len({item["seed"] for item in selected})
unique_type_count = len({item["captcha_name"] for item in selected})
if unique_seed_count < rounds:
    raise SystemExit("nondeterministic seed selection unexpectedly repeated")

summary = {
    "schema_version": "captcha.nondeterministic_live_agentic_eval.v1",
    "status": "PASS",
    "nondeterministic_live_e2e_verified": True,
    "mocked": False,
    "live": True,
    "fixture_backed": False,
    "rounds": rounds,
    "unique_seed_count": unique_seed_count,
    "unique_type_count": unique_type_count,
    "sampled_parameters": selected,
    "receipt_schemas": sorted({str(receipt.get("schema_version")) for receipt in receipts}),
    "bounded_judgments": sorted({str(receipt.get("bounded_judgment")) for receipt in receipts}),
    "run_dirs": [item["run_dir"] for item in selected],
    "claims": {
        "proves": (
            "the authorized local ReCAP evaluation path executed multiple live "
            "synthetic CAPTCHA runs with randomized seeds/types and verified "
            "each durable run receipt"
        ),
        "does_not_prove": (
            "permission or capability to bypass third-party CAPTCHAs, behavior "
            "outside the pinned ReCAP commit, or release readiness"
        ),
    },
}
print(json.dumps(summary, indent=2, sort_keys=True))
print("captcha.run_receipt.v1")
print("CAPABILITY_MEASURED")
print("nondeterministic_live_e2e_verified")
PY
