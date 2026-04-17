"""Structured tool trace compression for code-runner inter-round context.

Captures tool call history as structured events, then renders to prompt text.
Incorporates Codex 5.3 review feedback:
- Structured events first, render later
- Rust error codes parsed explicitly (E0xxx + both borrow spans)
- Semantic read_file summaries (what was discovered, not just "read happened")
- Confidence-tiered DO NOT (confirmed_bad vs likely_bad vs inconclusive)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


@dataclass
class TraceEvent:
    """Single tool call + result in the trace."""
    step: int
    tool: str
    file: str = ""
    line_range: str = ""       # "180-220" or "45"
    symbol: str = ""           # function/struct name if detectable
    command: str = ""          # for run_command
    content_preview: str = ""  # first 80 chars of edit content
    exit_code: int | None = None
    outcome: str = ""          # "ok", "error", "skipped"
    error_codes: list[str] = field(default_factory=list)  # ["E0502", "E0507"]
    primary_error: str = ""    # first error line
    borrow_spans: list[str] = field(default_factory=list)  # related borrow notes
    semantic_summary: str = "" # what was discovered/changed (for reads and edits)


@dataclass
class AttemptVerdict:
    """Confidence-tiered constraint from a prior round's failed attempt."""
    description: str
    confidence: str  # "confirmed_bad", "likely_bad", "inconclusive"
    round: int
    error_code: str = ""  # e.g. "E0502"


# ── Rust error parsing ────────────────────────────────────────────────

_RUST_ERROR_RE = re.compile(r"error\[(E\d{4})\]")
_RUST_SPAN_RE = re.compile(r"-->\s+(\S+):(\d+):\d+")
_RUST_NOTE_RE = re.compile(
    r"(first|second|previous|later|immutable|mutable)\s+(borrow|use|move)"
    r".*?(here|occurs)",
    re.IGNORECASE,
)
_RUST_SYMBOL_RE = re.compile(r"`(\w+)`")


def parse_rust_diagnostics(output: str) -> dict:
    """Extract structured Rust compiler diagnostics from stderr/stdout.

    Returns: {error_codes, primary_span, borrow_notes, symbols, primary_error}
    """
    error_codes = list(dict.fromkeys(_RUST_ERROR_RE.findall(output)))  # dedup, preserve order
    spans = _RUST_SPAN_RE.findall(output)
    borrow_notes = []
    for line in output.split("\n"):
        if _RUST_NOTE_RE.search(line):
            borrow_notes.append(line.strip()[:150])
    symbols = list(dict.fromkeys(_RUST_SYMBOL_RE.findall(output)))[:10]

    # Primary error: first line containing error[
    primary_error = ""
    for line in output.split("\n"):
        if "error[" in line or (line.strip().startswith("error") and ":" in line):
            primary_error = line.strip()[:200]
            break

    return {
        "error_codes": error_codes[:5],
        "primary_span": f"{spans[0][0]}:{spans[0][1]}" if spans else "",
        "borrow_notes": borrow_notes[:4],
        "symbols": symbols,
        "primary_error": primary_error,
    }


# ── Tool trace compression ───────────────────────────────────────────

def compress_tool_trace(
    messages: list[dict],
    max_events: int = 12,
    max_chars: int = 4000,
) -> tuple[list[TraceEvent], str]:
    """Compress tool_use conversation into structured events + rendered text.

    Returns: (events, rendered_text) — events for /memory, text for prompt.

    Design choices (from Codex 5.3 review):
    - Structured events first, render to text second
    - Semantic read_file summaries (first line of result hints at content)
    - Rust error codes parsed from run_command output
    - edit_file content preview shows what was changed
    """
    events: list[TraceEvent] = []
    step = 0

    # Build a map of tool_call_id → TraceEvent for result attachment
    pending: dict[str, TraceEvent] = {}

    for msg in messages:
        role = msg.get("role", "")

        if role == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                step += 1
                func = tc.get("function") or {}
                fn = func.get("name", "unknown")
                tc_id = tc.get("id") or f"syn_{step}_{fn}"
                try:
                    args = json.loads(func.get("arguments", "{}"))
                except (json.JSONDecodeError, TypeError):
                    args = {}

                ev = TraceEvent(step=step, tool=fn)

                if fn == "read_file":
                    ev.file = args.get("path", "?")
                    start = args.get("start_line")
                    end = args.get("end_line")
                    if start is not None:
                        ev.line_range = f"{start}-{end}" if end is not None else str(start)

                elif fn == "edit_file":
                    ev.file = args.get("path", "?")
                    start = args.get("start_line")
                    end = args.get("end_line")
                    if start is not None:
                        ev.line_range = f"{start}-{end}" if end is not None else str(start)
                    content = args.get("content", "")
                    ev.content_preview = content[:80].replace("\n", " ").strip()
                    # Try to extract symbol from content
                    fn_match = re.search(r"(?:fn|struct|impl|pub fn)\s+(\w+)", content)
                    if fn_match:
                        ev.symbol = fn_match.group(1)

                elif fn == "write_file":
                    ev.file = args.get("path", "?")
                    content = args.get("content", "")
                    ev.content_preview = f"({content.count(chr(10)) + 1} lines)"

                elif fn == "run_command":
                    ev.command = args.get("command", "?")[:120]

                pending[tc_id] = ev
                events.append(ev)

        elif role == "tool":
            tc_id = msg.get("tool_call_id", "")
            content = msg.get("content", "")
            # Guard: content may be list/dict in some OpenAI-style responses
            if not isinstance(content, str):
                content = str(content)[:500]
            ev = pending.get(tc_id)
            if not ev:
                continue

            if ev.tool == "read_file":
                # Semantic summary: first non-empty line that looks meaningful
                ev.outcome = "ok"
                for line in content.split("\n")[:20]:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("//") and len(stripped) > 10:
                        # Extract structural hints
                        if any(kw in stripped for kw in ["fn ", "struct ", "impl ", "pub ", "use ", "mod "]):
                            ev.semantic_summary = stripped[:100]
                            sym = re.search(r"(?:fn|struct|impl)\s+(\w+)", stripped)
                            if sym:
                                ev.symbol = sym.group(1)
                            break

            elif ev.tool == "run_command":
                if "error" in content.lower() or "FAILED" in content:
                    ev.outcome = "error"
                    diag = parse_rust_diagnostics(content)
                    ev.error_codes = diag["error_codes"]
                    ev.primary_error = diag["primary_error"]
                    ev.borrow_spans = diag["borrow_notes"]
                    if diag["symbols"]:
                        ev.symbol = ", ".join(diag["symbols"][:3])
                else:
                    ev.outcome = "ok"
                    # Capture test summary
                    for line in reversed(content.split("\n")):
                        if "passed" in line or "ok" in line.lower():
                            ev.semantic_summary = line.strip()[:100]
                            break

            elif ev.tool in ("edit_file", "write_file"):
                ev.outcome = "ok" if content.startswith("OK") else "error"
                if ev.outcome == "error":
                    ev.primary_error = content[:150]

    # Trim to max_events — keep last failure + surrounding context
    if len(events) > max_events:
        # Find last error event
        last_err_idx = -1
        for i, e in enumerate(events):
            if e.outcome == "error":
                last_err_idx = i
        if last_err_idx >= 0:
            # Keep events around the last error
            start = max(0, last_err_idx - max_events // 2)
            events = events[start:start + max_events]
        else:
            events = events[-max_events:]

    rendered = _render_trace(events, max_chars)
    return events, rendered


def _render_trace(events: list[TraceEvent], max_chars: int = 4000) -> str:
    """Render structured events to prompt-friendly text."""
    lines = []
    for ev in events:
        if ev.tool == "read_file":
            loc = f"{ev.file}"
            if ev.line_range:
                loc += f":{ev.line_range}"
            summary = f" → {ev.semantic_summary}" if ev.semantic_summary else ""
            lines.append(f"  {ev.step}. read_file {loc}{summary}")

        elif ev.tool == "edit_file":
            loc = f"{ev.file}"
            if ev.line_range:
                loc += f":{ev.line_range}"
            sym = f" ({ev.symbol})" if ev.symbol else ""
            preview = f" → {ev.content_preview}" if ev.content_preview else ""
            lines.append(f"  {ev.step}. edit_file {loc}{sym}{preview}")

        elif ev.tool == "write_file":
            lines.append(f"  {ev.step}. write_file {ev.file} {ev.content_preview}")

        elif ev.tool == "run_command":
            cmd_short = ev.command[:80]
            lines.append(f"  {ev.step}. run_command {cmd_short}")
            if ev.outcome == "error":
                if ev.error_codes:
                    codes = ", ".join(ev.error_codes)
                    lines.append(f"     → [{codes}]: {ev.primary_error[:120]}")
                    for note in ev.borrow_spans[:2]:
                        lines.append(f"     → {note}")
                elif ev.primary_error:
                    lines.append(f"     → ERROR: {ev.primary_error[:120]}")
            elif ev.semantic_summary:
                lines.append(f"     → {ev.semantic_summary}")

        else:
            lines.append(f"  {ev.step}. {ev.tool} {ev.file or ev.command or ''}")

        if ev.outcome == "error" and ev.tool in ("edit_file", "write_file"):
            lines.append(f"     → FAILED: {ev.primary_error[:100]}")

    text = "\n".join(lines)
    return text[:max_chars]


# ── DO NOT constraint management ─────────────────────────────────────

def build_do_not_constraints(
    rounds_history: list[dict],
    current_diagnosis_do_not: list[str] | None = None,
) -> list[AttemptVerdict]:
    """Build confidence-tiered DO NOT constraints from round history.

    Codex 5.3 review: "some failed attempts were failed because of adjacent
    mistakes, not core strategy invalidity." Only hard-ban confirmed_bad.

    Rules:
    - Same error code in 2+ rounds on same file → confirmed_bad
    - Error in 1 round but score improved → inconclusive (might have been partial fix)
    - Diagnosis.do_not_do → likely_bad (diagnosis is a hypothesis)
    """
    verdicts: list[AttemptVerdict] = []

    # Collect error patterns across rounds
    error_patterns: dict[str, list[int]] = {}  # "E0502:page_renderer.rs" → [round_nums]
    for r in rounds_history:
        rnum = r.get("round", 0)
        trace_events = r.get("tool_trace_events", [])
        for ev_dict in trace_events:
            if isinstance(ev_dict, dict) and ev_dict.get("outcome") == "error":
                for code in ev_dict.get("error_codes", []):
                    key = f"{code}:{ev_dict.get('file', '?')}"
                    error_patterns.setdefault(key, []).append(rnum)

    # Confirmed bad: same error code on same file in 2+ rounds
    for pattern, rounds in error_patterns.items():
        if len(rounds) >= 2:
            code, file = pattern.split(":", 1)
            verdicts.append(AttemptVerdict(
                description=f"Rust {code} on {file} — failed in rounds {rounds}",
                confidence="confirmed_bad",
                round=rounds[-1],
                error_code=code,
            ))

    # Likely bad: from diagnosis.do_not_do
    if current_diagnosis_do_not:
        last_round = rounds_history[-1].get("round", 0) if rounds_history else 0
        for item in current_diagnosis_do_not:
            # Check if this overlaps with a confirmed constraint
            already_confirmed = any(
                v.description.lower() in item.lower() or item.lower() in v.description.lower()
                for v in verdicts if v.confidence == "confirmed_bad"
            )
            if not already_confirmed:
                verdicts.append(AttemptVerdict(
                    description=item,
                    confidence="likely_bad",
                    round=last_round,
                ))

    return verdicts


def render_do_not_block(verdicts: list[AttemptVerdict]) -> str:
    """Render DO NOT constraints with confidence tiers for the prompt."""
    if not verdicts:
        return ""

    confirmed = [v for v in verdicts if v.confidence == "confirmed_bad"]
    likely = [v for v in verdicts if v.confidence == "likely_bad"]

    lines = ["DO NOT:"]
    for v in confirmed:
        lines.append(f"  ✗ {v.description}")
    if likely:
        lines.append("PROBABLY AVOID (failed once, may work differently):")
        for v in likely:
            lines.append(f"  ? {v.description}")

    return "\n".join(lines)


# ── Structured serialization for /memory ──────────────────────────────

def trace_events_to_dict(events: list[TraceEvent]) -> list[dict]:
    """Serialize events for JSON storage in round_entry and /memory."""
    return [
        {
            "step": e.step,
            "tool": e.tool,
            "file": e.file,
            "line_range": e.line_range,
            "symbol": e.symbol,
            "command": e.command[:100] if e.command else "",
            "outcome": e.outcome,
            "error_codes": e.error_codes,
            "primary_error": e.primary_error[:200] if e.primary_error else "",
            "borrow_spans": e.borrow_spans[:2],
            "semantic_summary": e.semantic_summary[:100] if e.semantic_summary else "",
        }
        for e in events
    ]
