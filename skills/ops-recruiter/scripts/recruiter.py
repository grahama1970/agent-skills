"""ops-recruiter: claim-bound, humanized recruiter-reply drafting. Never sends.

Owns: build (context packet + claim ledger + preflighted $ask chain), gate
(fail-closed claim-bind check), store (one recruiter_correspondence doc to Memory).
Drafting/humanizing is $ask (webgpt then webkimi) — kept in $ask, not reimplemented.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import typer

app = typer.Typer(add_completion=False, help="Draft claim-bound humanized recruiter replies. Never sends.")

MEMORY_URL = "http://127.0.0.1:8601"
COLLECTION = "recruiter_correspondence"

# Closed domain enums (fail-closed) for the deferred analyze slice. No free-text verdicts.
DISPOSITIONS = ["PURSUE", "DEFER", "DECLINE_LOW_RATE", "DECLINE_PUSHY", "DECLINE_OFF_MANDATE", "NEEDS_HUMAN"]
RATE_SIGNALS = ["ABOVE_FLOOR", "AT_FLOOR", "BELOW_FLOOR", "RATE_UNKNOWN"]
TONE_SIGNALS = ["NORMAL", "PERSISTENT", "PUSHY", "UNKNOWN"]


def _sanitize_for_browser(text: str) -> str:
    """Make packet text surf-submittable: `~<digits>` tokens make surf reject the
    submit (browser_submit_not_accepted). Rewrite `~137K` -> `about 137K`.
    ponytail: only the tilde-digit case bites today; widen if surf rejects more.
    """
    return re.sub(r"~(\d)", r"about \1", text)


def _fail(code: str, cause: str, next_command: str) -> None:
    """Emit one unambiguous triage-shaped failure and exit non-zero.

    Pipeline failures resolve to a $triage-error catalog code or a minted
    ops_recruiter_unclassified_<8hex>. Never a vague failure.
    """
    print(json.dumps({"schema": "ops_recruiter.failure.v1", "code": code, "cause": cause,
                      "next_command": next_command}, indent=2))
    raise typer.Exit(2)


def _mint(cause: str) -> str:
    return "ops_recruiter_unclassified_" + hashlib.sha256(cause.encode()).hexdigest()[:8]


@app.command()
def status(json_out: bool = typer.Option(False, "--json")):
    """Capabilities and standing boundaries."""
    payload = {
        "schema": "ops_recruiter.status.v1",
        "immutable_goal": "Draft claim-bound, humanized recruiter replies from approved context. Never send. Human transmits.",
        "capabilities": {
            "build_packet": "IMPLEMENTED",
            "claim_bind_gate": "IMPLEMENTED_HEURISTIC",
            "correspondence_memory": "IMPLEMENTED",
            "draft_webgpt": "COMPOSED_VIA_ASK",
            "humanize_webkimi": "COMPOSED_VIA_ASK",
            "research_seed_brave": "COMPOSED_VIA_BRAVE_SEARCH",
            "analyze_rate_tone": "NOT_IMPLEMENTED_DEFERRED",
            "email_send": "PERMANENTLY_FORBIDDEN",
            "linkedin_automation": "PERMANENTLY_FORBIDDEN",
        },
        "ingestion": {"email": "via /gmail (NOT ops-google)", "linkedin": "read-only human capture via ops-linkedin"},
        "enums": {"disposition": DISPOSITIONS, "rate": RATE_SIGNALS, "tone": TONE_SIGNALS},
        "non_claims": ["Does not send email or message.", "Does not mint facts.", "Heuristic gate is not LLM claim-binding proof."],
    }
    print(json.dumps(payload, indent=2) if json_out else payload["immutable_goal"])


def _recall_thread(recruiter: str, thread_id: str):
    """Recall prior recruiter_correspondence for this recruiter/thread from Memory.

    Returns (relationship, prior_markdown, note). Fail-open: if Memory is down we
    degrade to new-contact framing and SAY SO, rather than falsely claiming first contact.
    ponytail: BM25 recall by recruiter+thread; add strict thread_id filter if noise bites.
    """
    if not recruiter and not thread_id:
        return "new", "", "no recruiter/thread key supplied"
    # Exact thread lookup uses /list filters, not /recall: a fresh custom collection
    # is not in Memory's semantic search view, so /recall returns nothing (verified).
    filters = {"thread_id": thread_id} if thread_id else {"recruiter": recruiter}
    try:
        import httpx
        r = httpx.Client(base_url=MEMORY_URL, timeout=httpx.Timeout(10.0, connect=2.0)).post(
            "/list", json={"collection": COLLECTION, "limit": 50, "filters": filters})
        r.raise_for_status()
        items = [i for i in r.json().get("documents", [])
                 if (not thread_id or i.get("thread_id") == thread_id)
                 and (not recruiter or i.get("recruiter") == recruiter)]
    except Exception as e:
        return "unknown", "", f"memory list unavailable ({type(e).__name__}); treat as possibly-existing, do not claim first contact"
    if not items:
        return "new", "", "no prior correspondence found in memory"
    items.sort(key=lambda i: i.get("received_at", ""))
    md = "\n".join(f"- [{i.get('direction','?')} {i.get('received_at','?')}] {i.get('body','')[:500]}" for i in items)
    return "existing", md, f"{len(items)} prior message(s) recalled"


@app.command()
def build(
    recruiter_message: Path = typer.Option(..., "--recruiter-message", exists=True),
    role: Path = typer.Option(..., "--role", exists=True),
    resume: Path = typer.Option(..., "--resume", exists=True),
    recruiter: str = typer.Option("", "--recruiter", help="Recruiter identity for thread recall"),
    thread_id: str = typer.Option("", "--thread-id", help="Thread id for prior-correspondence recall"),
    research: bool = typer.Option(False, "--research", help="Emit a $brave-search seed step"),
    out: Path = typer.Option(Path("/tmp/ops-recruiter"), "--out"),
):
    """Assemble the context packet (with prior-thread recall) and print the $ask chain."""
    out.mkdir(parents=True, exist_ok=True)
    relationship, prior_md, recall_note = _recall_thread(recruiter, thread_id)
    tone = {
        "existing": "You are continuing an EXISTING relationship; Graham has ALREADY connected with this recruiter. Do NOT reintroduce Graham, write first-contact framing, or offer/agree to connect (no 'glad to connect', 'open to connecting', etc.). Reference the prior thread and move the conversation forward; be collaborative.",
        "new": "No prior correspondence found; first-contact framing is appropriate.",
        "unknown": "Prior-correspondence lookup was unavailable. Do NOT assert this is a first contact; keep the opening relationship-neutral.",
    }[relationship]
    packet = out / "context-packet.md"
    packet.write_text(_sanitize_for_browser(
        f"# Recruiter reply context\n\n## Relationship: {relationship}\n{tone}\nrecall_note: {recall_note}\n\n"
        f"## Prior correspondence (from recruiter_correspondence memory)\n{prior_md or '(none)'}\n\n"
        f"## Recruiter message\n{recruiter_message.read_text()}\n\n"
        f"## Role\n{role.read_text()}\n\n## Approved resume / claim ledger (fact authority)\n{resume.read_text()}\n"
    ))
    steps = []
    if research:
        steps.append("skills/brave-search/run.sh web \"<company> <role> recruiter rate glassdoor\"  # company/role seed, cite, degradable")
        if recruiter:
            steps.append(
                f"skills/brave-search/run.sh web \"{recruiter} recruiter LinkedIn profile background history\"  "
                "# recruiter deep-research: LinkedIn page + history; seed only, cited, degradable")
    steps.append(
        f"skills/ask/scripts/browser_prompt_preflight.py --prompt 'Draft recruiter reply from packet' {packet}")
    steps.append(
        f"cd skills/ask && ./run.sh webgpt --browser-tab-lifecycle fresh-keep --attach-file {packet} "
        "'Draft a claim-bound reply to this recruiter using ONLY facts in the attached ledger. Never invent facts.'")
    steps.append(
        "cd skills/ask && ./run.sh webkimi --browser-tab-lifecycle fresh-keep --attach-file <webgpt-draft> "
        "'Humanize this draft for clarity and non-templated prose. Do not add any new factual claim.'")
    steps.append(
        f"./run.sh gate --draft <webkimi-final> --claims {resume} --relationship {relationship}   # fail-closed claim-bind + stale-connect-offer check before use")
    print(json.dumps({"schema": "ops_recruiter.build.v1", "packet": str(packet),
                      "relationship": relationship, "recall_note": recall_note, "ask_chain": steps}, indent=2))


# Connection-offer phrases: fine on a first contact, wrong on an EXISTING thread
# (Graham already connected). Kept minimal and case-insensitive.
CONNECT_OFFER_PHRASES = [
    "glad to connect", "happy to connect", "open to connecting", "let's connect",
    "lets connect", "like to connect", "love to connect", "we connect",
    "connect and learn more", "nice to connect", "great to connect",
]


@app.command()
def gate(draft: Path = typer.Option(..., "--draft", exists=True),
         claims: Path = typer.Option(..., "--claims", exists=True),
         relationship: str = typer.Option("unknown", "--relationship",
             help="existing|new|unknown; 'existing' forbids re-offering to connect")):
    """Fail-closed claim-bind check: numbers/credentials in the draft must be backed by the ledger.

    Heuristic v1: flags numeric metrics and configured fact-keywords present in the
    draft but absent from the ledger. Not LLM claim-binding proof.
    ponytail: heuristic token gate; add LLM claim-binding if false positives/negatives bite.

    With --relationship existing, also fail closed on connection-offer language: on an
    already-connected thread a draft must not re-offer to connect (the fuckery agentic-evals
    exists to catch).
    """
    ledger = claims.read_text().lower()
    text = draft.read_text()
    if relationship == "existing":
        low = text.lower()
        offered = [p for p in CONNECT_OFFER_PHRASES if p in low]
        if offered:
            _fail("ops_recruiter_stale_connect_offer",
                  f"existing thread but draft re-offers to connect: {offered}",
                  "rewrite the opening to continue the existing thread (no connect offer), then rerun gate")
    unbacked = []
    # Numbers (metrics, dates, counts) are the top overclaim risk.
    for tok in set(re.findall(r"\b\d[\d,\.]*[kKmM%+]?\b", text)):
        norm = tok.lower().rstrip(".")
        if norm.rstrip("%+km") and norm not in ledger and norm.rstrip("%+km") not in ledger:
            unbacked.append(tok)
    if unbacked:
        _fail("ops_recruiter_claim_unbacked",
              f"draft asserts facts absent from the ledger: {sorted(unbacked)}",
              "remove or rewrite each token to match an approved claim, then rerun gate")
    print(json.dumps({"schema": "ops_recruiter.gate.v1", "verdict": "PASS",
                      "checked_tokens": "numeric", "unbacked": []}, indent=2))


@app.command()
def store(message: Path = typer.Option(..., "--message", exists=True)):
    """Write one recruiter_correspondence doc to Memory via /store (no raw AQL, no vectors)."""
    try:
        doc = json.loads(message.read_text())
    except json.JSONDecodeError as e:
        _fail("ops_recruiter_bad_message_json", f"message file is not valid JSON: {e}",
              "fix the message JSON and rerun store")
    for req in ("source", "thread_id", "message_id", "direction"):
        if req not in doc:
            _fail("ops_recruiter_message_missing_field", f"missing required field: {req}",
                  f"add '{req}' to the message doc and rerun store")
    if doc["direction"] not in ("inbound", "draft", "sent", "meeting"):
        _fail("ops_recruiter_bad_direction", f"direction must be inbound|draft|sent|meeting, got {doc['direction']}",
              "set direction to inbound|draft|sent|meeting (meeting = a call/interview transcript)")
    doc.setdefault("_key", f"{doc['source']}:{doc['thread_id']}:{doc['message_id']}")
    doc.setdefault("kind", "recruiter_correspondence")
    doc.setdefault("schema", "ops_recruiter.correspondence.v1")
    # Typed signals: optional but VALIDATED when present, so stored docs are
    # uniformly minable via /list filters and /recall tags. Closed enums, fail-closed.
    sig = doc.get("signals") or {}
    if "disposition" in sig and sig["disposition"] not in DISPOSITIONS:
        _fail("ops_recruiter_bad_signal_disposition",
              f"signals.disposition must be one of {DISPOSITIONS}", "fix the disposition enum value")
    if "rate" in sig and sig["rate"] not in RATE_SIGNALS:
        _fail("ops_recruiter_bad_signal_rate",
              f"signals.rate must be one of {RATE_SIGNALS}", "fix the rate enum value")
    if "tone" in sig and sig["tone"] not in TONE_SIGNALS:
        _fail("ops_recruiter_bad_signal_tone",
              f"signals.tone must be one of {TONE_SIGNALS}", "fix the tone enum value")
    doc["signals"] = sig
    try:
        import httpx
        r = httpx.Client(base_url=MEMORY_URL, timeout=httpx.Timeout(10.0, connect=2.0)).post(
            "/store", json={"document": doc, "collection": COLLECTION})
        r.raise_for_status()
    except Exception as e:  # memory down / network — fail-closed with next step
        _fail(_mint(f"memory_store_failed:{type(e).__name__}"),
              f"Memory /store failed: {e}",
              "start the memory daemon (skills/memory/run.sh status) then rerun store")
    print(json.dumps({"schema": "ops_recruiter.store.v1", "stored_key": doc["_key"],
                      "collection": COLLECTION}, indent=2))


if __name__ == "__main__":
    app()
