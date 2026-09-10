"""Service-backed proof for immutable regression replay identity.

The proof starts a real local HTTP service, runs the documented agentic-evals
entrypoint against it, and writes a JSON result. It demonstrates the false-green
negative from issue #1631: changing only the test locator can make the broken
service command exit 0, but the original evidence slot remains unmet because the
test generation changed. Repairing the service and replaying the original test
unchanged is then accepted.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import provenance as prov  # noqa: E402


class _Handler(BaseHTTPRequestHandler):
    state_path: Path

    def do_GET(self) -> None:
        if self.path != "/state":
            self.send_response(404)
            self.end_headers()
            return
        payload = self.state_path.read_bytes()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _case(name: str, qid: str, url: str, receipt: Path, *, mutation: bool = False) -> dict[str, Any]:
    script = ROOT / "scripts" / "issue1631_live_e2e.py"
    case: dict[str, Any] = {
        "name": name,
        "type": "adversarial",
        "real_world": True,
        "readback": True,
        "evidence_class": "live_e2e",
        "supports_claims": ["issue1631.immutable_replay"],
        "command": [
            sys.executable,
            str(script),
            "check-service",
            "--url",
            url,
            "--qid",
            qid,
            "--want",
            "ready",
            "--receipt",
            str(receipt),
        ],
        "expected": {
            "exit_code": 0,
            "artifacts": [{"path": str(receipt), "json_pointer": "/matched", "equals": True}],
        },
    }
    if mutation:
        case["provenance"] = {}
        case["mutation_provenance"] = {"locator_changed": True}
    return case


def _manifest(case: dict[str, Any], admitted_case: dict[str, Any], app_identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": 2,
        "skill": "agentic-evals",
        "eval_kind": "runner_selftest",
        "trials": 1,
        "live": True,
        "application_identity": app_identity,
        "proof_scope": "service-backed immutable regression replay proof for issue #1631",
        "capability_claims": [
            {
                "id": "issue1631.immutable_replay",
                "description": "fixed replay only accepts the admitted test/oracle identity",
                "criticality": "critical",
                "evidence_required": {"live_e2e": True},
                "admitted_evidence": [
                    {
                        "case": case["name"],
                        "test_source_sha256": prov.test_source_hash(admitted_case),
                        "oracle_sha256": prov.oracle_hash(admitted_case),
                    }
                ],
            }
        ],
        "cases": [case],
    }


def check_service(url: str, qid: str, want: str, receipt: Path) -> int:
    with urlopen(url, timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
    observed = payload["controls"].get(qid)
    matched = observed == want
    _write_json(
        receipt,
        {
            "schema": "agentic_evals.issue1631.service_check.v1",
            "mocked": False,
            "live": True,
            "qid": qid,
            "want": want,
            "observed": observed,
            "matched": matched,
        },
    )
    return 0 if matched else 1


def _run_fixture(manifest: Path, output: Path) -> dict[str, Any]:
    cmd = [str(ROOT / "run.sh"), "run", str(manifest), "--output", str(output), "--report-only"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    if not output.is_file():
        raise RuntimeError(f"run did not write {output}: rc={result.returncode} stderr={result.stderr}")
    report = json.loads(output.read_text(encoding="utf-8"))
    return {
        "command": cmd,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-1000:],
        "stderr_tail": result.stderr[-1000:],
        "report": report,
    }


def run_proof(output: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="ae-issue1631-") as raw_tmp:
        tmp = Path(raw_tmp)
        state = tmp / "state.json"
        _write_json(state, {"controls": {"primary": "broken", "secondary": "ready"}})
        _Handler.state_path = state
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_address[1]}/state"
        try:
            receipt = tmp / "service-receipt.json"
            broken_app_identity = {
                "kind": "local_http_service",
                "source": str(ROOT / "scripts" / "issue1631_live_e2e.py"),
                "build_identity": "broken-primary-control",
            }
            fixed_app_identity = {
                "kind": "local_http_service",
                "source": str(ROOT / "scripts" / "issue1631_live_e2e.py"),
                "build_identity": "application-repaired-primary-control",
            }
            original = _case("service-qid-replay", "primary", url, receipt)
            original_manifest = tmp / "original.json"
            _write_json(original_manifest, _manifest(original, original, broken_app_identity))
            original_failed = _run_fixture(original_manifest, tmp / "original-report.json")

            locator_repair = _case(
                "service-qid-replay",
                "secondary",
                url,
                receipt,
                mutation=True,
            )
            locator_repair["provenance"] = {"prior_test_source_sha256": prov.test_source_hash(original)}
            locator_manifest = tmp / "locator-repair.json"
            _write_json(locator_manifest, _manifest(locator_repair, original, broken_app_identity))
            locator_changed = _run_fixture(locator_manifest, tmp / "locator-repair-report.json")

            _write_json(state, {"controls": {"primary": "ready", "secondary": "ready"}})
            fixed_manifest = tmp / "fixed-original.json"
            _write_json(fixed_manifest, _manifest(original, original, fixed_app_identity))
            app_repaired = _run_fixture(fixed_manifest, tmp / "fixed-report.json")
        finally:
            server.shutdown()
            thread.join(timeout=5)

    result = {
        "schema": "agentic_evals.issue1631.live_e2e_result.v1",
        "mocked": False,
        "live": True,
        "steps": {
            "original_frozen_failure": _summarize(original_failed),
            "locator_only_test_change": _summarize(locator_changed),
            "application_repair_unchanged_replay": _summarize(app_repaired),
        },
        "passed": (
            original_failed["report"]["readiness"] != "READY"
            and locator_changed["report"]["readiness"] != "READY"
            and locator_changed["report"]["cases"][0]["observed_outcome"] == "PASS"
            and locator_changed["report"]["cases"][0]["outcome"] == "FAIL"
            and app_repaired["report"]["readiness"] == "READY"
            and app_repaired["report"]["capability_readiness"]["claims"][0]["verdict"] == "PROVEN"
        ),
    }
    if not result["passed"]:
        raise SystemExit(json.dumps(result, indent=2))
    _write_json(output, result)


def _summarize(run: dict[str, Any]) -> dict[str, Any]:
    report = run["report"]
    case = report["cases"][0]
    claim = report["capability_readiness"]["claims"][0]
    return {
        "command": run["command"],
        "returncode": run["returncode"],
        "readiness": report["readiness"],
        "case_outcome": case["outcome"],
        "observed_outcome": case["observed_outcome"],
        "claim_verdict": claim["verdict"],
        "test_source_sha256": case["test_source_sha256"],
        "oracle_sha256": case["oracle_sha256"],
        "application_identity": case["application_identity"],
        "evidence_eligibility": case["evidence_eligibility"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check-service")
    check.add_argument("--url", required=True)
    check.add_argument("--qid", required=True)
    check.add_argument("--want", required=True)
    check.add_argument("--receipt", type=Path, required=True)
    proof = sub.add_parser("run-proof")
    proof.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "check-service":
        raise SystemExit(check_service(args.url, args.qid, args.want, args.receipt))
    run_proof(args.output)


if __name__ == "__main__":
    main()
