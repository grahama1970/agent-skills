"""Replay captured provider completion metadata through the production Ask adapter.

The network boundary is replaced with captured/modified responses. This is a
fault-injected regression, NOT live provider or ticket-closure evidence.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

# One CLI bootstrap for the skill's executable source-tree worker.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import tau_roundtable_worker as worker  # noqa: E402


def run_live(output: Path) -> int:
    """Exercise the public Ask -> Tau -> provider path with a fresh sentinel."""
    marker = "COMPLETE-ADMISSION-" + uuid.uuid4().hex[:12]
    runs = output.parent / (output.stem + "-runs")
    command = [str(ROOT / "run.sh"), "tau-dag", f"Reply with exactly {marker} and no other text.",
               "--repo", "grahama1970/agent-skills", "--target", "skills/ask",
               "--immutable-goal", "Prove complete-response admission; do not change files.",
               "--handler", "opencode-go/deepseek-v4-flash", "--execute", "--allow-provider-calls",
               "--execution-timeout-seconds", "120", "--run-output-root", str(runs), "--json"]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=150, check=False)
    evidence = []
    for meta_path in runs.glob("*/node-artifacts/handler-*/response.meta.json"):
        response_path = meta_path.with_name("response.md")
        if not response_path.exists() or response_path.read_text().strip() != marker:
            continue
        meta = json.loads(meta_path.read_text())
        node = json.loads(meta_path.with_name("node-receipt.json").read_text())
        evidence.append({"path": str(meta_path), "finish_reason": meta.get("finish_reason"),
                         "status": node.get("status"), "provider_live": node.get("provider_live"),
                         "model": meta.get("model"), "sentinel": marker})
    passed = (completed.returncode == 0 and len(evidence) == 1
              and evidence[0]["finish_reason"] == "stop" and evidence[0]["status"] == "PASS"
              and evidence[0]["provider_live"] is True)
    result = {"schema": "ask.completion_admission_live.v1", "live": True, "mocked": False,
              "command": command, "exit_code": completed.returncode, "evidence": evidence,
              "stderr": completed.stderr[-3000:], "passed": passed}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


def main() -> int:
    if "--live" in sys.argv:
        return run_live(Path(sys.argv[1]))
    captured = json.loads((ROOT / "fixtures/completion-admission/truncated-response.json").read_text())
    checks = []
    for name, reason, expected in [
        ("captured_length", "length", False),
        ("complete_positive", "stop", True),
        ("filtered", "content_filter", False),
        ("missing_finish_reason", None, False),
    ]:
        payload = copy.deepcopy(captured)
        payload["choices"][0]["finish_reason"] = reason
        if expected:
            payload["choices"][0]["message"]["content"] = "VERDICT: PASS\n"
        raw = json.dumps(payload)
        with TemporaryDirectory(prefix="ask-completion-admission-") as directory:
            root = Path(directory)
            prompt = root / "prompt.md"
            prompt.write_text("Validate completion admission; no live provider call.")
            args = SimpleNamespace(scillm_base_url="http://fixture.invalid", scillm_api_key="fixture-key-not-secret", timeout=5, attach_files=[], provider_hint="")
            response = SimpleNamespace(status=200, read=lambda: raw.encode())
            transport = patch.object(worker.urllib.request, "urlopen")
            accepted, errors = False, []
            with transport as request:
                request.return_value.__enter__.return_value = response
                try:
                    text, meta = worker._run_scillm_handler(
                        args, handler="claude-fable-low", prompt_path=prompt,
                        response_path=root / "response.md", raw_path=root / "raw.json",
                        meta_path=root / "meta.json",
                    )
                    accepted = bool(text)
                except Exception as exc:
                    errors = exc.errors(include_input=False) if hasattr(exc, "errors") else [{"type": type(exc).__name__, "msg": str(exc)}]
            meta_path = root / "meta.json"
            meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
            raw_preserved = (root / "raw.json").read_text() == raw
            metadata_preserved = meta.get("finish_reason") == reason and "finish_reason" in meta
            rejected_output_absent = expected or not (root / "response.md").exists()
            passed = accepted == expected and raw_preserved and metadata_preserved and rejected_output_absent
            if not expected:
                code = worker._classify_handler_failure(handler="claude-fable-low", failure="", submit_meta=meta)
                passed = (passed and bool(errors) and bool(meta.get("validation_errors"))
                          and code == "scillm_response_incomplete"
                          and worker._handler_auto_retry_blocked_reason(code) == "provider_completion_requires_output_contract_repair")
            checks.append({"name": name, "expected_accepted": expected, "accepted": accepted,
                           "raw_preserved": raw_preserved, "metadata_preserved": metadata_preserved,
                           "rejected_output_absent": rejected_output_absent,
                           "errors": errors, "passed": passed})
    result = {"schema": "ask.completion_admission_eval.v1", "mocked": True,
              "live": False, "checks": checks, "passed": all(c["passed"] for c in checks)}
    output = Path(sys.argv[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
