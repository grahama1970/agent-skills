#!/usr/bin/env python3
"""Carry a discussion back into memory, so a later dream can know what was said.

This closes the return arc. Until now the loop ran one way: memory produced a
dream, the dream produced a journal, Embry read it aloud, and a human talked
back to her -- and the talking-back went nowhere. `conversation.jsonl` was
durable but inert. A conversation that cannot reach the next dream is a comment
thread, not a loop.

The hazard here is not losing the data, it is what the data becomes. If a human
asks "why did that memory surface?" and it is written back as an ordinary
episodic event, then next week it recalls as something that HAPPENED to her, and
a question turns into an experience. The project's whole discipline is that
synthetic content and human commentary must never silently become historical
fact.

So a turn is carried back as a thing that was SAID, never as a thing that
occurred:

  record_type   conversation_turn   -- not an event
  speaker       human | agent | embry
  said_about    the sha256 of the journal being discussed
  kind          conversation        -- its own kind, so the day's round-robin
                                       gives it a slot instead of it competing
                                       as if it were code churn

The text is stored verbatim, attributed. A later dream recalls it as
"Conversation (human said)", which is a different claim from "this happened".
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
MEMORY_SOCKET = "/run/user/1000/embry/memory.sock"
COLLECTION = "persona_memory"

#: Conversation decays slowly. What someone said about a dream is the kind of
#: thing that should still be reachable when the same tension resurfaces.
DECAY_CLASS = "slow"

#: A turn is worth recalling, but must not outrank the day's affect signal.
SALIENCE = {"human": 0.75, "agent": 0.6, "embry": 0.55}


def utc_now() -> str:
    return datetime.now().astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rel(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def day_scope(date: str) -> str:
    return f"episodic:day={date}"


def _key_for(persona: str, turn: dict[str, Any]) -> str:
    src = f"{persona}:{turn.get('created_at')}:{turn.get('role')}:{turn.get('text')}"
    return "pd_conv_" + hashlib.sha256(src.encode()).hexdigest()[:24]


def read_turns(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    problems: list[str] = []
    turns: list[dict[str, Any]] = []
    if not path.is_file():
        return [], [f"conversation_missing:{path}"]
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            problems.append(f"unparseable_line:{n}")
            continue
        if isinstance(row, dict) and str(row.get("text") or "").strip():
            turns.append(row)
    return turns, problems


def build_documents(turns: list[dict[str, Any]], persona: str, date: str) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for turn in turns:
        role = str(turn.get("role") or "unknown")
        text = str(turn.get("text") or "").strip()
        # Attribution lives in the stored text as well as the metadata. A recall
        # path that drops the metadata must still not be able to present this as
        # something that happened.
        said = f"{role} said, about my journal entry: {text}"
        docs.append({
            "_key": _key_for(persona, turn),
            "problem": f"What was said to {persona} about the {date} journal entry",
            "solution": said,
            "scope": day_scope(date),
            "tags": ["persona-dream", "conversation-turn", f"speaker:{role}",
                     f"persona:{persona}", f"day:{date}"],
            "persona_id": persona,
            "record_type": "conversation_turn",
            "kind": "conversation",
            "speaker": role,
            "said_about": turn.get("journal_spoken_sha256"),
            "salience": SALIENCE.get(role, 0.5),
            "decay_class": DECAY_CLASS,
            "day": date,
            "verbatim_text": text,
            "provenance": {
                "source": "conversation.jsonl",
                "created_at": turn.get("created_at"),
                "requested_delivery_tone": turn.get("requested_delivery_tone"),
                "boundary": ("this is a record of something said about a dream, "
                             "not a record of an event that occurred"),
            },
        })
    return docs


def _client():
    import httpx
    return httpx.Client(
        transport=httpx.HTTPTransport(uds=MEMORY_SOCKET),
        base_url="http://localhost", timeout=30.0,
    )


def carry(docs: list[dict[str, Any]], persona: str, date: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Write each turn, then prove it is retrievable. Store responses are not evidence."""
    failed: list[str] = []
    results: list[dict[str, Any]] = []
    with _client() as client:
        for doc in docs:
            try:
                resp = client.post("/store", json={"document": doc, "collection": COLLECTION})
                status, err = resp.status_code, None
            except Exception as exc:  # noqa: BLE001
                status, err = 0, str(exc)
            if err or status >= 400:
                failed.append(f"store_failed:{doc['_key']}:{status}{':' + err if err else ''}")
            results.append({"document_key": doc["_key"], "speaker": doc["speaker"],
                            "store_http_status": status, "store_error": err, "read_back": False})

        keys = {d["_key"] for d in docs}
        seen: set[str] = set()
        try:
            resp = client.post("/query", json={
                "aql": ("FOR d IN @@col FILTER d.day == @day AND d.record_type == 'conversation_turn' "
                        "AND d.persona_id == @p RETURN d._key"),
                "bind_vars": {"@col": COLLECTION, "day": date, "p": persona},
            })
            body = resp.json() or {}
            for raw in (body.get("documents") or body.get("result") or []):
                key = raw if isinstance(raw, str) else str(raw.get("_key", ""))
                if key in keys:
                    seen.add(key)
        except Exception as exc:  # noqa: BLE001
            failed.append(f"read_back_query_failed:{exc}")
    for r in results:
        r["read_back"] = r["document_key"] in seen
    missing = [r["document_key"] for r in results if not r["read_back"]]
    if missing:
        failed.append(f"carried_but_not_retrievable:{len(missing)}")
    return results, failed


def run(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir).resolve()
    path = run_dir / "conversation.jsonl"
    turns, problems = read_turns(path)

    date = args.date
    if not date:
        stamp = str((turns[0].get("created_at") if turns else "") or utc_now())
        date = stamp[:10]

    if not turns:
        return {
            "schema": "persona_dream.conversation_carry_receipt.v1",
            "created_at": utc_now(), "status": "BLOCKED_NO_TURNS_TO_CARRY",
            "mocked": False, "live": False, "run_dir": rel(run_dir),
            "conversation": rel(path), "failed_gates": problems or ["no_turns"],
        }

    docs = build_documents(turns, args.persona, date)
    results, failed = carry(docs, args.persona, date)
    failed = problems + failed

    return {
        "schema": "persona_dream.conversation_carry_receipt.v1",
        "created_at": utc_now(),
        "status": "PASS_CONVERSATION_CARRIED" if not failed else "BLOCKED_CONVERSATION_CARRY",
        "mocked": False,
        "live": True,
        "run_dir": rel(run_dir),
        "conversation": rel(path),
        "persona": args.persona,
        "date": date,
        "scope": day_scope(date),
        "collection": COLLECTION,
        "turns_carried": len(results),
        "read_back_count": sum(1 for r in results if r["read_back"]),
        "turns": results,
        "provenance_rule": (
            "each turn is stored as record_type=conversation_turn with a speaker and "
            "the sha256 of the journal it was about, and its text is prefixed with who "
            "said it. Human commentary must never recall as something that happened."
        ),
        "read_back_rule": (
            "a /store success body is not evidence; a turn counts only when an AQL "
            "query for that day's conversation turns returns its key"
        ),
        "claims": {
            "proves": [
                "the discussion is carried into memory and is retrievable there",
                "each carried turn is attributed to a speaker and bound to the journal it discussed",
            ] if not failed else [],
            "does_not_prove": [
                "that a later dream is better for having it",
                "that the persona interprets the conversation correctly",
            ],
        },
        "failed_gates": failed,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--persona", default="embry")
    ap.add_argument("--date", help="YYYY-MM-DD to file the turns under; defaults to the first turn's date")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    r = run(args)
    if args.out:
        Path(args.out).write_text(json.dumps(r, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(r, indent=2, sort_keys=True) if args.json else
          f"{r['status']}  carried={r.get('turns_carried')}  read_back={r.get('read_back_count')}  "
          f"scope={r.get('scope')}" + (f"  failed={r['failed_gates']}" if r["failed_gates"] else ""))
    return 0 if r["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
