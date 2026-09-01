#!/usr/bin/env python3
"""Retained contract check for session-mood recognition status propagation."""
from __future__ import annotations

import importlib.util
import json
import stat
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MOD = REPO / "persona-dream/scripts/live_chain_receipt.py"
SOURCE_RECEIPT = REPO / (
    "persona-dream/reports/goal_v5/continuity/reliability/"
    "soak35_after_1130/cycle_003/voice_recognition/RECEIPT.json"
)

spec = importlib.util.spec_from_file_location("live_chain_receipt", MOD)
lcr = importlib.util.module_from_spec(spec)
sys.modules["live_chain_receipt"] = lcr
assert spec.loader is not None
spec.loader.exec_module(lcr)

failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + detail) if detail and not cond else ""))
    if not cond:
        failures.append(name)


def stub(body: str) -> Path:
    path = Path(tempfile.mkdtemp(prefix="pd-stub-")) / "stub-python"
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "out = pathlib.Path(args[args.index('--out') + 1])\n"
        "out.parent.mkdir(parents=True, exist_ok=True)\n"
        + body
        + "\nsys.stderr.write('stub stderr tail\\n')\nsys.exit(1)\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


def run(body: str) -> BaseException:
    out = Path(tempfile.mkdtemp(prefix="pd-out-")) / "voice_recognition" / "RECEIPT.json"
    try:
        lcr.run_recognition(REPO / "does-not-matter.json", out, stub(body))
    except BaseException as exc:  # noqa: BLE001 - exception identity is the contract under test
        return exc
    raise AssertionError("run_recognition did not raise on a non-zero child")


real = json.loads(SOURCE_RECEIPT.read_text(encoding="utf-8"))
blocked = deepcopy(real)
blocked["status"] = "BLOCKED_SESSION_MOOD_VOICE_RECOGNITION"
blocked["failed_gates"] = ["all_renders_recognized_as_embry"]

check("source_artifact_is_current_pass", real["status"] == "PASS_SESSION_MOOD_VOICE_RECOGNITION")
check("source_artifact_has_gate_counterexample", any(r.get("passes_duration_aware_floor") is False for r in real["genuine_renders"]))
check("blocked_fixture_is_domain_blocked", blocked["status"] == "BLOCKED_SESSION_MOOD_VOICE_RECOGNITION")
check("blocked_fixture_failed_gate", blocked["failed_gates"] == ["all_renders_recognized_as_embry"])
check("blocked_fixture_backend_error_null", blocked["backend_error"] is None)

exc = run(f"out.write_text({json.dumps(json.dumps(blocked))}, encoding='utf-8')")
DomainBlocked = getattr(lcr, "RecognitionDomainBlocked", None)
check("domain_block_type", DomainBlocked is not None and isinstance(exc, DomainBlocked), type(exc).__name__)
msg = str(exc)
check("domain_block_not_command_failed", "BLOCKED_RECOGNITION_COMMAND_FAILED" not in msg)
check("domain_block_status_in_message", "BLOCKED_SESSION_MOOD_VOICE_RECOGNITION" in msg)
check("domain_block_stage_token_preserved", "BLOCKED_RECOGNITION" in msg)
d = getattr(exc, "detail", {})
check("detail_status", d.get("status") == "BLOCKED_SESSION_MOOD_VOICE_RECOGNITION")
check("detail_failed_gates", d.get("failed_gates") == ["all_renders_recognized_as_embry"])
check("detail_min_threshold", (d.get("preregistered_thresholds") or {}).get("min_embry_similarity") == 0.75)
check("detail_separation", d.get("separation") == blocked["separation"])
check("detail_backend_error_key", "backend_error" in d and d["backend_error"] is None)
check("detail_child_returncode", (d.get("child_process") or {}).get("returncode") == 1)
check("detail_child_stderr_tail", "stub stderr tail" in (d.get("child_process") or {}).get("stderr_tail", ""))
scores = d.get("genuine_renders") or []
check("detail_per_render_count", len(scores) == len(blocked["genuine_renders"]))
check("detail_per_render_similarity", any(r.get("similarity_to_embry") == 0.750938 for r in scores))
check(
    "detail_duration_aware_floor",
    [r.get("duration_aware_floor") for r in scores]
    == [r.get("duration_aware_floor") for r in blocked["genuine_renders"]]
    and 0.765504 in [r.get("duration_aware_floor") for r in scores],
)
check("detail_render_gate_flags", any(r.get("passes_duration_aware_floor") is False for r in scores))
adv = d.get("adversarial_voices") or []
check("detail_adversarial_scores", len(adv) == len(blocked["adversarial_voices"]) and all("similarity_to_embry" in r for r in adv))
check("detail_receipt_sha256", str(d.get("sha256", "")).startswith("sha256:"))
check("detail_marked_propagated", d.get("propagated_from_child_receipt") is True)

mocked = dict(blocked, mocked=True)
passing = dict(blocked, status="PASS_SESSION_MOOD_VOICE_RECOGNITION", failed_gates=[])
unknown = dict(blocked, status="BLOCKED_SOMETHING_ELSE")
noschema = {k: v for k, v in blocked.items() if k != "schema"}
nogates = dict(blocked, failed_gates=[])
negatives = {
    "missing_receipt": "pass",
    "malformed_receipt": "out.write_text('{not json', encoding='utf-8')",
    "unreadable_receipt": "out.write_bytes(b'\\xff\\xfe\\x00garbage')",
    "wrong_schema": f"out.write_text({json.dumps(json.dumps(noschema))}, encoding='utf-8')",
    "mocked_receipt": f"out.write_text({json.dumps(json.dumps(mocked))}, encoding='utf-8')",
    "unrecognized_status": f"out.write_text({json.dumps(json.dumps(unknown))}, encoding='utf-8')",
    "passing_status_with_nonzero_exit": f"out.write_text({json.dumps(json.dumps(passing))}, encoding='utf-8')",
    "blocked_without_failed_gates": f"out.write_text({json.dumps(json.dumps(nogates))}, encoding='utf-8')",
}
for name, body in negatives.items():
    exc = run(body)
    check(
        f"command_failed_reserved_for_{name}",
        type(exc) is RuntimeError and str(exc).startswith("BLOCKED_RECOGNITION_COMMAND_FAILED:"),
        f"{type(exc).__name__}:{str(exc)[:120]}",
    )

rec_src = (REPO / "persona-dream/scripts/session_mood_voice_recognition.py").read_text(encoding="utf-8")
check(
    "recognition_thresholds_unchanged",
    "MIN_EMBRY_SIMILARITY = 0.75" in rec_src and "MIN_REFERENCE_PROVENANCE_SIMILARITY = 0.75" in rec_src,
    "threshold literal not found",
)
check("recognition_gate_still_enforced", 'failed_gates.append("all_renders_recognized_as_embry")' in rec_src)
lcr_src = MOD.read_text(encoding="utf-8")
check("parent_still_validates_pass_receipts", 'raise ValueError("BLOCKED_RECOGNITION_RECEIPT_FAILED")' in lcr_src)

print(json.dumps({"failures": failures}, sort_keys=True))
if failures:
    sys.exit(1)
print("RECOGNITION_STATUS_CONTRACT_OK")
