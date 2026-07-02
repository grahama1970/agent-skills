"""Perplexity oracle backend (one-shot CDP via surf).

Unlike tab-persistent browser lanes, Perplexity does not preserve conversation context on
a standing tab — each query opens a fresh search session. Use for fresh web
research oracle synthesis, not multi-turn review loops on the same thread.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ask_config import PERPLEXITY_DEFAULT_TIMEOUT, SURF_RUN


class PerplexityBackendError(RuntimeError):
    pass


_PATH_TOKEN_RE = re.compile(r"(?:(?:^|\s)|`)((?:~|/|\./|\.\./)[^\s`]+)")


def extract_file_attachments(question: str, *, max_bytes: int = 2_000_000) -> list[dict[str, Any]]:
    seen: set[Path] = set()
    out: list[dict[str, Any]] = []
    for match in _PATH_TOKEN_RE.finditer(question):
        token = match.group(1).rstrip(".,;:)>)")
        try:
            p = Path(token).expanduser()
        except Exception:
            continue
        if not p.is_absolute():
            try:
                p = p.resolve(strict=False)
            except Exception:
                continue
        if not p.exists() or not p.is_file() or p in seen:
            continue
        seen.add(p)
        try:
            data = p.read_bytes()
        except Exception as exc:
            out.append({"path": str(p), "error": f"read failed: {exc}", "bytes": 0, "truncated": False})
            continue
        truncated = len(data) > max_bytes
        text = data[:max_bytes].decode("utf-8", errors="replace")
        out.append({"path": str(p), "bytes": len(data), "truncated": truncated, "text": text})
    return out


def build_perplexity_prompt(base_prompt: str, attachments: list[dict[str, Any]]) -> str:
    parts = [base_prompt.strip()]
    if attachments:
        parts.extend(["", "---", "", "## Attached files", ""])
        for att in attachments:
            parts.append(f"### {att['path']}")
            if "error" in att:
                parts.append(f"_could not read: {att['error']}_")
            else:
                if att.get("truncated"):
                    parts.append(f"_truncated ({att['bytes']:,} bytes)_")
                parts.extend(["", "```", att["text"], "```"])
            parts.append("")
    return "\n".join(parts).rstrip() + "\n"


@dataclass
class PerplexityResult:
    response: str
    artifact_dir: Path
    took_ms: int
    meta: dict[str, Any]


def call_perplexity(
    prompt: str,
    *,
    timeout: float = PERPLEXITY_DEFAULT_TIMEOUT,
    mode: str = "search",
    artifact_dir: Path | None = None,
    surf_run: Path | None = None,
    run_state: object | None = None,
) -> PerplexityResult:
    surf = Path(surf_run or SURF_RUN)
    if not surf.exists():
        raise PerplexityBackendError(f"surf runtime not found: {surf}")

    if artifact_dir is None:
        artifact_dir = Path(tempfile.mkdtemp(prefix="ask-perplexity-"))
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    request_path = artifact_dir / "01_request.md"
    response_path = artifact_dir / "02_response.md"
    meta_path = artifact_dir / "02_response.meta.json"
    request_path.write_text(prompt)

    command = [
        str(surf),
        "perplexity",
        prompt,
        "--timeout",
        str(int(timeout)),
        "--mode",
        mode,
        "--keep-tab",
        "--no-activate",
    ]

    event_payload = {
        "backend": "webperplexity",
        "timeout_seconds": float(timeout),
        "mode": mode,
        "artifact_dir": str(artifact_dir),
    }
    if run_state is not None and hasattr(run_state, "event"):
        run_state.event("oracle_perplexity_call_started", **event_payload)

    start_t = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout + 60,
            cwd=surf.parent,
        )
    except subprocess.TimeoutExpired as exc:
        if run_state is not None and hasattr(run_state, "event"):
            run_state.event("oracle_perplexity_call_failed", **event_payload, error="subprocess_timeout")
        raise PerplexityBackendError(f"surf perplexity timed out after {timeout + 60:.0f}s") from exc

    took_ms = int((time.monotonic() - start_t) * 1000)
    response_text = (proc.stdout or "").strip()
    if proc.returncode != 0 or not response_text:
        if run_state is not None and hasattr(run_state, "event"):
            run_state.event(
                "oracle_perplexity_call_failed",
                **event_payload,
                returncode=proc.returncode,
                stderr_tail=(proc.stderr or "")[-2000:],
            )
        raise PerplexityBackendError(
            f"surf perplexity failed: returncode={proc.returncode}\n"
            f"stderr tail: {(proc.stderr or '')[-1000:]}"
        )

    response_path.write_text(response_text + "\n")
    meta = {"status": "completed", "returncode": proc.returncode, "response_chars": len(response_text)}
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")

    if run_state is not None and hasattr(run_state, "event"):
        run_state.event("oracle_perplexity_call_finished", **event_payload, took_ms=took_ms, response_chars=len(response_text))

    return PerplexityResult(response=response_text, artifact_dir=artifact_dir, took_ms=took_ms, meta=meta)
