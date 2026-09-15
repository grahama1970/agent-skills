#!/usr/bin/env python3
"""Deterministic shape checks for ask.call_log documents (offline)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ask import call_log  # noqa: E402
from ask import tau_dag  # noqa: E402


def main() -> int:
    ok_doc = call_log.document_for(
        {
            "node_id": "handler-webgemini",
            "ok": True,
            "provider_live": True,
            "provider_transport": "$surf",
            "response_path": "/tmp/x/node-artifacts/handler-webgemini/response.md",
            "response_chars": 10,
        },
        run_dir="/tmp/run-a",
        target="pdf-lab",
        status="PASS",
    )
    assert ok_doc["schema"] == "ask.call_log.v1", ok_doc
    assert ok_doc["handler"] == "webgemini", ok_doc
    assert ok_doc["status"] == "ok" and ok_doc["ok"] is True, ok_doc
    assert ok_doc["_key"] == "ask:run-a-handler-webgemini", ok_doc
    assert "webgemini call succeeded" in ok_doc["retrieval_text"], ok_doc
    assert "embedding" not in ok_doc, ok_doc

    fail_doc = call_log.document_for(
        {"node_id": "join", "ok": False, "failure": {"failure_code": "browser_handler_timeout"}},
        run_dir="/tmp/run-a",
        status="NEEDS_ATTENTION",
    )
    assert fail_doc["status"] == "error" and fail_doc["ok"] is False, fail_doc
    assert fail_doc["failure_code"] == "browser_handler_timeout", fail_doc
    assert fail_doc["handler"] == "join", fail_doc

    env_url = call_log.MEMORY_URL
    assert env_url.startswith("http://"), env_url
    retracted = {"ok": None, "status": "retracted_fixture"}
    assert not (retracted["ok"] is True) and retracted["status"] == "retracted_fixture"

    # Method denormalization: a fake run dir must yield the exact proven
    # configuration so the next web-model call is not a blind guess.
    with tempfile.TemporaryDirectory(prefix="ask-call-log-method-") as raw:
        run = Path(raw)
        node = run / "node-artifacts" / "handler-webgemini"
        node.mkdir(parents=True)
        (node / "response.md").write_text("answer\n", encoding="utf-8")
        (node / "response.meta.json").write_text(json.dumps({
            "controlled_tab_id": "42",
            "conversation_url": "https://gemini.google.com/app/x",
            "requested_reasoning": "Pro",
            "selected_reasoning": "2.5 Pro",
            "reasoning_selection_status": "selected",
            "requested_tab_id": "42",
            "roundtrip_preflight_exit_code": 0,
        }), encoding="utf-8")
        (run / "browser-tab-lifecycle.json").write_text(json.dumps({
            "mode": "fresh-keep", "cleanup_policy": "keep_created_tabs_for_inspection",
            "created_tabs": ["42"],
        }), encoding="utf-8")
        spec_dir = run / "command-specs" / "handler-webgemini"
        spec_dir.mkdir(parents=True)
        (spec_dir / "tau-dispatch-command.json").write_text(json.dumps({
            "command": ["/bin/worker", "--handler", "webgemini", "--topology", "concurrent"],
        }), encoding="utf-8")
        method_doc = call_log.document_for(
            {"node_id": "handler-webgemini", "ok": True,
             "response_path": str(node / "response.md"), "provider_live": True,
             "provider_transport": "$surf"},
            run_dir=str(run), target="t", status="PASS",
        )
        method = method_doc["method"]
        assert method["requested_reasoning"] == "Pro", method
        assert method["selected_reasoning"] == "2.5 Pro", method
        assert method["tab_lifecycle_mode"] == "fresh-keep", method
        assert method["tab_lifecycle_cleanup_policy"] == "keep_created_tabs_for_inspection", method
        assert method["dispatch_command"][1:3] == ["--handler", "webgemini"], method
        assert method_doc["controlled_tab_id"] == "42" and method_doc["conversation_url"].endswith("/x"), method_doc

    # Secret-bearing flag values are redacted before storage.
    redacted = call_log._redact_command(["--scillm-api-key", "sk-local-abc", "--handler", "webgpt"])
    assert redacted[1] == "<redacted>" and redacted[3] == "webgpt", redacted

    # Model ids come from the catalog, never a guess: an invented id is
    # rejected at compile with the nearest valid alternative.
    unknown = tau_dag.unknown_scillm_model_ids(
        ["fable-5:high", "gpt-5.5-high", "claude-fable-5", "webgemini"],
        catalog_ids=["claude-fable-5", "gpt-5.5"],
    )
    assert len(unknown) == 1 and unknown[0]["requested_model"] == "fable-5:high", unknown
    assert "claude-fable-5" in unknown[0]["alternatives"], unknown
    # Effort-suffixed selectors route to their catalog base id and must pass.
    assert not tau_dag.unknown_scillm_model_ids(
        ["gpt-5.5-high"], catalog_ids=["claude-fable-5", "gpt-5.5"]
    )

    # Seat health: three consecutive recorded failures mark a known-bad seat
    # with the exact failure codes, so a run warns before burning it again.
    docs = [
        {"ts": "2026-09-15T02:00:00Z", "ok": False, "failure_code": "browser_provider_setup_failed"},
        {"ts": "2026-09-15T01:00:00Z", "ok": False, "failure_code": "browser_submit_not_accepted"},
        {"ts": "2026-09-15T00:30:00Z", "ok": False, "failure_code": "browser_provider_setup_failed"},
        {"ts": "2026-09-14T00:00:00Z", "ok": True},
    ]
    health = call_log.seat_health("webkimi", docs=docs)
    assert health["known_bad"] is True and health["consecutive_failures"] == 3, health
    assert set(health["failure_codes"]) == {"browser_provider_setup_failed", "browser_submit_not_accepted"}, health
    healthy = call_log.seat_health("webgpt", docs=[{"ts": "2026-09-15T00:00:00Z", "ok": True}])
    assert healthy["known_bad"] is False, healthy

    # Backfill: undated run dirs get their timestamp from the node receipt's
    # mtime so history ordering reflects when runs actually happened.
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "backfill_call_log", Path(__file__).resolve().parent / "backfill_call_log.py"
    )
    backfill = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backfill)
    with tempfile.TemporaryDirectory(prefix="ask-backfill-") as raw:
        undated = Path(raw) / "ask-tau-undated-run-abc123"
        node = undated / "node-artifacts" / "handler-webkimi"
        node.mkdir(parents=True)
        receipt = node / "node-receipt.json"
        receipt.write_text("{}", encoding="utf-8")
        import os

        stamp = 1750000000  # 2025-06-15: unambiguously not "now"
        os.utime(receipt, (stamp, stamp))
        ts = backfill._run_ts(undated, receipt)
        assert ts and ts.startswith("2025-06-15"), ts

    print(
        json.dumps(
            {
                "schema": "ask.call_log_shape_eval.v1",
                "status": "PASS",
                "checked": [
                    "success document shape: schema, handler, ok, deterministic _key",
                    "failure document shape: failure_code fallback from failure dict",
                    "no embedding vectors written into Arango documents",
                    f"memory url normalized to http: {env_url}",
                    "method denormalization: reasoning, tab lifecycle, dispatch command, conversation url",
                    "invented scillm model ids rejected at compile with catalog alternatives",
                    "browser seat health marks consecutive failures before dispatch",
                ],
                "memory_url": env_url,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
