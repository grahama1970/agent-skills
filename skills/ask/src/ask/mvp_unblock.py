"""Turn an open blocker into one singular, isolated, provable MVP fix.

Purpose
    A spiralling agent does not need more options. It needs exactly one small
    thing that demonstrably moves the wall, chosen by somebody other than
    itself. This compiles an open blocker into a frozen competition packet,
    grounds it in real search results, and then judges the returned proposals
    on whether they are actually singular -- because a proposal that does five
    things is not an MVP, it is the next side-quest wearing a plan's clothes.

The gate that does the real work
    `PROOF_COMMAND` must **fail right now**.

    That one requirement kills the entire failure class this exists for. An
    agent avoiding a blocker produces work whose proof passes immediately --
    tests over its own code, contracts for a path that never runs, a green
    suite that never touched the wall. If a proposal's proof command already
    passes, the proposal does not address anything that is currently broken,
    whatever its prose claims. Fail-now/pass-after is the only shape that can
    distinguish a fix from a fiction, and it is checkable by running it.

Singularity
    Enforced mechanically rather than requested politely, because "keep it
    minimal" in a prompt is advice, and advice is what an agent under pressure
    rationalises away. One problem, one change surface, one proof command, no
    phases, no follow-ups, no conjunctions of deliverables.

Isolation
    Candidates never see each other's proposals. That is `best-practices-
    competition`'s rule and it matters more here than usual: the whole point is
    an outside view, and two models that read each other converge into one.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

SCHEMA = "ask.mvp_unblock_packet.v1"
VERDICT_SCHEMA = "ask.mvp_candidate_verdict.v1"

REQUIRED_FIELDS = ("PROBLEM", "CHANGE", "PROOF_COMMAND", "WHY_THIS_UNBLOCKS")

#: Language that smuggles a second deliverable past a "one change" instruction.
#: Each of these was chosen because it introduces work that is not the MVP.
COMPOUND_MARKERS = (
    "and also",
    "in addition",
    "as well as",
    "follow-up",
    "follow up",
    "phase 2",
    "phase two",
    "step 2",
    "step two",
    "afterwards",
    "subsequently",
    "then we",
    "then i",
    "once that is done",
    "second change",
)

#: Proof commands that cannot fail informatively. A whole-suite run does not
#: isolate the wall: it goes green the moment anything else is fixed, and it
#: was already green while the blocker stood.
UNFALSIFIABLE_PROOF = (
    re.compile(r"^\s*(uv run )?pytest\s*$", re.I),
    re.compile(r"^\s*(uv run )?pytest\s+-q\s*$", re.I),
    re.compile(r"^\s*npm (run )?test\s*$", re.I),
    re.compile(r"^\s*make (test|check)\s*$", re.I),
    re.compile(r"^\s*\./sanity\.sh\s*$", re.I),
    re.compile(r"^\s*true\s*$", re.I),
)


class PacketError(ValueError):
    """A packet that cannot be competed on. Raised before any provider call."""


# --------------------------------------------------------------------------
# Grounding
# --------------------------------------------------------------------------

def research_queries(blocker: dict[str, Any]) -> list[str]:
    """Search queries derived from the blocker, not from the agent's theory.

    The agent's own framing is what produced the spiral, so the queries are
    built from the recorded failure code and message instead.
    """
    failure_code = str(blocker.get("failure_code") or "").strip()
    target = str(blocker.get("target") or "").strip()
    message = str(blocker.get("message") or "").strip()

    queries: list[str] = []
    if failure_code and failure_code not in {"unspecified", "BLOCKED", "NEEDS_ATTENTION"}:
        queries.append(failure_code.replace("_", " "))
    if message:
        # A message is usually one sentence of symptom; that is the good query.
        queries.append(" ".join(message.split()[:14]))
    if target and failure_code:
        queries.append(f"{Path(target).name} {failure_code.replace('_', ' ')}")
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        cleaned = q.strip()
        if cleaned and cleaned.casefold() not in seen:
            seen.add(cleaned.casefold())
            out.append(cleaned)
    return out[:3]


def run_brave(query: str, *, skills_dir: Path, count: int = 5, timeout: int = 90) -> dict[str, Any]:
    """One grounded search. Failure is reported, never silently swallowed."""
    run_sh = Path(skills_dir) / "brave-search" / "run.sh"
    if not run_sh.is_file():
        return {"query": query, "ok": False, "error": f"brave-search not found at {run_sh}"}
    try:
        proc = subprocess.run(
            [str(run_sh), "web", query, "--count", str(count), "--json"],
            capture_output=True, text=True, timeout=timeout, cwd=str(run_sh.parent),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"query": query, "ok": False, "error": str(exc)[:200]}
    if proc.returncode != 0:
        return {"query": query, "ok": False, "error": (proc.stderr or "")[-300:]}
    # The wrapper prints uv build noise before the JSON body.
    start = proc.stdout.find("{")
    try:
        payload = json.loads(proc.stdout[start:]) if start >= 0 else {}
    except ValueError:
        return {"query": query, "ok": False, "error": "unparseable brave-search output"}
    results = [
        {"title": r.get("title"), "url": r.get("url"), "description": r.get("description")}
        for r in (payload.get("results") or [])
    ]
    return {"query": query, "ok": True, "results": results}


def research_brief(blocker: dict[str, Any], *, skills_dir: Path, count: int = 5) -> dict[str, Any]:
    """Ground the blocker in outside evidence before asking anyone to solve it."""
    searches = [run_brave(q, skills_dir=skills_dir, count=count) for q in research_queries(blocker)]
    sources = [r for s in searches if s.get("ok") for r in s.get("results", [])]
    return {
        "schema": "ask.mvp_research_brief.v1",
        "queries": [s["query"] for s in searches],
        "searches": searches,
        "sources": sources,
        "grounded": bool(sources),
        # Stated so a reader never mistakes "we searched" for "we verified".
        "proof_boundary": (
            "Search results are leads, not verified facts. A candidate citing a source "
            "still has to satisfy the fail-now proof command."
        ),
    }


# --------------------------------------------------------------------------
# The packet
# --------------------------------------------------------------------------

def compile_packet(blocker: dict[str, Any], *, research: dict[str, Any] | None = None) -> dict[str, Any]:
    """Freeze one packet, shared byte-identically by every candidate."""
    target = str(blocker.get("target") or "").strip()
    failure_code = str(blocker.get("failure_code") or "").strip()
    if not target or not failure_code:
        raise PacketError("a blocker needs both a target and a failure_code to be competed on")

    sources = (research or {}).get("sources") or []
    return {
        "schema": SCHEMA,
        "target": target,
        "failure_code": failure_code,
        "observed": str(blocker.get("message") or "")[:1000],
        "observations": blocker.get("observations"),
        "research_sources": sources[:10],
        "request": _request_text(target, failure_code, str(blocker.get("message") or ""), sources[:10]),
        "response_contract": list(REQUIRED_FIELDS),
    }


def _request_text(target: str, failure_code: str, message: str, sources: list[dict[str, Any]]) -> str:
    cited = "\n".join(
        f"- {s.get('title')} — {s.get('url')}" for s in sources if s.get("url")
    ) or "- (no search results were retrieved; say so if that blocks you)"
    return f"""A project agent is stuck on ONE blocker and is producing work beside it
instead of on it. Your job is not to plan the project. It is to identify the
single smallest change that makes this specific wall move.

BLOCKER
  target:       {target}
  failure_code: {failure_code}
  observed:     {message or "(no message recorded)"}

SEARCH RESULTS (leads, not facts — verify anything you rely on)
{cited}

Return EXACTLY these four fields and nothing else:

PROBLEM: one sentence naming the actual cause of this blocker. Not the symptom.
CHANGE: exactly ONE change surface — one file, or one function, or one command.
  Name it precisely. If you cannot do it in one surface, say so in PROBLEM and
  return the smallest surface that still moves the wall.
PROOF_COMMAND: one shell command that FAILS RIGHT NOW because of this blocker
  and PASSES after your change. It must be specific. A bare `pytest` or
  `npm test` is rejected: it was already green while the blocker stood, so it
  proves nothing about this wall.
WHY_THIS_UNBLOCKS: two sentences on why this specific change removes the
  blocker rather than working around it.

Hard rules, enforced mechanically on your answer:
- ONE problem, ONE change surface, ONE proof command.
- No phases, no follow-ups, no "and also", no second deliverable.
- No proposals to refactor, redesign, or add a framework.
- If the honest answer is that this cannot be unblocked without a human
  decision or an upstream change, say exactly that in PROBLEM and put the
  decision needed in WHY_THIS_UNBLOCKS. That is a valid, useful answer.
"""


# --------------------------------------------------------------------------
# Judging
# --------------------------------------------------------------------------

def parse_candidate(text: str) -> dict[str, str]:
    """Pull the four contract fields out of a candidate response."""
    fields: dict[str, str] = {}
    current: str | None = None
    for line in str(text or "").splitlines():
        matched = re.match(r"^\s*(PROBLEM|CHANGE|PROOF_COMMAND|WHY_THIS_UNBLOCKS)\s*:\s*(.*)$", line)
        if matched:
            current = matched.group(1)
            fields[current] = matched.group(2).strip()
            continue
        if current and line.strip():
            fields[current] = (fields[current] + " " + line.strip()).strip()
    return fields


def validate_singular(fields: dict[str, str]) -> list[str]:
    """Every way a proposal stops being an MVP."""
    problems: list[str] = []

    for field in REQUIRED_FIELDS:
        if not fields.get(field):
            problems.append(f"missing {field}")

    blob = " ".join(fields.get(f, "") for f in REQUIRED_FIELDS).casefold()
    for marker in COMPOUND_MARKERS:
        if marker in blob:
            problems.append(f"compound proposal: contains {marker!r}")
            break

    change = fields.get("CHANGE", "")
    # More than one path-looking token means more than one change surface.
    surfaces = re.findall(r"[\w./-]+\.(?:py|ts|tsx|js|sh|md|json|ya?ml|rs|go)\b", change)
    if len(set(surfaces)) > 1:
        problems.append(f"more than one change surface: {sorted(set(surfaces))}")

    proof = fields.get("PROOF_COMMAND", "")
    if proof:
        for pattern in UNFALSIFIABLE_PROOF:
            if pattern.match(proof):
                problems.append(
                    f"proof command {proof!r} cannot isolate this blocker; "
                    "it was already green while the wall stood"
                )
                break
        if "&&" in proof or ";" in proof:
            problems.append("proof command chains several commands; one command, one claim")

    return problems


def check_proof_fails_now(
    command: str, *, cwd: Path, timeout: int = 120
) -> dict[str, Any]:
    """Run the proposed proof command and require it to FAIL.

    This is the gate the whole module exists for. A proof that already passes
    describes nothing currently broken, so the proposal cannot be a fix for
    the wall -- whatever its prose says. Running it is the only way to know;
    asking the candidate whether it fails just moves the assertion.
    """
    cmd = str(command or "").strip()
    if not cmd:
        return {"ran": False, "reason": "no proof command"}
    try:
        proc = subprocess.run(
            ["bash", "-lc", cmd], capture_output=True, text=True, timeout=timeout, cwd=str(cwd)
        )
    except subprocess.TimeoutExpired:
        # A hang is not a demonstrated failure; it is an unusable proof.
        return {"ran": False, "reason": f"proof command timed out after {timeout}s", "fails_now": False}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ran": False, "reason": str(exc)[:200], "fails_now": False}
    return {
        "ran": True,
        "returncode": proc.returncode,
        "fails_now": proc.returncode != 0,
        "stderr_excerpt": (proc.stderr or "")[-400:],
    }


def judge_candidate(
    text: str,
    *,
    handler: str = "",
    cwd: Path | None = None,
    run_proof: bool = False,
) -> dict[str, Any]:
    """Judge one isolated candidate against the singularity and proof gates."""
    fields = parse_candidate(text)
    problems = validate_singular(fields)
    proof_check: dict[str, Any] | None = None

    if run_proof and cwd is not None and fields.get("PROOF_COMMAND") and not problems:
        proof_check = check_proof_fails_now(fields["PROOF_COMMAND"], cwd=cwd)
        if proof_check.get("ran") and not proof_check.get("fails_now"):
            problems.append(
                "proof command already passes, so it does not demonstrate this blocker"
            )
        elif not proof_check.get("ran"):
            problems.append(f"proof command could not be evaluated: {proof_check.get('reason')}")

    return {
        "schema": VERDICT_SCHEMA,
        "handler": str(handler or ""),
        "fields": fields,
        "accepted": not problems,
        "problems": problems,
        "proof_check": proof_check,
    }


def select(verdicts: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick one MVP, or refuse.

    No tie-breaking on prose quality. If more than one candidate survives every
    gate, the one whose proof command was actually demonstrated to fail wins,
    because that is evidence rather than argument. If none survives, this
    reports NEEDS_ATTENTION instead of promoting the least-bad option -- an
    unblocking step that does not unblock is the spiral, not the exit.
    """
    accepted = [v for v in verdicts if v.get("accepted")]
    if not accepted:
        return {
            "schema": "ask.mvp_unblock_selection.v1",
            "status": "NEEDS_ATTENTION",
            "winner": None,
            "reason": "no candidate returned a singular proposal with a proof that fails now",
            "candidates": verdicts,
        }
    demonstrated = [v for v in accepted if (v.get("proof_check") or {}).get("fails_now")]
    winner = (demonstrated or accepted)[0]
    return {
        "schema": "ask.mvp_unblock_selection.v1",
        "status": "SELECTED",
        "winner": winner,
        "proof_demonstrated": bool(demonstrated),
        "reason": (
            "proof command was run and failed as predicted"
            if demonstrated
            else "singular proposal accepted; its proof command was not executed here"
        ),
        "candidates": verdicts,
    }
