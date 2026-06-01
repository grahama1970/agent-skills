#!/usr/bin/env python3
"""Run a scillm streaming chat request and persist monitoring artifacts.

This is intentionally small and dependency-light. It records:
- exact request JSON
- every SSE event/data payload
- visible assistant content
- provider thinking/reasoning fields when present
- periodic /active-calls snapshots while the stream is live
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import httpx


DEFAULT_URL = "http://localhost:4001/v1/chat/completions"
DEFAULT_AUTH = "Bearer sk-dev-proxy-123"


def _json_write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _extract_reasoning(delta: dict[str, Any], choice: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    chunks: list[str] = []
    for source in (delta, choice, payload):
        for key in (
            "reasoning_content",
            "reasoning",
            "thinking",
            "thought",
            "analysis",
        ):
            value = source.get(key) if isinstance(source, dict) else None
            if isinstance(value, str) and value:
                chunks.append(value)
            elif isinstance(value, dict):
                text = value.get("content") or value.get("text") or value.get("summary")
                if isinstance(text, str) and text:
                    chunks.append(text)

    raw_output = payload.get("raw_output")
    if isinstance(raw_output, dict):
        for key in ("reasoning_content", "reasoning", "thinking", "thought"):
            value = raw_output.get(key)
            if isinstance(value, str) and value:
                chunks.append(value)
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, help="Path to chat completion request JSON")
    parser.add_argument("--out-dir", required=True, help="Directory for monitor artifacts")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--caller", default="scillm-monitor")
    parser.add_argument("--active-calls-url", default="http://localhost:4001/v1/scillm/active-calls")
    parser.add_argument("--snapshot-s", type=float, default=5.0)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    request["stream"] = True
    request["stream_progress_events"] = True
    request.setdefault("stream_heartbeat_s", 5)
    request.setdefault("timeout", 600)

    _json_write(out_dir / "request.effective.json", request)

    headers = {
        "Authorization": DEFAULT_AUTH,
        "X-Caller-Skill": args.caller,
        "Content-Type": "application/json",
    }

    events_path = out_dir / "events.jsonl"
    snapshots_path = out_dir / "active-calls.jsonl"
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    last_snapshot = 0.0

    with (
        httpx.Client(timeout=httpx.Timeout(650.0, connect=5.0)) as client,
        events_path.open("w", encoding="utf-8") as events_f,
        snapshots_path.open("w", encoding="utf-8") as snapshots_f,
        client.stream("POST", args.url, headers=headers, json=request) as response,
    ):
        response.raise_for_status()
        for line in response.iter_lines():
            now = time.time()
            if now - last_snapshot >= args.snapshot_s:
                try:
                    snap = client.get(
                        args.active_calls_url,
                        headers={"Authorization": DEFAULT_AUTH, "X-Caller-Skill": args.caller},
                        timeout=3.0,
                    ).json()
                    snapshots_f.write(json.dumps({"ts": now, "snapshot": snap}, ensure_ascii=False) + "\n")
                    snapshots_f.flush()
                except Exception as exc:  # noqa: BLE001 - monitoring must not break stream
                    snapshots_f.write(json.dumps({"ts": now, "snapshot_error": str(exc)}) + "\n")
                    snapshots_f.flush()
                last_snapshot = now

            if not line:
                continue
            record: dict[str, Any] = {"ts": now, "line": line}
            if line.startswith("event:"):
                record["event"] = line[6:].strip()
                events_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                events_f.flush()
                continue
            if not line.startswith("data:"):
                events_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                events_f.flush()
                continue

            data = line[5:].strip()
            record["data"] = data
            if data == "[DONE]":
                events_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                events_f.flush()
                break
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                events_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                events_f.flush()
                continue

            record["payload"] = payload
            choices = payload.get("choices") or []
            choice = choices[0] if choices else {}
            delta = choice.get("delta") or {}
            if isinstance(delta.get("content"), str):
                content_parts.append(delta["content"])
            reasoning_chunks = _extract_reasoning(delta, choice, payload)
            if reasoning_chunks:
                reasoning_parts.extend(reasoning_chunks)
                record["captured_reasoning"] = reasoning_chunks
            events_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            events_f.flush()

    content = "".join(content_parts)
    reasoning = "".join(reasoning_parts)
    (out_dir / "content.txt").write_text(content, encoding="utf-8")
    (out_dir / "thinking.txt").write_text(reasoning, encoding="utf-8")
    _json_write(
        out_dir / "summary.json",
        {
            "content_chars": len(content),
            "thinking_chars": len(reasoning),
            "events": str(events_path),
            "active_call_snapshots": str(snapshots_path),
            "content": str(out_dir / "content.txt"),
            "thinking": str(out_dir / "thinking.txt"),
        },
    )
    print(json.dumps(json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
