#!/usr/bin/env python3
"""Deterministic shape checks for ask.call_log documents (offline)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ask import call_log  # noqa: E402


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

    print(
        json.dumps(
            {
                "schema": "ask.call_log_shape_eval.v1",
                "status": "PASS",
                "checked": [
                    "success document shape: schema, handler, ok, deterministic _key",
                    "failure document shape: failure_code fallback from failure dict, join adapter handler",
                    "no embedding vectors written into Arango documents",
                    f"memory url normalized to http: {env_url}",
                ],
                "memory_url": env_url,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
