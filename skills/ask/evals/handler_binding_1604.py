"""Exercise Ask's declared transport through real CLI boundaries (ticket 1604)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "src"))
from ask.seam_models import HandlerExecutionBinding
from ask.tau_dag import resolve_handler_execution_binding
from pydantic import ValidationError


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["schema", "invalid", "api", "codex"])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    checks = []
    if args.mode == "schema":
        valid = {"handler": "claude-fable-low", "transport": "scillm.chat", "model": "claude-fable-5"}
        for bad in [dict(valid, workspace=str(SKILL)), dict(valid, surprise=True),
                    {k: v for k, v in valid.items() if k != "model"},
                    dict(valid, transport="invented"), dict(valid, model=123),
                    {"handler": "codex", "transport": "codex.exec", "model": "claude-fable-5", "workspace": str(SKILL)}]:
            try:
                HandlerExecutionBinding.model_validate(bad)
            except ValidationError as exc:
                checks.append({"rejected": True, "errors": exc.errors(include_input=False, include_url=False)})
            else:
                raise AssertionError(bad)
        assert resolve_handler_execution_binding("claude-fable-low").transport == "scillm.chat"
        assert resolve_handler_execution_binding("codex", workspace=str(SKILL)).model == "gpt-5.5"
        report = {"status": "PASS", "mocked": False, "live": False, "checks": checks}
    else:
        nonce = uuid.uuid4().hex
        command = [str(SKILL / "run.sh"), "tau-dag"]
        if args.mode == "codex":
            nonce_path = args.out / "nonce.txt"
            nonce_path.write_text(nonce)
            prompt = f'Read {nonce_path} using a local tool. Return exactly JSON {{"nonce":"the file contents"}}. Do not edit any file, run git mutations, or change configuration.'
            handlers = ["--dag-template", "single-call", "--handler", "codex", "--handler-workspace", f"codex={SKILL.parents[1]}"]
        elif args.mode == "invalid":
            prompt = "Do not run any node when the reviewer binding is invalid."
            handlers = ["--dag-template", "creator-reviewer", "--handler", "codex", "--handler-workspace", f"codex={SKILL.parents[1]}",
                        "--handler", "claude-fable-low", "--handler-workspace", f"claude-fable-low={SKILL.parents[1]}"]
        else:
            prompt = f'Return exactly this JSON: {{"nonce":"{nonce}"}}. Do not access local files.'
            handlers = ["--dag-template", "single-call", "--handler", "claude-fable-low"]
        command += [prompt, "--repo", "grahama1970/agent-skills", "--target", "ask-routing-1604",
                    "--immutable-goal", "Read-only route verification, no source changes or GitHub mutations.",
                    *handlers, "--run-output-root", str(args.out / "run"), "--execute", "--allow-provider-calls", "--json"]
        run = subprocess.run(command, cwd=SKILL.parents[1], capture_output=True, text=True, timeout=600)
        (args.out / "stdout.json").write_text(run.stdout)
        (args.out / "stderr.log").write_text(run.stderr)
        output = json.loads(run.stdout)
        bundle = output["bundle"]
        root = Path(bundle["run_dir"])
        if args.mode == "invalid":
            assert run.returncode == 2 and output["status"] == "BLOCKED", output
            assert bundle["failure_code"] == "ask_handler_binding_invalid"
            assert bundle["binding_errors"][0]["errors"][0]["type"] == "handler_workspace_transport_mismatch"
            assert not (root / "dag.json").exists() and not (root / "node-artifacts").exists()
            report = {"status": "PASS", "live": False, "mocked": False, "provider_calls": 0,
                      "proof_scope": "real CLI rejects before DAG/worker artifacts exist", "source": str(args.out / "stdout.json")}
        else:
            name = "handler-codex" if args.mode == "codex" else "handler-claude-fable-low"
            node = root / "node-artifacts" / name
            receipt = json.loads((node / "node-receipt.json").read_text())
            provider = receipt["provider_receipt"]
            expected = "$codex-cli" if args.mode == "codex" else "$scillm"
            assert run.returncode == 0 and receipt["ok"] is True, receipt.get("failure")
            assert provider["provider_transport"] == expected, provider
            raw = (node / ("response.raw.md" if args.mode == "codex" else "response.md")).read_text().strip()
            assert json.loads(raw) == {"nonce": nonce}, raw[:500]
            if args.mode == "api":
                assert provider["model"] == "claude-fable-5" and not provider.get("rate_limit_fallback"), provider
            report = {"status": "PASS", "mocked": False, "live": True, "transport": expected,
                      "response_verified": True, "node_receipt": str(node / "node-receipt.json"),
                      "proof_scope": "actual model response" if args.mode == "api" else "actual local nonce-file read, no source edits"}
    (args.out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(json.loads((args.out / "result.json").read_text())))


if __name__ == "__main__":
    main()
