#!/usr/bin/env python3
"""mailbox-mining CLI (Typer, per best-practices-skills — never argparse/click).

Division of labour, stated explicitly because it is easy to get wrong:

  /gmail owns all mailbox access (OAuth, REST API, plan/commit writes, receipts).
  This CLI owns only what /gmail does not: the redaction contract that decides
  what may enter a searchable knowledge graph, the typed writes through /memory,
  and the roundtable gate before an outbound draft is prepared.

Nothing here talks to Gmail or Google, and nothing here touches ArangoDB.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from redaction import RedactionViolation, redact_thread  # noqa: E402

RESERVED = {"contact_key", "display_name", "email_domain", "thread_text", "employer"}


def _extract(raw: object) -> tuple[list[dict], list[dict]]:
    """Single extraction path shared by `redact` and `mine`.

    They MUST agree: an earlier split implementation let `mine` skip the extra
    fields, so a credential in `outcome` reached the dry-run count unrefused
    while `redact` correctly rejected it.
    """
    threads = raw if isinstance(raw, list) else raw.get("threads", [])
    client_domains = tuple(raw.get("client_domains", []) if isinstance(raw, dict) else [])
    docs: list[dict] = []
    refused: list[dict] = []
    for t in threads:
        try:
            rec = redact_thread(
                contact_key=t["contact_key"],
                display_name=t["display_name"],
                email_domain=t.get("email_domain", ""),
                thread_text=t.get("thread_text", ""),
                employer=t.get("employer", ""),
                client_domains=client_domains,
                **{k: v for k, v in t.items() if k not in RESERVED},
            )
            docs.append(rec.to_memory_document())
        except (RedactionViolation, KeyError) as exc:
            refused.append({"contact_key": t.get("contact_key"), "reason": str(exc)})
    return docs, refused


app = typer.Typer(add_completion=False, help="Documented Gmail connector layer.")

MEMORY_URL = "http://127.0.0.1:8601"


@app.command("redact")
def redact(
    input_path: Optional[Path] = typer.Option(None, "--input", help="JSON file; omit to read stdin"),
    json_out: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    """Run agent-extracted threads through the redaction contract. Fails closed."""
    raw = json.loads(input_path.read_text() if input_path else sys.stdin.read())
    threads = raw if isinstance(raw, list) else raw.get("threads", [])
    if not threads:
        typer.echo("no threads supplied; expected a list or {'threads': [...]}", err=True)
        raise typer.Exit(2)

    ok, refused = _extract(raw)

    out = {
        "schema": "mailbox_mining.redaction_result.v1",
        "accepted": len(ok),
        "refused": len(refused),
        "export_controlled": sum(1 for d in ok if d.get("export_controlled_thread")),
        "documents": ok,
        "refusals": refused,
    }
    typer.echo(json.dumps(out, indent=2) if json_out else
               f"accepted={len(ok)} refused={len(refused)}")
    if refused and not ok:
        raise typer.Exit(1)


@app.command("mine")
def mine(
    input_path: Optional[Path] = typer.Option(None, "--input"),
    dry_run: bool = typer.Option(True, "--dry-run/--commit", help="Dry run is the default and is mandatory first"),
) -> None:
    """Redact, then (only with --commit) write typed records through /memory."""
    raw = json.loads(input_path.read_text() if input_path else sys.stdin.read())
    docs, refused = _extract(raw)

    if dry_run:
        typer.echo(json.dumps({
            "schema": "mailbox_mining.mine_receipt.v1", "mode": "dry_run", "wrote_to_memory": False,
            "would_write": len(docs), "refused": len(refused),
            "export_controlled": sum(1 for d in docs if d.get("export_controlled_thread")),
            "readiness": "NOT_ESTABLISHED — human must confirm this extraction before --commit",
            "documents": docs, "refusals": refused,
        }, indent=2))
        return

    import httpx  # deferred: dry-run path needs no network dependency

    with httpx.Client(base_url=MEMORY_URL, timeout=30.0) as client:
        resp = client.post("/upsert", json={"collection": "contacts", "documents": docs}).json()
    typer.echo(json.dumps({
        "schema": "mailbox_mining.mine_receipt.v1", "mode": "commit", "wrote_to_memory": True,
        "written": len(docs), "refused": len(refused), "memory_response": resp,
        "verify_hint": "Read back via /memory recall before reporting success — an upsert response is not proof.",
    }, indent=2))


@app.command("draft-validate")
def draft_validate(
    spec: Path = typer.Argument(..., help="Draft spec JSON"),
    schema: Path = typer.Option(
        Path("/mnt/storage12tb/workspace/experiments/resume/src/resume/job_search/inmail-draft.schema.json"),
        "--schema"),
) -> None:
    """Validate an email draft spec against grahamaco.inmail_draft.v1 (channel=email)."""
    import jsonschema

    doc = json.loads(spec.read_text())
    errors = [f"{list(e.path)}: {e.message}" for e in
              jsonschema.Draft202012Validator(json.loads(schema.read_text())).iter_errors(doc)]
    if doc.get("channel") != "email":
        errors.append("channel must be 'email' for a Gmail draft")

    # Operator decision 2026-08-02: EVERY outbound message is gated by an /ask
    # roundtable following best-practices-roundtable. Low volume + high response
    # likelihood means a bad message costs a contact permanently, so the panel is
    # the cheap option. Checked here explicitly and not left to the schema alone,
    # because this CLI is the last gate before a draft reaches the mailbox.
    rt = doc.get("roundtable_review") or {}
    if not rt:
        errors.append("roundtable_review is required: every outbound draft needs an /ask roundtable")
    else:
        if rt.get("ran") is not True:
            errors.append("roundtable_review.ran must be true")
        if rt.get("topology") != "concurrent":
            errors.append("roundtable_review.topology must be 'concurrent' (a sequential chain is a pipeline)")
        if rt.get("follows_best_practices_roundtable") is not True:
            errors.append("roundtable_review.follows_best_practices_roundtable must be true")
        if rt.get("verdict") not in ("SEND_AS_IS", "SEND_WITH_REVISIONS"):
            errors.append(f"roundtable verdict {rt.get('verdict')!r} does not permit a draft")
        passing = [x for x in rt.get("seats", []) if x.get("status") == "PASS"]
        if len(passing) < 2:
            errors.append(f"need >=2 passing seats, got {len(passing)} (one voice is not a panel)")
        if not rt.get("run_dir"):
            errors.append("roundtable_review.run_dir is required so receipts can be inspected")
    typer.echo(json.dumps({
        "schema": "mailbox_mining.draft_validation.v1",
        "valid": not errors, "errors": errors,
        "may_create_draft": not errors,
        "may_send": False,
        "note": "ops-gmail has no send command by design; the human sends.",
    }, indent=2))
    if errors:
        raise typer.Exit(1)


SEND_STEPS = {
    "email": [
        "Open Gmail -> Drafts",
        "Find the draft named in draft_id",
        "Read it once more",
        "Press Send",
    ],
    "linkedin_inmail": [
        "Open the recipient's LinkedIn profile",
        "Click Message (InMail)",
        "Paste the subject and body below",
        "Press Send",
    ],
    "employer_contact_form": [
        "Open the employer contact form URL",
        "Paste the body below",
        "Submit the form",
    ],
    "marketplace_message": [
        "Open the marketplace conversation",
        "Paste the body below",
        "Press Send",
    ],
}


def _ready(doc: dict) -> tuple[bool, str]:
    """A message may be presented only when validated and panel-approved."""
    rt = doc.get("roundtable_review") or {}
    if not rt:
        return False, "no roundtable_review"
    if rt.get("verdict") not in ("SEND_AS_IS", "SEND_WITH_REVISIONS"):
        return False, f"roundtable verdict {rt.get('verdict')!r} does not permit sending"
    if len([x for x in rt.get("seats", []) if x.get("status") == "PASS"]) < 2:
        return False, "fewer than 2 passing seats"
    v = doc.get("validation") or {}
    if not v.get("schema_valid"):
        return False, "schema_valid is not true"
    if v.get("forbidden_phrases_found"):
        return False, f"forbidden phrases: {v['forbidden_phrases_found']}"
    if doc.get("human_review", {}).get("status") == "SENT_BY_HUMAN":
        return False, "already sent"
    return True, "ready"


@app.command("outbox")
def outbox(
    directory: Path = typer.Argument(..., help="Directory of draft spec JSON files"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Present every ready message to the human, with FULL text and send steps.

    Presentation is mandatory: staging a message without showing the human what
    they would be sending is a silent queue. Nothing here transmits anything —
    InMail and Gmail are never sent automatically.
    """
    specs = sorted(directory.glob("*.json"))
    ready, withheld = [], []
    for f in specs:
        try:
            doc = json.loads(f.read_text())
        except json.JSONDecodeError as exc:
            withheld.append({"file": f.name, "reason": f"unparseable: {exc}"})
            continue
        ok, why = _ready(doc)
        (ready if ok else withheld).append(
            {"file": f.name, "doc": doc} if ok else {"file": f.name, "reason": why}
        )

    # deadline first, then fit_score descending
    def _key(item: dict) -> tuple:
        ref = item["doc"].get("opportunity_ref", {})
        return (ref.get("deadline_at") or "9999", -float(ref.get("fit_score") or 0))

    ready.sort(key=_key)

    if json_out:
        typer.echo(json.dumps({
            "schema": "mailbox_mining.outbox.v1",
            "ready_to_send": len(ready), "withheld": len(withheld),
            "nothing_is_sent_automatically": True,
            "messages": [r["doc"] for r in ready], "withheld_detail": withheld,
        }, indent=2))
        return

    if not ready:
        typer.echo("OUTBOX EMPTY — nothing is ready to send.")
        typer.echo("An empty outbox is a valid outcome; the bar was not lowered to fill it.")
    for i, item in enumerate(ready, 1):
        d = item["doc"]
        rt = d["roundtable_review"]
        rec = d.get("recipient", {})
        typer.echo("=" * 72)
        typer.echo(f"[{i}/{len(ready)}] {d.get('channel')}  —  YOU send this. Nothing was sent.")
        typer.echo(f"  to        : {rec.get('display_name')} ({rec.get('employer')})")
        typer.echo(f"  identified: {rec.get('role_basis')}")
        typer.echo(f"  lane      : {d.get('lane')}   dossier: {d.get('opportunity_ref',{}).get('dossier_path')}")
        typer.echo(f"  fit_score : {d.get('opportunity_ref',{}).get('fit_score')}")
        typer.echo(f"  intent    : {d.get('intent',{}).get('kind')} (stated in body: {d.get('intent',{}).get('stated_in_body')})")
        typer.echo(f"  the ask   : {d.get('call_to_action',{}).get('text')}")
        if d.get("subject"):
            typer.echo(f"\n  SUBJECT: {d['subject']}")
        typer.echo("\n  --- FULL MESSAGE, verbatim ---")
        for line in (d.get("body") or "").splitlines() or [""]:
            typer.echo(f"  {line}")
        typer.echo("  --- end ---")
        typer.echo("\n  claims asserted:")
        for c in d.get("claims_referenced", []):
            typer.echo(f"    - {c.get('claim_key')} [{c.get('verifiability')}] {c.get('asserted_text')}")
        seats = ", ".join(f"{s.get('handler')}={s.get('status')}" for s in rt.get("seats", []))
        typer.echo(f"\n  roundtable: {rt.get('verdict')}  seats: {seats}")
        dissent = (rt.get("synthesis") or {}).get("attributed_dissent")
        if dissent:
            typer.echo(f"  SURVIVING DISSENT (read this): {dissent}")
        if rt.get("revisions_applied"):
            typer.echo(f"  revisions applied: {rt['revisions_applied']}")
        budget = d.get("inmail_budget")
        if budget:
            typer.echo(f"  InMail budget remaining: {budget.get('remaining')}")
        typer.echo("\n  TO SEND:")
        for n, step in enumerate(SEND_STEPS.get(d.get("channel"), ["Open the channel and send manually"]), 1):
            typer.echo(f"    {n}. {step}")
    if withheld:
        typer.echo("=" * 72)
        typer.echo(f"WITHHELD ({len(withheld)}) — not presented because they are not ready:")
        for w in withheld:
            typer.echo(f"  - {w['file']}: {w['reason']}")


@app.command("assess")
def assess(target: Path = typer.Argument(..., help="File to audit for Gmail misuse")) -> None:
    """Audit external code for bespoke Gmail access that should route through this skill."""
    import re

    pat_file = Path(__file__).resolve().parent.parent / "references" / "misuse_patterns.json"
    patterns = [
        (p["name"], p["pattern"], p["severity"], p["fix"])
        for p in json.loads(pat_file.read_text())["patterns"]
    ]

    text = target.read_text()
    issues = []
    for name, pat, sev, fix in patterns:
        for m in re.finditer(pat, text, re.I):
            issues.append({"file": str(target), "line": text[:m.start()].count("\n") + 1,
                           "pattern": name, "severity": sev, "fix": fix})
    typer.echo(json.dumps({"schema": "mailbox_mining.assess.v1", "issues": issues,
                           "passed": not any(i["severity"] == "error" for i in issues)}, indent=2))
    if any(i["severity"] == "error" for i in issues):
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
