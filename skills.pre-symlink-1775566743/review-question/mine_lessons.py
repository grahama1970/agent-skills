#!/usr/bin/env python3
"""Mine memory.lessons QRAs from ArangoDB into intent classifier training data.

Samples `problem` fields from memory.lessons (263k+ entries), grouped by persona
scope, applies heuristic query_type labels, and writes JSONL for train_classifiers.py.

This produces 3000-6000 real domain questions — far better than the 120 hand-crafted
questions from /review-question generate.

Usage:
    python mine_lessons.py                     # default: 500 per persona
    python mine_lessons.py --per-persona 1000  # 1000 per persona
    python mine_lessons.py --dry-run           # show counts without writing
"""
from __future__ import annotations
import os

import json
import random
import re
import subprocess
from collections import Counter
from pathlib import Path

# Output dirs (same as label_intent.py)
SCOPE_OUTPUT_DIR = Path.home() / ".pi" / "assistant" / "training_data" / "5ft-scope"
TYPE_OUTPUT_DIR = Path.home() / ".pi" / "assistant" / "training_data" / "5ft-type"
INTENT_OUTPUT_DIR = Path.home() / ".pi" / "assistant" / "training_data" / "5ft-intent"

# Persona scopes in memory.lessons
SCOPES = [
    "brandon_bailey",
    "jennifer_cheung",
    "noah_evans",
    "margaret_chen",
    "paul_nakamura",
    "embry",
]

# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)
# --- Query type heuristics (same as label_intent.py) ---

_ANALYTICAL_RE = re.compile(
    r"\b(show me|chart|graph|distribution|compare|trend|breakdown|break down|"
    r"how many|coverage|plot|visuali[sz]e|count|histogram|pie|bar chart|"
    r"top \d+|by family|by category|percentage|ratio|summary stats|"
    r"impact analysis|correlation|across|between .+ and|overlap|"
    r"list all|enumerate|tabulate|rank|sort by|group by|aggregate|"
    r"what percentage|which .+ have the most|highest|lowest)\b",
    re.IGNORECASE,
)

_STATUS_RE = re.compile(
    r"\b(status|health|daemon|service|uptime|running|connectivity|"
    r"is .+ working|are .+ online|check .+ availability)\b",
    re.IGNORECASE,
)

# Questions that are too short or too generic to be useful
_MIN_QUESTION_LEN = 20
_MAX_QUESTION_LEN = 500


def classify_query_type(question: str) -> str:
    """Heuristic query_type from question text."""
    if _STATUS_RE.search(question):
        return "status"
    if _ANALYTICAL_RE.search(question):
        return "analytical"
    return "knowledge"


def _memory_cmd(args: list, timeout: int = 60) -> dict:
    """Call embry-memory daemon via Unix socket HTTP API."""
    str_args = [str(a) for a in args]
    subcmd = str_args[0] if str_args else ""
    rest = str_args[1:]

    # Parse CLI-style flags into a dict
    params: dict = {}
    list_keys: dict[str, list] = {}
    i = 0
    while i < len(rest):
        if rest[i].startswith("--"):
            key = rest[i][2:].replace("-", "_")
            if i + 1 < len(rest) and not rest[i + 1].startswith("--"):
                val = rest[i + 1]
                if key in ("tag", "tags", "collections"):
                    list_keys.setdefault(key, []).append(val)
                else:
                    params[key] = val
                i += 2
            else:
                params[key] = True
                i += 1
        else:
            i += 1
    for k, v in list_keys.items():
        params[k] = v

    transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=float(timeout)) as client:
        if subcmd == "recall":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("k", params.get("limit", 5)))}
            for opt in ("scope", "threshold"):
                if opt in params:
                    body[opt] = float(params[opt]) if opt == "threshold" else params[opt]
            if "collections" in params:
                c = params["collections"]
                body["collections"] = c if isinstance(c, list) else [c]
            if "tags" in params:
                t = params["tags"]
                body["tags"] = t if isinstance(t, list) else [t]
            resp = client.post("/recall", json=body)
        elif subcmd == "learn":
            body = {"problem": params.get("problem", ""), "solution": params.get("solution", "")}
            if "scope" in params:
                body["scope"] = params["scope"]
            if "collection" in params:
                body["scope"] = params["collection"]
            if "tag" in params:
                body["tags"] = params["tag"] if isinstance(params["tag"], list) else [params["tag"]]
            if "tags" in params:
                body["tags"] = params["tags"] if isinstance(params["tags"], list) else [params["tags"]]
            if "json" in params:
                body.update(json.loads(params["json"]))
            resp = client.post("/learn", json=body)
        elif subcmd == "count":
            coll = params.get("collection", params.get("scope", "lessons"))
            resp = client.post("/query", json={"aql": f"RETURN LENGTH({coll})", "bind_vars": {}})
        elif subcmd == "sample":
            body = {"collection": params.get("collection", "lessons"), "limit": int(params.get("limit", 10))}
            if "fields" in params:
                body["return_fields"] = [f.strip() for f in str(params["fields"]).split(",")]
            resp = client.post("/list", json=body)
        elif subcmd == "tag":
            if "doc" in params:
                doc = json.loads(params["doc"]) if isinstance(params["doc"], str) else params["doc"]
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [doc]})
            elif "key" in params:
                tags_val = params.get("tags", "[]")
                tags_list = json.loads(tags_val) if isinstance(tags_val, str) else tags_val
                field = params.get("field", "tags")
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [{"_key": params["key"], field: tags_list}]})
            else:
                raise RuntimeError(f"Unsupported tag args: {rest}")
        elif subcmd == "search":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("limit", 10))}
            if "collection" in params:
                body["collections"] = [params["collection"]]
            if "scope" in params:
                body["scope"] = params["scope"]
            resp = client.post("/recall", json=body)
        else:
            raise RuntimeError(f"Unsupported memory subcommand via httpx: {subcmd}")
        resp.raise_for_status()
        return resp.json()

def mine_scope(scope: str, limit: int) -> list[dict]:
    """Sample lessons for a specific persona scope via /memory."""
    results = _memory_cmd([
        "sample", "--collection", "lessons",
        "--filter", f"scope={scope}",
        "--random", "--limit", str(limit),
    ])
    docs = results if isinstance(results, list) else results.get("results", [])
    return [{"problem": d.get("problem", ""), "scope": d.get("scope", scope)} for d in docs]


def clean_question(text: str) -> str | None:
    """Clean and validate a question for training use."""
    if not text:
        return None

    # Strip markdown formatting artifacts
    text = text.strip()
    text = re.sub(r"^\*\*Q:\*\*\s*", "", text)
    text = re.sub(r"^Q:\s*", "", text)
    text = re.sub(r"^\d+\.\s*", "", text)

    # Strip section references like [3.3.4. Define OT-Specific Policies...]
    text = re.sub(r"^\[.*?\]\s*", "", text)

    # Strip library/chunk references
    if re.match(r"^[A-Za-z]+ [A-Za-z]+ library:", text):
        return None

    # Length filter
    if len(text) < _MIN_QUESTION_LEN or len(text) > _MAX_QUESTION_LEN:
        return None

    # Filter out non-questions (solution text that leaked into problem field)
    if text.startswith("**Reasoning:") or text.startswith("**Answer:"):
        return None

    # Must end with ? or contain question words to be a real question
    question_words = re.compile(r"\b(what|how|why|when|where|which|who|can|should|does|do|is|are|will)\b", re.IGNORECASE)
    if not text.rstrip().endswith("?") and not question_words.search(text):
        return None

    return text


import typer
import httpx

app = typer.Typer()


@app.command()
def main(
    per_persona: int = typer.Option(500, "--per-persona", help="Samples per persona"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show counts without writing"),
    seed: int = typer.Option(42, help="Random seed"),
):
    random.seed(seed)

    all_scope_entries = []
    all_type_entries = []
    all_intent_entries = []

    for scope in SCOPES:
        print(f"Mining {scope}...", end=" ", flush=True)
        try:
            docs = mine_scope(scope, per_persona * 2)  # over-sample for filtering
        except Exception as exc:
            print(f"ERROR: {exc}")
            continue

        # Clean and filter
        cleaned = []
        for doc in docs:
            q = clean_question(doc.get("problem", ""))
            if q:
                cleaned.append(q)

        # Deduplicate
        seen = set()
        unique = []
        for q in cleaned:
            q_lower = q.lower().strip()
            if q_lower not in seen:
                seen.add(q_lower)
                unique.append(q)

        # Trim to target
        unique = unique[:per_persona]

        print(f"{len(unique)} questions (from {len(docs)} raw)")

        for q in unique:
            query_type = classify_query_type(q)
            composite = f"{scope}:{query_type}"

            entry_scope = {
                "input": {"text": q},
                "output": {"prediction": scope},
                "teacher_grade": scope,
                "source": "memory-lessons-mine",
            }
            entry_type = {
                "input": {"text": q},
                "output": {"prediction": query_type},
                "teacher_grade": query_type,
                "source": "memory-lessons-mine",
            }
            entry_intent = {
                "input": {"text": q},
                "output": {"prediction": composite},
                "teacher_grade": composite,
                "source": "memory-lessons-mine",
            }
            all_scope_entries.append(entry_scope)
            all_type_entries.append(entry_type)
            all_intent_entries.append(entry_intent)

    # Summary
    print(f"\nTotal: {len(all_scope_entries)} entries across {len(SCOPES)} scopes")

    scope_counts = Counter(e["teacher_grade"] for e in all_scope_entries)
    print("\nScope distribution:")
    for label, count in sorted(scope_counts.items()):
        print(f"  {label}: {count}")

    type_counts = Counter(e["teacher_grade"] for e in all_type_entries)
    print("\nType distribution:")
    for label, count in sorted(type_counts.items()):
        print(f"  {label}: {count}")

    if dry_run:
        print("\n(dry run — no files written)")
        return

    # Oversample the hand-crafted f36 labels to boost persona-specific signal
    # The curated questions have clearer persona vocabulary than mined QRAs
    OVERSAMPLE_FACTOR = 10
    for output_dir, entries, name in [
        (SCOPE_OUTPUT_DIR, all_scope_entries, "scope"),
        (TYPE_OUTPUT_DIR, all_type_entries, "type"),
        (INTENT_OUTPUT_DIR, all_intent_entries, "intent"),
    ]:
        output_dir.mkdir(parents=True, exist_ok=True)

        # Read existing f36 labels and oversample
        f36_path = output_dir / "labels_f36.jsonl"
        oversampled = []
        if f36_path.exists():
            with open(f36_path) as fh:
                f36_entries = [json.loads(line) for line in fh if line.strip()]
            oversampled = f36_entries * OVERSAMPLE_FACTOR
            print(f"  Oversampled {len(f36_entries)} f36 entries × {OVERSAMPLE_FACTOR} = {len(oversampled)}")

        out_path = output_dir / "labels_mined.jsonl"
        with open(out_path, "w") as fh:
            for entry in entries:
                fh.write(json.dumps(entry) + "\n")
            for entry in oversampled:
                fh.write(json.dumps(entry) + "\n")
        total = len(entries) + len(oversampled)
        print(f"Wrote {total} {name} entries to {out_path} ({len(entries)} mined + {len(oversampled)} oversampled f36)")


if __name__ == "__main__":
    app()
